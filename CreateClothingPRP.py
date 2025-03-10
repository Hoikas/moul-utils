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
parser.add_argument("-f", "--fast", action="store_true", help="use fast but low quality compressor")
parser.add_argument("-i", "--input", help="path to clothing JSON definition")
parser.add_argument("-o", "--output", default="GehnAdditions.json", help="directory containing the clothing PRP")
parser.add_argument("-p", "--page", help="single-page export from JSON")
parser.add_argument("-r", "--round-trip", action="store_true", help="round-trip all clothing PRPs through HSPlasma")

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
sharedMeshKeys: Set[plKey] = set()
mipKeys: Set[plKey] = set()

quality = plMipmap.kBlockQualityUltra

def CheckForAlphaChannel(im: Image) -> bool:
    if "A" in im.getbands():
        return any((i != 0 and i != 255 for i in im.getchannel("A").tobytes()))
    else:
        # HACK: make sure we have alpha channel, otherwise bad things will happen.
        im.putalpha(255)
    return False

def FindKeyByName(keyName: str, ageKeys: Iterable[plKey], localKeys: Union[None, Iterable[plKey]] = None) -> plKey:
    # Check our local page keylist first, if provided
    if localKeys and (theKey := next((key for key in localKeys if key.name == keyName), None)):
        return theKey

    # If we haven't already found it, search the entire Age
    return next((key for key in ageKeys if key.name == keyName), None)

def FilterKeys(keys: Iterable[plKey], page: Optional[str]):
    if page is not None:
        location = next((i for i in plResMgr.getLocations() if plResMgr.FindPage(i).page == page))
        for key in keys:
            if key.location == location:
                yield key
    else:
        for key in keys:
            yield key

