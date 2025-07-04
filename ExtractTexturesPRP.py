#    ExtractTexturesPRP
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
from pathlib import Path
import logging
from typing import *
import re
import sys

from PIL import Image
from PyHSPlasma import *

_parser = argparse.ArgumentParser()
_parser.add_argument("-d", "--destination", help="Path to extract to")
_parser.add_argument("input", nargs="+")

def _bgra(imData: bytes, numChannels: int) -> bytes:
    if numChannels < 3:
        return imData

    buf = bytearray(imData)
    # Dammit, got to swap to BGRA and stupid PIL can't go from RGB to BGR
    for i in range(0, len(buf), numChannels):
        buf[i:i+3] = buf[i+2], buf[i+1], buf[i]
    return bytes(buf)

def _export_jpeg(output_path: Path, name: str, image: plMipmap, data: bytes):
    image_path = output_path.joinpath(name).with_suffix(".jpg")
    logging.debug(f"Saving '{image_path}'")
    with image_path.open("wb") as s:
        s.write(data)

def _export_png(output_path: Path, name: str, image: plMipmap, data: bytes):
    image_path = output_path.joinpath(name).with_suffix(".png")
    if not data:
        logging.debug(f"Empty data, not saving '{image_path}'")
        return

    logging.debug(f"Saving '{image_path}'")
    imLen = len(data)
    numChannels = imLen // image.width // image.height
    if numChannels == 4:
        mode = "RGBA"
    elif numChannels == 3:
        mode = "RGB"
    elif numChannels == 1:
        mode = "L"
    else:
        raise RuntimeError
    logging.debug(f"{image.width=}, {image.height=}, {len(data)=}, {numChannels=}")

    imData = Image.frombytes(mode, (image.width, image.height), _bgra(data, numChannels))
    imData.save(image_path)

def _export_image(output_path: Path, image: plMipmap):
    logging.info(f"Saving image '{image.key.name}'")

    image_name = re.sub(r"[<>:\"/\|?*]", "_", re.sub(r"(?:\*\d+#\d+)?\.\w+$", "", image.key.name))
    if image.compressionType == plBitmap.kDirectXCompression:
        dds = plDDSurface()
        dds.setFromMipmap(image)
        image_path = output_path.joinpath(image_name).with_suffix(".dds")
        with hsFileStream().open(image_path, fmWrite) as fs:
            dds.write(fs)
    elif image.compressionType == plBitmap.kJPEGCompression:
        logging.debug(f"{image.isImageJPEG()=}, {image.isAlphaJPEG()=}")
        if image.isImageJPEG() and image.isAlphaJPEG():
            _export_jpeg(output_path, image_name, image, image.jpegImage)
            _export_jpeg(output_path, f"ALPHA_{image_name}", image, image.jpegAlpha)
        elif image.isImageJPEG() and not image.isAlphaJPEG():
            _export_jpeg(output_path, image_name, image, image.jpegImage)
            _export_png(output_path, f"ALPHA_{image_name}", image, image.extractAlphaData())
        elif not image.isImageJPEG() and image.isAlphaJPEG():
            # NOTE: for some reason, plMipmap.extractColorData() is returning garbage,
            # so we'll just output the decompressed alpha data into the PNG. That may make
            # the most sense for now.
            _export_png(output_path, image_name, image, image.getLevel(0))
            _export_jpeg(output_path, f"ALPHA_{image_name}", image, image.jpegAlpha)
        elif not image.isImageJPEG() and not image.isAlphaJPEG():
            _export_png(output_path, image_name, image, image.getLevel(0))
        else:
            raise RuntimeError
    else:
        _export_png(output_path, image_name, image, image.getLevel(0))

def _export_images_from_prp(output_path: Path, input_path: Path):
    logging.info(f"Processing '{input_path.name}'")

    mgr = plResManager()
    page = mgr.ReadPage(input_path)

    mmKeys = mgr.getKeys(page.location, plFactory.kMipmap)
    for mmKey in mmKeys:
        _export_image(output_path, mmKey.object)

def export_images(output_path: Path, input_paths: Iterable[Path]):
    for i in input_paths:
        if not (i.is_file() and i.exists()):
            logging.critical("Input file {i} does not exist!")
            sys.exit(1)

    if not (output_path.is_dir() and output_path.exists()):
        logging.critical(f"Output directory {output_path} does not exist!")
        sys.exit(1)

    for input_file in input_paths:
        _export_images_from_prp(output_path, input_file)

if __name__ == "__main__":
    args = _parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        level=logging.DEBUG
    )
    export_images(Path(args.destination), [Path(i) for i in args.input])
