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

import os
import sys
import json
from collections import namedtuple
from ast import literal_eval as make_tuple

try:
    import PyHSPlasma
except ImportError as e:
    print("Required module PyHSPlasma cannot be found.")
    sys.exit(1)

## Constant name-conversions
groupNames = {
    "male": PyHSPlasma.plClothingItem.kClothingBaseMale,
    "female": PyHSPlasma.plClothingItem.kClothingBaseFemale
}
typeNames = {
    "pants": PyHSPlasma.plClothingItem.kTypePants,
    "shirt": PyHSPlasma.plClothingItem.kTypeShirt,
    "lefthand": PyHSPlasma.plClothingItem.kTypeLeftHand,
    "righthand": PyHSPlasma.plClothingItem.kTypeRightHand,
    "face": PyHSPlasma.plClothingItem.kTypeFace,
    "hair": PyHSPlasma.plClothingItem.kTypeHair,
    "leftfoot": PyHSPlasma.plClothingItem.kTypeLeftFoot,
    "rightfoot": PyHSPlasma.plClothingItem.kTypeRightFoot,
    "accessory": PyHSPlasma.plClothingItem.kTypeAccessory,
}


## Create our Resource Manager
plResMgr = PyHSPlasma.plResManager()

## Empty set to hold our keys
sharedMeshKeys = set()
mipKeys = set()

def FindKeyByName(keyName, ageKeys, localKeys=None):
    # Check our local page keylist first, if provided
    theKey = None
    if localKeys:
        theKey = list({key for key in localKeys if key.name == keyName})

    # If we haven't already found it, search the entire Age
    if not theKey:
        theKey = list({key for key in ageKeys if key.name == keyName})

    return theKey

