#!/usr/bin/env python

# CreateClothingPRP is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CreateClothingPRP is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with CreateClothingPRP.  If not, see <http://www.gnu.org/licenses/>.

"""CreateClothingPRP.py
    A Utility for Creating Plasma Clothing Pages
    by Joseph Davies (deledrius@gmail.com)
  * Requires libHSPlasma and PyHSPlasma (https://github.com/H-uru/libhsplasma)
  Usage:
    ./CreateClothingPRP.py ... [TODO]
"""

from __future__ import annotations

import argparse
from ast import literal_eval as make_tuple
import itertools
import json
import math
from pathlib import Path
from typing import Any, Dict, Sequence
import sys

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    from PyHSPlasma import *
except ImportError as e:
    print("Required module PyHSPlasma cannot be found.")
    sys.exit(1)

## Arguments
parser = argparse.ArgumentParser(description="A Utility for Creating Plasma Clothing Pages")
parser.add_argument("-i", "--input", help="path to clothing JSON definition")
parser.add_argument("-o", "--output", default="GehnAdditions.json", help="directory containing the clothing PRP")

## Constant name-conversions
groupNames = {
    "male": plClothingItem.kClothingBaseMale,
    "female": plClothingItem.kClothingBaseFemale
}
typeNames = {
    "pants": plClothingItem.kTypePants,
    "shirt": plClothingItem.kTypeShirt,
    "lefthand": plClothingItem.kTypeLeftHand,
    "righthand": plClothingItem.kTypeRightHand,
    "face": plClothingItem.kTypeFace,
    "hair": plClothingItem.kTypeHair,
    "leftfoot": plClothingItem.kTypeLeftFoot,
    "rightfoot": plClothingItem.kTypeRightFoot,
    "accessory": plClothingItem.kTypeAccessory,
}


## Create our Resource Manager
plResMgr = plResManager()

## Empty set to hold our keys
sharedMeshKeys = set()
mipKeys = set()

def CheckForAlphaChannel(im: Image) -> bool:
    if "A" in im.getbands():
        return any((i != 0 or i != 255 for i in im.getchannel("A").tobytes()))
    else:
        # HACK: make sure we have alpha channel, otherwise bad things will happen.
        im.putalpha(255)
    return False

def FindKeyByName(keyName: str, ageKeys: Sequence[plKey], localKeys: Union[None, Sequence[plKey]] = None) -> plKey:
    # Check our local page keylist first, if provided
    if localKeys and (theKey := next((key for key in localKeys if key.name == keyName), None)):
        return theKey

    # If we haven't already found it, search the entire Age
    return next((key for key in ageKeys if key.name == keyName), None)