def CreatePage(input_path: Path, output_path: Path, gcAgeInfo: plAgeInfo, pageInfo: Dict[str, Any]) -> plLocation:
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
    for i in pageInfo["mipmaps"]:
        if isinstance(i, str):
            mipmap = input_path.joinpath(i)
            forceDXT5 = False
        elif isinstance(i, dict):
            mipmap = input_path.joinpath(i["name"])
            forceDXT5 = i.get("forcedxt5", False)

        # If this mipmap is an icon anywhere, then we need to force it to only be one mip level
        # this prevents interesting issues in the UI where global level chopping causes the
        # resolution to not match what the ACA python is expecting.
        isIcon = any((mipmap.name == i["icon"] for i in pageInfo["clItems"]))

        if not mipmap.suffix or mipmap.suffix == ".dds":
            # Load already prepared DDS in as mipmap
            if isIcon:
                print(f"WARNING: {mipmap} is used as an icon, you should probably NOT use a .dds file")
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
                width = pow(2, math.floor(math.log(im.width, 2)))
                height = pow(2, math.floor(math.log(im.height, 2)))

                if isIcon:
                    if im.mode != "RGBA":
                        im = im.convert("RGBA")
                    mm = plMipmap(mipmap.name, width, height, 1, plMipmap.kPNGCompression, plBitmap.kRGB8888)
                    if (im.width, im.height) != (width, height):
                        im = im.resize((width, height))
                    buf = bytearray(im.tobytes())
                    # Dammit, got to swap to BGRA and stupid PIL can't go from RGB to BGR
                    for i in range(0, len(buf), 4):
                        buf[i:i+4] = buf[i+2], buf[i+1], buf[i], buf[i+3]
                    mm.setRawImage(bytes(buf))
                else:
                    if im.mode not in {"RGB", "RGBA"}:
                        im = im.convert("RGBA")
                    fullAlpha = CheckForAlphaChannel(im) or forceDXT5
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
                    numLevels = math.floor(math.log(min(width, height), 2)) + 1
                    if fullAlpha:
                        numLevels = max(2, numLevels - 2)
                    mm = plMipmap(mipmap.name, width, height, numLevels, plMipmap.kDirectXCompression, plBitmap.kRGB8888, dxt)
                    for level in range(numLevels):
                        # Hmm... im.reduce() seems to yield garbled images...
                        size = (width // pow(2, level), height // pow(2, level))
                        resizedIm = im.resize(size)
                        mm.CompressImage(level, resizedIm.tobytes(), quality=quality)
        else:
            raise RuntimeError(f"We were unable to process the mipmap {mipmap}. Is PIL installed?")

        if mipmap.name.startswith("Icon"):
            iconList[mipmap.name] = mm.key
        plResMgr.AddObject(newPage.location, mm)

    ## Keep a list of our local Mipmaps for later
    localMipKeys = plResMgr.getKeys(newPage.location, plFactory.kMipmap)

    for clItem in pageInfo["clItems"]:
        ci = plClothingItem(f"CItm_{clItem['name']}")
        ci.key.location = newPage.location

        # 0 = the default item, 1 = everything else (no Cyan data is 2+)
        ci.sortOrder = 1

        ci.itemName = clItem["name"]
        if clDesc := clItem.get("desc"):
            ci.description = clDesc
        if clText := clItem.get("text"):
            ci.customText = clText
        if clType := typeNames.get(clItem["type"].lower()):
            ci.type = clType
        if clGroup := groupNames.get(clItem["group"].lower()):
            ci.group = clGroup

        for attr, key in dict(defaultTint1="tint1", defaultTint2="tint2").items():
            if tint := clItem.get(key):
                try:
                    color = hsColorRGBA(*tint)
                except:
                    print(f" Bad {key} color specified for {clItem['name']}")
                    setattr(ci, attr, hsColorRGBA(0.0, 0.0, 0.0))
                else:
                    setattr(ci, attr, color)

        for meshLOD, meshSpec in enumerate(clItem.get("meshes", [])):
            if isinstance(meshSpec, dict):
                meshName, meshPage = meshSpec.get("name"), meshSpec.get("page")
            else:
                meshName, meshPage = meshSpec, None

            if meshKey := FindKeyByName(meshName, FilterKeys(sharedMeshKeys, meshPage)):
                ci.setMesh(plClothingItem.kLODHigh + meshLOD, meshKey)

        for idx, element in enumerate(clItem.get("elements", [])):
            #print(f" Adding element #{idx} named '{element['name']}'")
            ci.addElement(element["name"])
            for layeridx in element["layers"]:
                texSpec = element["layers"][layeridx]
                #print(f"  Adding layer #{layeridx} for texture '{texName}'")

                if isinstance(texSpec, dict):
                    texName, texPage = texSpec.get("name"), texSpec.get("page")
                    if texPage:
                        # We won't be searching all pages because they gave us a specific page name.
                        # So, we pretend that the page they gave us is the only set of keys
                        myLocalMipKeys = None
                        myAllMipKeys = FilterKeys(mipKeys, texPage)
                    else:
                        # They didn't supply a page name, so use the standard logic.
                        myLocalMipKeys, myAllMipKeys = localMipKeys, mipKeys
                elif isinstance(texSpec, str):
                    # This is just a string entry, so use the standard logic.
                    texName = texSpec
                    myLocalMipKeys, myAllMipKeys = localMipKeys, mipKeys
                else:
                    raise ValueError

                if mipKey := FindKeyByName(texName, myAllMipKeys, myLocalMipKeys):
                    ci.setElementTexture(idx, int(layeridx), mipKey)
                else:
                    print(f"  ** Unable to find MipMap named {texName}.  Skipping {element['name']} layer #{layeridx} in {clItem['name']}.")

        # Set appropriate icon
        if clIcon := clItem.get("icon"):
            ci.icon = iconList[clIcon]

        newNode.addPoolObject(ci.key)
        plResMgr.AddObject(newPage.location, ci)
    plResMgr.AddObject(newPage.location, newNode)

    # Apply object name sorting optimizations.
    plResMgr.optimizeKeys(newPage.location)

    plResMgr.WritePage(filename, newPage)
    return newPage.location

def ProcessClothingJSON(input_path: Path, output_path: Path, gcAgeInfo: plAgeInfo, single_page: Optional[str] = None) -> Generator[plLocation]:
    print("Loading clothing instruction file...")
    with input_path.open("r") as clothingFile:
        clothingData = json.load(clothingFile)
        pages = clothingData["pages"]
        if single_page:
            pages = (i for i in pages if i["name"] == single_page)

        for pageInfo in pages:
            print(f"Creating {pageInfo['name']}...")
            yield CreatePage(input_path.parent, output_path, gcAgeInfo, pageInfo)

def main(input_path: Path, output_path: Path, round_trip: bool, single_page: Optional[str] = None) -> None:
    version = pvMoul
    plResMgr.setVer(version)

    ## Load in the GlobalClothing Age, for access to common plKeys
    print("Loading GlobalClothing Age...")
    gcAgeInfo = plResMgr.ReadAge(output_path.joinpath("GlobalClothing.age"), True)

    if round_trip:
        print("Optimizing all PRPs for name lookups...")
        for i in plResMgr.getLocations():
            plResMgr.optimizeKeys(i)

    ## Load the Shared Mesh and Mipmap keys for searching later
    print("Caching useful plKeys...")
    for pageIndex in range(gcAgeInfo.getNumPages()):
        gcapl = gcAgeInfo.getPageLoc(pageIndex, version)
        sharedMeshKeys.update(plResMgr.getKeys(gcapl, plFactory.kSharedMesh))
        mipKeys.update(plResMgr.getKeys(gcapl, plFactory.kMipmap))

    pages = set()
    if input_path:
        pages = set(ProcessClothingJSON(input_path, output_path, gcAgeInfo, single_page))

    if round_trip:
        for loc in (i for i in plResMgr.getLocations() if i not in pages):
            if page := plResMgr.FindPage(loc):
                print(f"Round-tripping '{page.page}' through HSPlasma...")
                filename = output_path.joinpath(page.getFilename(plResMgr.getVer()))
                plResMgr.WritePage(filename, page)


if __name__ == '__main__':
    args = parser.parse_args()
    input_path = Path(args.input) if args.input else None
    output_path = Path(args.output) if Path(args.output) else input_path.parent
    single_page = args.page if args.page else None
    if args.fast:
        quality = plMipmap.kBlockQualityNormal
    main(input_path, output_path, args.round_trip, single_page)
