#    PRP Merger
#    Copyright (C) 2017  Adam Johnson
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

import argparse
import os
import pathlib
from PyHSPlasma import *

parser = argparse.ArgumentParser(prog="PRP Merger",
                                 description="""A simple tool that allows one to merge many PRPs
                                                into a single output PRP. Originally written by Adam
                                                Johnson to merge clothing updates from MOULa into a
                                                single page for Gehn Shard updates.""")
parser.add_argument("-p", "--prefix", help="Sequence prefix of merged PRP")
parser.add_argument("-s", "--suffix", help="Sequence suffix of merged PRP")
parser.add_argument("-v", "--version", help="Plasma Version of final PRP",
                    choices=["pvMoul", "pvPots", "pvPrime"], default="pvMoul")
parser.add_argument("output", help="Path of merged PRP")
parser.add_argument("source", help="Path of source PRP(s) to merge", nargs=argparse.REMAINDER)

def _merge_page(mgr, destination, source):
    print("Reading Source PRP: {}...".format(pathlib.Path(source).name))
    source_prp = mgr.ReadPage(source)
    print("** Orignial Location: {};{}".format(source_prp.location.prefix, source_prp.location.page))
    print("** New Location: {};{}".format(destination.prefix, destination.page))
    mgr.ChangeLocation(source_prp.location, destination)

def merge_pages(output, sources, version, prefix=None, suffix=None):
    output_path = pathlib.Path(output)
    output_exists = output_path.exists()
    if not output_exists:
        if prefix is None or suffix is None:
            print("'{}' does not exist, ergo, you MUST provide the sequence prefix and suffix".format(output))
            return

    # Prep output page
    mgr = plResManager()
    if output_exists:
        print("Reading Output PRP: '{}'".format(output_path.name))
        dest_prp = mgr.ReadPage(output)
        if prefix is not None:
            assert dest_prp.location.prefix == prefix
        if suffix is not None:
            assert dest_prp.location.page == suffix
    else:
        parent_dir = output_path.parent
        if not pathlib.Path(parent_dir).exists():
            print("Creating Directories: '{}'".format(parent_dir))
            os.makedirs(parent_dir)

        print("Creating Output PRP: '{}'".format(output_path.name))
        dest_loc = plLocation(version)
        dest_loc.prefix = int(prefix)
        dest_loc.page = int(suffix)
        dest_prp = plPageInfo()
        dest_prp.age, dest_prp.page = output_path.stem.split("_District_", 2)
        dest_prp.location = dest_loc
        mgr.AddPage(dest_prp)

    # Move
    for i in sources:
        _merge_page(mgr, dest_prp.location, i)

    # Write out destination
    print("Flushing Output PRP: '{}'".format(output_path.name))
    mgr.WritePage(output, dest_prp)


if __name__ == "__main__":
    args = parser.parse_args()
    print("Starting PRP Merger...", end="\n\n")
    print(repr(args.source))
    merge_pages(args.output, args.source, globals()[args.version], args.prefix, args.suffix)