def CreatePage(input_path: Path, output_path: Path, gcAgeInfo: plAgeInfo, pageInfo: Dict[str, Any]) -> None:
    filename = output_path.joinpath(f"{pageInfo['agename']}_District_{pageInfo['name']}.prp")

    pageLoc = plLocation(pvMoul)
    pageLoc.prefix = pageInfo["prefix"]
    pageLoc.page = pageInfo["suffix"]
    pageLoc.flags = pageLoc.flags | plLocation.kReserved

    ## Check we don't already have a version of this page (probably from a previous export)
    existingPage = plResMgr.FindPage(pageLoc)
    if existingPage:
        ## Remove the keys from the existing page, effectively emptying it for our new contents
        oldKeysIter = itertools.chain.from_iterable((plResMgr.getKeys(pageLoc, i) for i in plResMgr.getTypes(pageLoc)))
        for key in oldKeysIter:
            plResMgr.DelObject(key)
        plResMgr.WritePage(filename, existingPage)

    newPage = plPageInfo()
    newPage.location = pageLoc
    newPage.age = pageInfo["agename"]
    newPage.page = pageInfo["name"]
    plResMgr.AddPage(newPage)

    newNode = plSceneNode()
    newNode.key.name = f"{pageInfo['agename']}_{pageInfo['name']}"

    iconList = {}
    for mipmap in (input_path.joinpath(i) for i in pageInfo["mipmaps"]):
        if not mipmap.suffix or mipmap.suffix == ".dds":
            # Load already prepared DDS in as mipmap
            mipmap = mipmap.with_suffix(".dds")
            print(f"Opening {mipmap}")
            with hsFileStream().open(mipmap, fmRead) as fs:
                dd = plDDSurface()
                dd.read(fs)
                mm = dd.createMipmap(mipmap)
        elif Image is not None:
            # Convert generic image to mipmap
            print(f"Compressing {mipmap}")
            with Image.open(mipmap) as im:
                fullAlpha = CheckForAlphaChannel(im)
                dxt = plBitmap.kDXT5 if fullAlpha else plBitmap.kDXT1
                # Major Workaround Ahoy
                # There is a bug in Cyan's level size algorithm that causes it to not allocate enough memory
                # for the color block in certain mipmaps. I personally have encountered an access violation on
                # 1x1 DXT5 mip levels -- the code only allocates an alpha block and not a color block. Paradox
                # reports that if any dimension is smaller than 4px in a mip level, OpenGL doesn't like Cyan generated
                # data. So, we're going to lop off the last two mip levels, which should be 1px and 2px as the smallest.
                # This bug is basically unfixable without crazy hacks because of the way Plasma reads in texture data.
                #     "<Deledrius> I feel like any texture at a 1x1 level is essentially academic.  I mean, JPEG/DXT
                #                  doesn't even compress that, and what is it?  Just the average color of the whole
                #                  texture in a single pixel?"
                # :)
                numLevels = math.floor(math.log(min(im.width, im.height), 2)) + 1
                if fullAlpha:
                    numLevels = max(2, numLevels - 2)
                mm = plMipmap(mipmap.name, im.width, im.height, numLevels, plMipmap.kDirectXCompression, plBitmap.kRGB8888, dxt)
                for level in range(numLevels):
                    # Hmm... im.reduce() seems to yield garbled images...
                    size = (im.width // pow(2, level), im.height // pow(2, level))
                    resizedIm = im.resize(size)
                    mm.CompressImage(level, resizedIm.tobytes())
        else:
            raise RuntimeError(f"We were unable to process the mipmap {mipmap}. Is PIL installed?")

        if mipmap.name.startswith("Icon"):
            iconList[mipmap.name] = mm.key
        plResMgr.AddObject(newPage.location, mm)

    ## Keep a list of our local Mipmaps for later
    localMipKeys = plResMgr.getKeys(pageLoc, plFactory.kMipmap)

    for clItem in pageInfo["clItems"]:
        ci = plClothingItem(f"CItm_{clItem['name']}")
        ci.key.location = newPage.location

        ci.itemName = clItem["name"]
        if clDesc := clItem.get("desc"):
            ci.description = clDesc
        if clText := clItem.get("text"):
            ci.customText = clText
        if clType := typeNames.get(clItem["type"].lower()):
            ci.type = clType
        if clGroup := groupNames.get(clItem["group"].lower()):
            ci.group = clGroup

        tint = make_tuple(clItem["tint1"])
        if tint and len(tint) == 3:
            ci.defaultTint1 = hsColorRGBA(*tint)
        else:
            print(f" Bad tint color #1 ({clItem['tint1']}) specified for {clItem['name']}")
            ci.defaultTint1 = hsColorRGBA(0,0,0)

        tint = make_tuple(clItem["tint2"])
        if tint and len(tint) == 3:
            ci.defaultTint2 = hsColorRGBA(*tint)
        else:
            print(f" Bad tint color #2 ({clItem['tint2']}) specified for {clItem['name']}")
            ci.defaultTint2 = hsColorRGBA(0,0,0)

        for meshLOD, meshName in enumerate(clItem.get("meshes", [])):
            if meshKey := FindKeyByName(meshName, sharedMeshKeys):
                ci.setMesh(plClothingItem.kLODHigh + meshLOD, meshKey)

        for idx, element in enumerate(clItem.get("elements", [])):
            #print(f" Adding element #{idx} named '{element['name']}'")
            ci.addElement(element["name"])
            for layeridx in element["layers"]:
                texName = element["layers"][layeridx]
                #print(f"  Adding layer #{layeridx} for texture '{texName}'")

                if mipKey := FindKeyByName(texName, mipKeys, localMipKeys):
                    ci.setElementTexture(idx, int(layeridx), mipKey)
                else:
                    print(f"  ** Unable to find MipMap named {texName}.  Skipping {element['name']} layer #{layeridx} in {clItem['name']}.")

        # Set appropriate icon
        if clIcon := clItem.get("icon"):
            ci.icon = iconList[clIcon]

        newNode.addPoolObject(ci.key)
        plResMgr.AddObject(newPage.location, ci)
    plResMgr.AddObject(newPage.location, newNode)

    plResMgr.WritePage(filename, newPage)

def main(input_path: Path, output_path: Path) -> None:
    version = pvMoul
    plResMgr.setVer(version)

    ## Load in the GlobalClothing Age, for access to common plKeys
    print("Loading GlobalClothing Age...")
    gcAgeInfo = plResMgr.ReadAge(output_path.joinpath("GlobalClothing.age"), True)

    ## Load the Shared Mesh and Mipmap keys for searching later
    print("Caching useful plKeys...")
    for pageIndex in range(gcAgeInfo.getNumPages()):
        gcapl = gcAgeInfo.getPageLoc(pageIndex, version)
        sharedMeshKeys.update(plResMgr.getKeys(gcapl, plFactory.kSharedMesh))
        mipKeys.update(plResMgr.getKeys(gcapl, plFactory.kMipmap))

    print("Loading clothing instruction file...")
    with input_path.open("r") as clothingFile:
        clothingData = json.load(clothingFile)
        pages = clothingData["pages"]

        for pageInfo in pages:
            print(f"Creating {pageInfo['name']}...")
            CreatePage(input_path.parent, output_path, gcAgeInfo, pageInfo)


if __name__ == '__main__':
    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if Path(args.output) else input_path.parent
    main(input_path, output_path)
