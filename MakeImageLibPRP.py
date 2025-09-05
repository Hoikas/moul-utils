#    MakeImageLibPRP
#    Copyright (C) 2024  Adam Johnson
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import logging
from pathlib import Path
import sys
from typing import *

from PIL import Image
from PyHSPlasma import *

_parser = argparse.ArgumentParser()
_parser.add_argument("input", nargs="+")
_parser.add_argument("-o", "--output")

def _create_res_mgr(settings: Dict[str, Any]) -> Tuple[plResManager, plPageInfo]:
    mgr = plResManager()
    mgr.setVer(pvMoul)

    location = plLocation(mgr.getVer())
    location.prefix = settings["prefix"]
    location.page = settings["suffix"]
    if location.prefix < 0:
        location.flags |= plLocation.kReserved

    page = plPageInfo()
    page.age = settings["age"]
    page.page = settings["name"]
    page.location = location
    mgr.AddPage(page)

    return mgr, page

def _add_object(mgr: plResManager, pKO: hsKeyedObject) -> None:
    # There is only one page per JSON file, so just grab it
    location = next(iter(mgr.getLocations()))
    mgr.AddObject(location, pKO)

def _create_object(mgr: plResManager, pClass: Type[KeyedT], name: str, *args, **kwargs) -> KeyedT:
    assert issubclass(pClass, hsKeyedObject)
    pObj = pClass(name, *args, **kwargs)
    _add_object(mgr, pObj)
    return pObj

def _bgra(imData: bytes, numChannels: int) -> bytes:
    if numChannels < 3:
        return imData

    buf = bytearray(imData)
    # Dammit, got to swap to BGRA and stupid PIL can't go from RGB to BGR
    for i in range(0, len(buf), numChannels):
        buf[i:i+3] = buf[i+2], buf[i+1], buf[i]
    return bytes(buf)

def _handle_alpha_flag(imMipmap: plMipmap, alphaChannel: bytes):
    # Figure out the alpha flag, yo. This is strictly speaking not needed,
    # but it allows us to avoid noisy diffs when this script regenerates
    # BkBookImages.prp for the first time.
    imMipmap.flags &= ~(plBitmap.kAlphaBitFlag | plBitmap.kAlphaChannelFlag)
    if all((i in {0, 255} for i in alphaChannel)):
        imMipmap.flags |= plBitmap.kAlphaBitFlag
    else:
        imMipmap.flags |= plBitmap.kAlphaChannelFlag