def CreatePage(gcAgeInfo, pageInfo):
    filename = "{}_District_{}.prp".format(pageInfo["agename"], pageInfo["name"])

    pageLoc = PyHSPlasma.plLocation(PyHSPlasma.pvMoul)
    pageLoc.prefix = pageInfo["prefix"]
    pageLoc.page = pageInfo["suffix"]
    pageLoc.flags = pageLoc.flags | PyHSPlasma.plLocation.kReserved

    ## Check we don't already have a version of this page (probably from a previous export)
    existingPage = plResMgr.FindPage(pageLoc)
    if existingPage:
        ## Let's ask if we should dump this page since we're planning to recreate it.
        choice = input(" '{}' already exists under the name '{}'.  Do you wish to overwrite it?  All existing contents will be lost. (y/N): ".format(pageInfo["name"], existingPage.page))
        if choice.lower() != "y":
            print(" Skipping {}.".format(pageInfo["name"]))
            return

        ## Remove the keys from the existing page, effectively emptying it for our new contents
        for type in plResMgr.getTypes(pageLoc):
            oldKeys = plResMgr.getKeys(pageLoc, type)
            for key in oldKeys:
                plResMgr.DelObject(key)
        plResMgr.WritePage(filename, existingPage)

    newPage = PyHSPlasma.plPageInfo()
    newPage.location = pageLoc
    newPage.age = pageInfo["agename"]
    newPage.page = pageInfo["name"]
    plResMgr.AddPage(newPage)

    newNode = PyHSPlasma.plSceneNode()
    newNode.key.name = "{}_{}".format(pageInfo["agename"], pageInfo["name"])

    iconList = {}
    for mipmap in pageInfo["mipmaps"]:
        dd = PyHSPlasma.plDDSurface()
        fs = PyHSPlasma.hsFileStream()
        #print("Opening {}.dds".format(mipmap))
        dd.read(fs.open("{}.dds".format(mipmap), 0))
        mm = dd.createMipmap(mipmap)
        mm.key.location = newPage.location
        if mipmap[0:4] == "Icon":
            iconList[mipmap] = mm.key
        plResMgr.AddObject(newPage.location, mm)
    ## Keep a list of our local Mipmaps for later
    localMipKeys = plResMgr.getKeys(pageLoc, PyHSPlasma.plFactory.ClassIndex("plMipmap"))

    for clItm in pageInfo["clItms"]:
        ci = PyHSPlasma.plClothingItem()
        ci.key.location = newPage.location
        ci.key.name = "CItm_{}".format(clItm["name"])

        ci.itemName = clItm["name"]
        if "desc" in clItm.keys():
            ci.description = clItm["desc"]
        if "text" in clItm.keys():
            ci.customText = clItm["text"]
        if clItm["type"].lower() in typeNames.keys():
            ci.type = typeNames[clItm["type"].lower()]
        if clItm["group"].lower() in groupNames.keys():
            ci.group = groupNames[clItm["group"].lower()]

        tint = make_tuple(clItm["tint1"])
        if tint and len(tint) == 3:
            ci.defaultTint1 = PyHSPlasma.hsColorRGBA(*tint)
        else:
            print(" Bad tint color #1 ({}) specified for {}".format(clItm["tint1"], clItm["name"]))
            ci.defaultTint1 = PyHSPlasma.hsColorRGBA(0,0,0)

        tint = make_tuple(clItm["tint2"])
        if tint and len(tint) == 3:
            ci.defaultTint2 = PyHSPlasma.hsColorRGBA(*tint)
        else:
            print(" Bad tint color #2 ({}) specified for {}".format(clItm["tint2"], clItm["name"]))
            ci.defaultTint2 = PyHSPlasma.hsColorRGBA(0,0,0)

        meshLoD = PyHSPlasma.plClothingItem.kLODHigh
        if "meshes" in clItm.keys():
            for meshName in clItm["meshes"]:
                meshKey = FindKeyByName(meshName, sharedMeshKeys)
                if meshKey:
                    # Just use the first matching mesh
                    ci.setMesh(meshLoD, meshKey[0])
                meshLoD += 1

        if "elements" in clItm.keys():
            for idx, element in enumerate(clItm["elements"]):
                #print(" Adding element #{} named '{}'".format(idx, element["name"]))
                ci.addElement(element["name"])
                for layeridx in element["layers"]:
                    texName = element["layers"][layeridx]
                    #print("  Adding layer #{} for texture '{}'".format(layeridx, texName))

                    mipKey = FindKeyByName(texName, mipKeys, localMipKeys)
                    if mipKey:
                        ci.setElementTexture(idx, int(layeridx), mipKey[0])
                    else:
                        print("  ** Unable to find MipMap named {}.  Skipping {} layer #{} in {}.".format(texName, element["name"], layeridx, clItm["name"]))

        # Set appropriate icon
        if clItm["icon"] in iconList.keys():
            ci.icon = iconList[clItm["icon"]]

        newNode.addPoolObject(ci.key)
        plResMgr.AddObject(newPage.location, ci)
    plResMgr.AddObject(newPage.location, newNode)

    plResMgr.WritePage(filename, newPage)

def main():
    version = PyHSPlasma.pvMoul
    plResMgr.setVer(version)

    ## Load in the GlobalClothing Age, for access to common plKeys
    print("Loading GlobalClothing Age...")
    gcAgeInfo = plResMgr.ReadAge("GlobalClothing.age", True)

    ## Load the Shared Mesh and Mipmap keys for searching later
    print("Caching useful plKeys...")
    for pageIndex in range(0, gcAgeInfo.getNumPages()):
        gcapl = gcAgeInfo.getPageLoc(pageIndex, version)
        smeshes = plResMgr.getKeys(gcapl, PyHSPlasma.plFactory.ClassIndex("plSharedMesh"))
        for smesh in smeshes:
            sharedMeshKeys.add(smesh)
        mips = plResMgr.getKeys(gcapl, PyHSPlasma.plFactory.ClassIndex("plMipmap"))
        for mip in mips:
            mipKeys.add(mip)

    print("Loading clothing instruction file...")
    with open("GehnAdditions.json", "r") as clothingFile:
        clothingData = json.load(clothingFile)
        pages = clothingData["pages"]

        for pageInfo in pages:
            print("Creating {}...".format(pageInfo["name"]))
            CreatePage(gcAgeInfo, pageInfo)


if __name__ == '__main__':
    main()