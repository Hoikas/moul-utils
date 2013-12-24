#    Plasma Texture Reporter
#    Copyright (C) 2013  Adam Johnson
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function
import argparse
import os.path
from PyHSPlasma import *

# Some arguments
parser = argparse.ArgumentParser(description="Plasma Texture Reporter",
                                 epilog="""This spade reports the names of Plasma Layers and Scene Objects that
                                           reference a given texture. This can be useful in some cases, such as
                                           placing Dynamic Camera Maps.
                                        """)
parser.add_argument("-a", "--age", help="An age...")
parser.add_argument("-t", "--texture", help="The name of the plBitmap that you're interested in.")

# Dict of hsGMaterial Keys to plSceneObject Keys
_mats_to_objects = {}

def _loop_thru_keys(res, type, callable):
    for loc in res.getLocations():
        for key in res.getKeys(loc, plFactory.ClassIndex(type)):
            callable(key)

def _get_objects_to_spans(key):
    """Loop through all the DrawableSpans to create a GMaterial->SceneObject map"""
    global _mats_to_objects

    # Working with DSpans is never a picnic...
    for span_key, idx in key.object.drawables:
        dspans = span_key.object
        diindices = dspans.DIIndices[idx]
        # Matrix only diindices are transforms, so we don't care about materials...
        if diindices.flags & plDISpanIndex.kMatrixOnly:
            continue

        # So, for each icicle, let's grab the material and stash it
        for icicle_index in diindices.indices:
            icicle = dspans.spans[icicle_index]
            material = dspans.materials[icicle.materialIdx]
            if material not in _mats_to_objects:
                _mats_to_objects[material] = []
            _mats_to_objects[material].append(key.object.owner)

def _search_for_layer(tex):
    """Searches all our plLayerInterfaces for a plBitmap named tex"""
    _layers = []
    _objects = []

    for material in _mats_to_objects:
        layers = material.object.layers + material.object.piggyBacks
        for layer in layers:
            interface = layer.object
            if interface.texture and interface.texture.name == tex:
                _layers.append(layer)
                _objects += _mats_to_objects[material]
    return (_layers, _objects)


def report_texture(agefile, tex):
    mgr = plResManager()
    mgr.ReadAge(agefile, True)

    # Discover how exactly our materials relate to our objects...
    _loop_thru_keys(mgr, "plDrawInterface", _get_objects_to_spans)

    # So now that we know our relationships, let's search all the materials for the given plBitmap.
    return _search_for_layer(tex)

def _print_key_prc(key,):
    blah = '<plKey Name="{}" Type="{}" Location="{};{}" LocFlag="{}" ObjID="{}"  />'.format(
        key.name, plFactory.ClassName(key.type, key.location.version), key.location.prefix,
        key.location.page, key.location.flags, key.id)
    print(blah)

if __name__ == "__main__":
    _args = parser.parse_args()
    if not os.path.isfile(_args.age):
        print("Nope, {} doesn't exist!".format(_args.age))
        

    print("Generating report for texture: {}".format(_args.texture))
    _layers, _objects = report_texture(_args.age, _args.texture)

    print("Layer Interfaces:")
    for i in _layers:
        _print_key_prc(i)
    print("\nScene Objects:")
    for i in _objects:
        _print_key_prc(i)
