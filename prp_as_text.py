#!/usr/bin/env python

# PRP_as_Text is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PRP_as_Text is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PRP_as_Text.  If not, see <http://www.gnu.org/licenses/>.

"""prp_as_text.py
    A utility for producing a textual overview of a PRP file,
    used to compare in diffs.
    by Joseph Davies (deledrius@gmail.com)
  * Requires libHSPlasma and PyHSPlasma (https://github.com/H-uru/libhsplasma)
  Usage:
    ./prp_as_text.py pagename.prp
"""

from hashlib import sha256 as hashFunc
import sys
from textwrap import indent

try:
    import PyHSPlasma
except ImportError as e:
    print("Required module PyHSPlasma cannot be found.", file=sys.stderr)
    sys.exit(1)


## Create our Resource Manager
plResMgr = PyHSPlasma.plResManager(preserveObjIDs=True)
assert plResMgr.preserveObjIDs, "shit"

## These types should not actually be diffed by PRC due to their complexity
pHashClasses = (
    PyHSPlasma.plDrawableSpans,
    PyHSPlasma.plGenericPhysical,
    #PyHSPlasma.plMipmap,
    PyHSPlasma.plSharedMesh,
)

## These classes should never be hashed - because they are subclasses of the above but
## need to be visualized for reasons.
pNoHashClasses = (PyHSPlasma.plDynamicTextMap,)

def main(page):
    # Python tries to be "helpful" on Windows by converting \n to \r\n.
    # Therefore we must change the mode of stdout.
    if sys.platform == "win32":
        import os, msvcrt
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    version = PyHSPlasma.pvMoul
    plResMgr.setVer(version)

    pageInfo = plResMgr.ReadPage(page)
    pageLoc = pageInfo.location

    classNameFunc = PyHSPlasma.plFactory.ClassName
    ramStream = PyHSPlasma.hsRAMStream

    for pTypeId in sorted(plResMgr.getTypes(pageLoc)):
        print(f"Type: {classNameFunc(pTypeId)}")

        for key in sorted(plResMgr.getKeys(pageLoc, pTypeId)):
            pKeyedObj = key.object
            if isinstance(pKeyedObj, pHashClasses) and not isinstance(pKeyedObj, pNoHashClasses):
                ram = ramStream(version)
                pKeyedObj.write(ram, plResMgr)
                h = hashFunc(ram.buffer)
                value = h.hexdigest()
            elif pKeyedObj is not None:
                value = pKeyedObj.toPrc(PyHSPlasma.pfPrcHelper.kExcludeTextureData)
            else:
                value = "NULL"

            print(f"\t{key.name} : {key}".replace("\r\n", "\n"))
            print(indent(value, "\t\t"))

if __name__ == '__main__':
    main(sys.argv[1])

    """
    # temp hackage for timing...
    import timeit
    from contextlib import redirect_stdout
    page = "G:\\Plasma\\Games\\MOULa\\dat\\city_District_Ferry.prp"

    # new code first...
    with open(os.devnull, "w") as f, redirect_stdout(f):
        result = timeit.timeit("main(page)", number=10, globals=locals())
    print(f"New Method: {result}")

    # old method
    pHashClasses = tuple()
    with open(os.devnull, "w") as f, redirect_stdout(f):
        result = timeit.timeit("main(page)", number=10, globals=locals())
    print(f"Old Method {result}")
    """