def _add_image(input_path: Path, mgr: plResManager, imSettings) -> Optional[plKey]:
    if isinstance(imSettings, dict):
        imName = imSettings.get("name")
        imColorPath = imSettings.get("color")
        imAlphaPath = imSettings.get("alpha")
        if imAlphaPath:
            imAlphaPath = Path(input_path, imAlphaPath)
        storeInLibrary = imSettings.get("library", True)
        flags = imSettings.get("flags", [])
    else:
        imColorPath = imSettings
        # If the color file prefixed with "ALPHA_" exists, use that.
        possible_alpha_paths = (
            (input_path.joinpath(f"ALPHA_{imColorPath}").with_suffix(i) for i in (".jpg", ".jpeg"))
        )
        imAlphaPath = next((i for i in possible_alpha_paths if i.is_file() and i.exists()), None)
        imName = None
        storeInLibrary = True
        flags = []

    if imColorPath:
        imColorPath = Path(input_path, imColorPath)
    elif isinstance(imSettings, dict) and "$comment" in imSettings and not "color" in imSettings:
        # Special case... It's just a comment
        return
    else:
        logging.critical(f"{imName if imName else '(Unknown Image)'} is missing the color source image")
        sys.exit(1)

    # Apply all of the fiddly Plasma Max suffixes to the name if the user didn't specify one.
    if imName is None:
        imName = imColorPath.with_stem(f"{imColorPath.stem}*1#0").with_suffix(".hsm").name.lower()

    # If it's a DDS file, this is a special case. Use DirectX compression and move along.
    if imColorPath.suffix.lower() == ".dds":
        logging.warning(f"'{imColorPath}' Will be imported directly to '{imName}'.")
        with hsFileStream().open(imColorPath, fmRead) as fs:
            dds = plDDSurface()
            dds.read(fs)
        imMipmap = dds.createMipmap(imName)
        if imMipmap.DXCompression == plMipmap.kDXT1:
            imMipmap.flags |= plBitmap.kAlphaBitFlag
        else:
            imMipmap.flags |= plBitmap.kAlphaChannelFlag
        _add_object(mgr, imMipmap)
        return imMipmap.key if storeInLibrary else None

    with ExitStack() as stack:
        imColor = stack.push(Image.open(imColorPath))
        isJPEG = bool(
            {
                imColorPath.suffix.lower(),
                imAlphaPath.suffix.lower() if imAlphaPath else ""
            } & {".jpeg", ".jpg"}
        )

        # Create the final mipmap now for stuffing purposes.
        compType = plMipmap.kJPEGCompression if isJPEG else plMipmap.kPNGCompression
        imMipmap = _create_object(
            mgr, plMipmap, imName, imColor.width, imColor.height,
            1, compType, plBitmap.kRGB8888
        )
        for flag in flags:
            if flag in {"kAlphaBitFlag", "kAlphaChannelFlag"}:
                logging.warning(f"Ignoring {flag=} - we will determine that")
                continue
            imMipmap.flags |= getattr(plBitmap, flag)

        if isJPEG:
            if imColorPath.suffix.lower() in {".jpeg", ".jpg"}:
                logging.info(f"Copying JPEG (color) file '{imColorPath.name}' into Mipmap '{imName}'")
                with imColorPath.open("rb") as s:
                    colorBuf = s.read()
                imMipmap.setImageJPEG(colorBuf)
            else:
                if imColor.mode != "RGB":
                    imColorRGB = imColor.convert("RGB")
                logging.info(f"Copying RLE (color) data '{imColorPath.name}' into Mipmap '{imName}'")
                imMipmap.setColorData(_bgra(imColorRGB.tobytes(), 3))

            if imAlphaPath and imAlphaPath.suffix.lower() in {".jpeg", ".jpg"}:
                logging.info(f"Copying JPEG (alpha) file '{imAlphaPath.name}' into Mipmap '{imName}'")
                with imAlphaPath.open("rb") as s:
                    alphaBuf = s.read()
                imMipmap.setAlphaJPEG(alphaBuf)
            else:
                if not imAlphaPath:
                    imAlpha = imColor
                    imAlphaPath = imColorPath
                else:
                    imAlpha = stack.push(Image.open(imAlphaPath))
                if imAlpha.mode not in {"L", "RGBA"}:
                    imAlpha = imAlpha.convert("RGBA").getchannel(3)
                elif imAlpha.mode == "RGBA":
                    imAlpha = imAlpha.getchannel(3)
                logging.info(f"Copying RLE (alpha) data '{imAlphaPath.name}' into Mipmap '{imName}'")
                imMipmap.setAlphaData(imAlpha.tobytes())
            _handle_alpha_flag(imMipmap, imMipmap.extractAlphaData())
        else:
            if imColor.mode != "RGBA":
                imColor = imColor.convert("RGBA")
            if imAlphaPath:
                logging.info(f"Combining '{imColorPath}' and {imAlphaPath}")
                imAlpha = stack.push(Image.open(imAlphaPath))
                if imAlpha.mode not in {"L", "RGBA"}:
                    imAlpha = imAlpha.convert("RGBA").getchannel(3)
                elif imAlpha.mode == "RGBA":
                    imAlpha = imAlpha.getchannel(3)
                imColor = Image.merge(
                    "RGBA",
                    [
                        imColor.getchannel(0),
                        imColor.getchannel(1),
                        imColor.getchannel(2),
                        imAlpha
                    ]
                )
            else:
                logging.debug(f"No alpha image file for '{imColorPath}' (using whatever is in the color file)")
            logging.info(f"Storing level #0 of {imName}")
            imMipmap.setLevel(0, _bgra(imColor.tobytes(), 4))
            _handle_alpha_flag(imMipmap, imColor.getchannel(3).tobytes())

    if storeInLibrary:
        return imMipmap.key

def make_image_prp(input_path: Path, output_path: Path, settings: Dict[str, Any]):
    mgr, page = _create_res_mgr(settings["page"])

    sceneNode = _create_object(mgr, plSceneNode, f"{page.age}_{page.page}")
    sceneObj = _create_object(mgr, plSceneObject, settings["object"]["name"])
    imageLib = _create_object(mgr, plImageLibMod, settings["object"]["library"])

    sceneNode.addSceneObject(sceneObj.key)
    sceneObj.addModifier(imageLib.key)
    sceneObj.sceneNode = sceneNode.key

    for imSettings in settings["images"]:
        if imKey := _add_image(input_path, mgr, imSettings):
            imageLib.addImage(imKey)

    mgr.optimizeKeys(page.location)
    mgr.WritePage(output_path.joinpath(f"{page.age}_District_{page.page}.prp"), page)


if __name__ == "__main__":
    args = _parser.parse_args()
    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        level=logging.INFO
    )

    if args.output:
        output_path = Path(args.output)
        if not (output_path.is_dir() and output_path.exists()):
            logging.critical(f"Output directory {output_path} is invalid!")
            sys.exit(1)
    else:
        output_path = None

    for i in args.input:
        input_file_path = Path(i)
        if not (input_file_path.is_file() and input_file_path.exists()):
            logging.error(f"{input_file_path.name} does not exist! Skipping.")
            continue

        with input_file_path.open("r") as fp:
            settings = json.load(fp)

        if output_path is None:
            current_output_path = input_file_path.parent
        else:
            current_output_path = output_path

        make_image_prp(input_file_path.parent, current_output_path, settings)
