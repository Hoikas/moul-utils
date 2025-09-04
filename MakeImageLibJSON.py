#    MakeImageLibJSON.py
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
import json
import logging
from pathlib import Path
import re
import sys
from typing import *

from ordered_set import OrderedSet
from PyHSPlasma import *

_parser = argparse.ArgumentParser()
_parser.add_argument("--clean", action="store_true", help="delete images not consumed by the json")
_parser.add_argument("-d", "--destination", help="Path to extract to")
_parser.add_argument("input", nargs="+")

_bitmapFlags = [
    "kBumpEnvMap",
    "kForce32Bit",
    "kDontThrowAwayImage",
    "kForceOneMipLevel",
    "kNoMaxSize",
    "kIntensityMap",
    "kHalfSize",
    "kUserOwnsBitmap",
    "kForceRewrite",
    "kForceNonCompressed",
    "kIsTexture",
    "kIsOffscreen",
    "kIsProjected",
    "kIsOrtho",
]

def _handle_mipmap(output_path: Path, mipmap: plMipmap, library: bool):
    assert mipmap.BPP == 32

    name = re.sub(r"(?:\*\d+#\d+)?\.\w+$", "", mipmap.key.name)
    srcImages = { i.name.lower(): i for i in output_path.iterdir() if i.is_file() }
    settings = dict(name=mipmap.key.name)

    # Can we find it?
    nameLower = name.lower()
    potentialImageNames = [f"{nameLower}.tga", f"{nameLower}.png", f"{nameLower}.jpg", f"{nameLower}.jpeg"]
    foundImagePath = next(filter(None, (srcImages.get(i) for i in potentialImageNames)), None)
    if foundImagePath is None:
        settings["$comment"] = "Source image not found!"
        if not library:
            settings["library"] = False
        return settings

    settings["color"] = foundImagePath.name
    if foundImagePath.suffix.lower() in {".jpg", ".jpeg"}:
        potentialAlphaNames = [
            f"alpha_{nameLower}.png",
            f"alpha_{nameLower}.tga",
            f"alpha_{nameLower}.jpg",
            f"alpha_{nameLower}.jpeg"
        ]
        foundAlphaPath = next(filter(None, (srcImages.get(i) for i in potentialAlphaNames)), None)
        if foundAlphaPath is not None:
            settings["alpha"] = foundAlphaPath.name
        else:
            settings["$alpha"] = "Alpha image not found!"

    flags = [i for i in _bitmapFlags if mipmap.flags & getattr(plBitmap, i)]
    if flags:
        settings["flags"] = flags
    if not library:
        settings["library"] = False

    # Try to avoid sending out the full dict, if possible.
    if not library or flags:
        return settings
    if set(settings.keys()) & {"$comment", "$alpha"}:
        return settings

    expectedKeyName = Path(nameLower)
    expectedKeyName = expectedKeyName.with_stem(f"{expectedKeyName.stem}*1#0").with_suffix(".hsm")
    if expectedKeyName.name != mipmap.key.name:
        return settings

    if foundAlphaPath := settings.get("alpha"):
        if re.sub(r"^ALPHA_", "", foundAlphaPath) != foundImagePath.name:
            return settings

    # Should be good enough
    return foundImagePath.name

def _make_json_file(output_path: Path, input_path: Path):
    mgr = plResManager()
    page = mgr.ReadPage(input_path)

    jsonFile = dict()
    jsonFile["page"] = dict(
        age=page.age,
        name=page.page,
        prefix=page.location.prefix,
        suffix=page.location.page
    )
    jsonFile["object"] = dict()
    jsonFile["images"] = []

    imageLibModKeys: List[plKey[plImageLibMod]] = mgr.getKeys(page.location, plFactory.kImageLibMod)
    allMipMapKeys: OrderedSet[plKey[plMipmap]] = OrderedSet(mgr.getKeys(page.location, plFactory.kMipmap))
    imLibMipMapKeys: OrderedSet[plKey[plMipmap]] = OrderedSet([j for i in imageLibModKeys for j in i.object.images])

    # Process all thingydos
    jsonFile["images"].append({"$comment": "--- Mipmaps in ImageLibMod ---"})
    for i in imLibMipMapKeys:
        jsonFile["images"].append(_handle_mipmap(output_path, i.object, True))
    jsonFile["images"].append({"$comment": "--- Loose Mipmaps ---"})
    for i in allMipMapKeys - imLibMipMapKeys:
        jsonFile["images"].append(_handle_mipmap(output_path, i.object, False))

    # We only support one ImageLibMod per JSON file (because having more than one
    # is kind of silly). So, grab the first one.
    imageLibMod: plKey[plImageLibMod] = next(iter(imageLibModKeys))
    jsonFile["object"]["name"] = imageLibMod.object.target.name
    jsonFile["object"]["library"] = imageLibMod.name

    with output_path.joinpath(f"{page.age}_{page.page}.json").open("w") as fp:
        json.dump(jsonFile, fp, indent=2)


def make_json_files(output_path: Path, input_paths: Iterable[Path]):
    for i in input_paths:
        if not (i.is_file() and i.exists()):
            logging.critical("Input file {i} does not exist!")
            sys.exit(1)

    if not (output_path.is_dir() and output_path.exists()):
        logging.critical(f"Output directory {output_path} does not exist!")
        sys.exit(1)

    for input_file in input_paths:
        _make_json_file(output_path, input_file)

if __name__ == "__main__":
    args = _parser.parse_args()

    logging.basicConfig(
        format="[%(asctime)s] %(levelname)s: %(message)s",
        level=logging.DEBUG
    )
    make_json_files(Path(args.destination), [Path(i) for i in args.input])
