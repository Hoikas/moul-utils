#    CWE Manifest Generator
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
import gzip
import hashlib
import os, os.path
import plasmoul
from PyHSPlasma import *
import shutil
import tempfile

# Define the argument parser (yay for batteries included!)
parser = argparse.ArgumentParser(description="CyanWorlds.com Engine Manifest Generator")
parser.add_argument("-b", "--blacklist", help="A list of files to blacklist from redistributing")
parser.add_argument("-d", "--destination", help="Destination for generated FileSrv",
                    default="/home/dirtsand/server/FileSrv")
parser.add_argument("-k", "--droid-key", help="notthedroids key",
                    default="31415926535897932384626433832795")
parser.add_argument("-s", "--source", help="Reference install to build FileSrv from",
                    default="/home/dirtsand/reference_build")

# Manifest options are special
_manifest = parser.add_argument_group()
_manifest.add_argument("-i", "--file-preloader", help="Generate a SecurePreloader.mfs file for H'uru clients",
                        action="store_true")
_manifest.add_argument("-l", "--auth-preloader", help="Generate legacy auth download lists",
                       action="store_true")
_manifest.add_argument("-c", "--client-manifests", help="Generate client manifests",
                       action="store_true")
_age = _manifest.add_mutually_exclusive_group()
_age.add_argument("-a", "--age", help="Generate a manifest for a specific age")
_age.add_argument("--no-ages", help="Don't generate any age manifests", action="store_true")

# final args
_args = None
_droid_key = []

# flags
NONE = 0
OGG_SPLIT_CHANNEL = 1
OGG_STREAM = 2
OGG_STEREO = 4
ZIPPED = 8
REDIST_UPDATE = 16
DELETED = 32

# some helpers
DONT_COMPRESS = {".age", ".csv", ".fni", ".ini", ".ogg", ".sdl"}
CLIENT_PREFIXES = {"pl", "uru"}
CLIENT_EXTENSIONS = {".exe"}

class ManifestLine:
    compress_size = 0

    def __str__(self):
        line = "{},{},{},{},{},{},{}".format(self.file.replace('\\', '/'), self.dest, self.base_md5,
                                             self.compress_md5, self.base_size, self.compress_size, self.flag)
        return line



# global dict of processed files. prevents us from doing a lot of dupe work!
_processed = {}

# hacks, just hacks...
_deadPRPs = set()

def _blacklist(fn):
    def nuke(fn):
        if os.path.isfile(fn):
            os.unlink(fn)

    with open(fn, "r") as list:
        for line in list:
            if not line or line.startswith('#') or line.startswith(';') or line.startswith("//"):
                # this is a comment, obviously...
                continue

            abspath = os.path.join(_args.destination, line.strip())
            nuke(abspath)
            nuke(abspath + ".gz")

def _encrypt_file(abspath, enc, key=None):
    if plEncryptedStream.IsFileEncrypted(abspath):
        # if it's already encrypted, I assume you know WTF you're doing...
        return (abspath, False)

    outfile = os.path.join(tempfile.gettempdir(), os.path.split(abspath)[1])
    with open(abspath, "rb") as infile:
        data = infile.read() # largest is Python.pak at ~5mb...
        stream = plEncryptedStream()
        stream.open(outfile, fmCreate, enc)
        if key is not None:
            stream.setKey(key)
        stream.write(data)
        stream.close()
    return (outfile, True)

def _do_file(file, subfolder=None, flag=NONE):
    global _processed
    if file in _processed:
        return str(_processed[file]) + "\n"

    # Does this file fucking exist?!?!
    abspath = os.path.join(_args.source, file)
    if not os.path.isfile(abspath):
        print("    WARNING: '%s' does not exist! Skipping..." % file)
        return None

    # Init final path here -- note, might change later due to compression...
    fn = os.path.split(file)[1]
    if subfolder is not None:
        destpath = os.path.join(_args.destination, subfolder, fn)
    else:
        destpath = os.path.join(_args.destination, fn)

    # Get some basic swhizzle for the manifest string.
    line = ManifestLine()
    if flag & DELETED:
        line.base_size = 0
    else:
        line.base_size = os.lstat(abspath).st_size

    # Zero byte files are fucking deleted! (don't fucking compress it)
    if line.base_size == 0:
        _zeroMD5 = hashlib.md5()
        line.base_md5 = _zeroMD5.hexdigest()
        line.compress_md5 = _zeroMD5.hexdigest()
        flag |= DELETED
    else:
        line.base_md5 = _do_md5(abspath)

        # Do we need to encrypt the file?
        ext = os.path.splitext(file)[1].lower()
        if ext in {".age", ".fni", ".csv"}:
            abspath, isTemp = _encrypt_file(abspath, plEncryptedStream.kEncXtea)
        elif ext in {".pak", ".sdl"}:
            abspath, isTemp = _encrypt_file(abspath, plEncryptedStream.kEncDroid, _droid_key)
        else:
            isTemp = False

        # So, if this is an execuatable file, and it doesn't look like a game executable,
        # Then it is PROBABLY a redist update. Let's flag those here.
        if ext in CLIENT_EXTENSIONS:
            for prefix in CLIENT_PREFIXES:
                if file.lower().startswith(prefix):
                    break
            else:
                flag |= REDIST_UPDATE

        # Ensure output directory exists
        outdir = os.path.split(destpath)[0]
        if not os.path.isdir(outdir):
            os.makedirs(outdir)

        # Okay, let's see if this is something we can compress...
        compressed = ext not in DONT_COMPRESS
        if compressed:
            destpath += ".gz"
            _do_gzip(abspath, destpath)
            flag |= ZIPPED

            line.compress_md5 = _do_md5(destpath)
            line.compress_size = os.lstat(destpath).st_size
        else:
            shutil.copy(abspath, destpath)
            line.compress_md5 = hashlib.md5().hexdigest()

        # If we created a temporary file, nuke it.
        if isTemp:
            os.unlink(abspath)

    # generate the manifest line
    line.file = file
    line.dest = os.path.relpath(destpath, _args.destination)
    line.flag = flag
    _processed[file] = line
    return str(line) + "\n"

def _do_file_action(fn, call):
    HAX = 1024 * 1024 * 5
    with open(fn, "rb") as handle:
        while True:
            data = handle.read(HAX)
            if not data:
                break
            call(data)

def _do_gzip(infile, outfile):
    with open(outfile, "wb") as handle:
        # We do this so we don't leak information about the build environment via FileSrv
        filename = os.path.split(outfile)[1]
        with gzip.GzipFile(filename, "wb", fileobj=handle) as gz:
            with open(infile, "rb") as inhandle:
                gz.writelines(inhandle)

def _do_md5(fn):
    md5 = hashlib.md5()
    _do_file_action(fn, md5.update)
    return md5.hexdigest()

def _process_dir(items, src, dst, indir=".", outdir=".", ext=None, require_ext=False):
    for item in os.listdir(os.path.join(src, indir)):
        abspath_in = os.path.join(src, indir, item)
        if os.path.isdir(abspath_in):
            continue

        # Make sure extensions are what we expect
        if ext is not None:
            this_ext = os.path.splitext(item)[1].lower()
            if (this_ext in ext) ^ require_ext:
                continue

        # Process file
        if indir != ".":
            relpath = os.path.join(indir, item)
        else:
            relpath = item
        items[relpath] = _do_file(relpath, outdir)



def _make_age_manifest(agefile):
    ageName = os.path.splitext(agefile)[0]
    mfs_path = os.path.join(_args.destination, "{}.mfs".format(ageName))

    with open(mfs_path, "w") as mfs:
        for i in {agefile, "{}.fni".format(ageName), "{}.csv".format(ageName)}:
            abspath = os.path.join(_args.source, "dat", i)
            if os.path.isfile(abspath):
                mfs.write(_do_file(os.path.join("dat", i), "GameBase"))

        # Read in age file and get the PRPs...
        res = plResManager()
        res.setVer(pvMoul)
        info = res.ReadAge(os.path.join(_args.source, "dat", agefile), False)
        
        # Grab the pages
        for i in range(info.getNumCommonPages(pvMoul)):
            prp = os.path.join("dat", info.getCommonPageFilename(i, pvMoul))
            line = _do_file(prp, "GameData")
            if line:
                mfs.write(line)
        
        for i in range(info.getNumPages()):
            prp = os.path.join("dat", info.getPageFilename(i, pvMoul))
            line = _do_file(prp, "GameData")
            if line:
                mfs.write(line)
        
        # Now, we do the fun part and enumerate the sfx
        for i in range(info.getNumPages()):
            path = os.path.join(_args.source, "dat", info.getPageFilename(i, pvMoul))
            if not os.path.exists(path):
                continue
            with plasmoul.page(path) as prp:
                for i in prp.get_keys(plasmoul.plSoundBuffer.class_type):
                    sbuf = prp.get_object(i)

                    flags = NONE
                    if sbuf.split_channel:
                        flags |= OGG_SPLIT_CHANNEL
                    else:
                        flags |= OGG_STEREO
                    if sbuf.stream:
                        flags |= OGG_STREAM
                    line = _do_file(os.path.join("sfx", sbuf.file_name), "GameAudio", flags)
                    if line:
                        mfs.write(line)

        # Special Case: Deleted PRPs are generally not in age files.
        prp_prefix = os.path.join("dat", "%s_District_" % ageName)
        for i in _deadPRPs:
            if i.startswith(prp_prefix):
                mfs.write(_do_file(i, "GameData", DELETED))

def _make_auth_lists():
    raise NotImplementedError("too lazy to support auth lists")

def _make_client_manifest(preloader):
    def generate_manifest(dst, name, items, exe_blacklist=None):
        abspath = os.path.join(dst, name)
        with open(abspath, "w") as mfs:
            for item in items:
                fn, ext = os.path.splitext(item)
                fn = fn.lower()
                ext = ext.lower()

                if ext in CLIENT_EXTENSIONS:
                    if exe_blacklist is not None and fn.startswith(exe_blacklist):
                        continue
                mfs.write(items[item])

    def generate_patcher_manifest(src, dst, name, launcher_exe):
        abspath = os.path.join(dst, name)
        with open(abspath, "w") as mfs:
            for item in os.listdir(src):
                abspath_in = os.path.join(src, item)
                if os.path.isdir(abspath_in):
                    continue

                fn, ext = os.path.splitext(item)
                if ext.lower() in CLIENT_EXTENSIONS:
                    fn = fn.lower()

                    bad_client = False
                    for i in CLIENT_PREFIXES:
                        if fn.startswith(i):
                            bad_client = (fn != launcher_exe)
                            break
                    if bad_client:
                        continue
                elif ext != ".ini":
                    continue

                mfs.write(_do_file(item, "GameClient"))

    source = _args.source
    destination = _args.destination

    # Now, we make a cache of the CORE client files.
    items = {}
    if preloader:
        _process_dir(items, source, destination, "Python", "ClientPreload", {".pak"}, True)
        _process_dir(items, source, destination, "SDL", "ClientPreload", {".sdl"}, True)
    _process_dir(items, source, destination, outdir="Client",
                 ext={".lnk", ".pdb", ".prd"}, require_ext=False)
    _process_dir(items, source, destination, "avi", "GameVideos", {".avi", ".bik", ".oggv", ".webm"}, True)
    _process_dir(items, source, destination, "dat", "GameBase", {".age", ".loc", ".p2f"}, True)

    # Now, let's spew out our not-image manifests...
    generate_manifest(destination, "ThinExternal.mfs", items, "pl")
    generate_manifest(destination, "ThinInternal.mfs", items, "uru")

    # Hacky Patcher Manifests...
    generate_patcher_manifest(source, destination, "ExternalPatcher.mfs", "urulauncher")
    generate_patcher_manifest(source, destination, "InternalPatcher.mfs", "plurulauncher")

def _make_preloader_manifest():
    src = _args.source
    dst = _args.destination

    items = {}
    _process_dir(items, src, dst, "Python", "ClientPreload", {".pak"}, True)
    _process_dir(items, src, dst, "SDL", "ClientPreload", {".sdl"}, True)

    abspath = os.path.join(dst, "SecurePreloader.mfs")
    with open(abspath, "w") as mfs:
        for i in items.values():
            mfs.write(i)

def _update_image_manifests():
    def barf_image(name, items, skip_exe_prefix):
        with open(os.path.join(_args.destination, name), "w") as mfs:
            for name, line in items.items():
                fn, ext = os.path.splitext(name)
                if ext.lower() in CLIENT_EXTENSIONS and fn.lower().startswith(skip_exe_prefix):
                    continue
                mfs.write(line)

    def load_items(fn, items):
        with open(os.path.join(_args.destination, fn), "r") as mfs:
            for line in mfs:
                item_name = line.split(',', 1)[0]
                items[item_name] = line

    # We can't assume this is a full build, so we need to test everything in our manifests
    items = {}
    for mfs in os.listdir(_args.destination):
        if not mfs.endswith(".mfs"):
            continue
        load_items(mfs, items)
    barf_image("Internal.mfs", items, "uru")
    barf_image("External.mfs", items, "pl")


def make_manifests(files):
    if not os.path.isdir(_args.destination):
        os.makedirs(_args.destination)

    while files:
        mfs = files.pop()
        if mfs.startswith("__"):
            if mfs.startswith("__client"):
                preloader = mfs.find("with_preloader") != -1
                if preloader:
                    print("Generating CLIENT manifests w/ preloader...")
                else:
                    print("Generating CLIENT manifests w/o preloader...")

                _make_client_manifest(preloader)
            elif mfs == "__auth_lists__":
                print("Generating AUTH lists...")
                _make_auth_lists()
            elif mfs == "__file_preloader__":
                print("Generating SECURE PRELOADER manifest...")
                _make_preloader_manifest()
        else:
            print("Generating AGE manifest for '%s'..." % mfs)
            _make_age_manifest(mfs)

    # And finally... We always have to touch our(selves) image manifests
    print("Updating IMAGE manifests...")
    _update_image_manifests()


def _make_droid_key():
    def buf_to_int(str):
        val = 0
        val += (int(str[0], 16) * 0x10000000) + (int(str[1], 16) * 0x01000000)
        val += (int(str[2], 16) * 0x00100000) + (int(str[3], 16) * 0x00010000)
        val += (int(str[4], 16) * 0x00001000) + (int(str[5], 16) * 0x00000100)
        val += (int(str[6], 16) * 0x00000010) + (int(str[7], 16) * 0x00000001)
        return val
    global _droid_key

    key = _args.droid_key
    _droid_key = [buf_to_int(key[0:8]), buf_to_int(key[8:16]),
                  buf_to_int(key[16:24]), buf_to_int(key[24:32])]

def _find_dead_prps(source):
    global _deadPRPs
    for item in os.listdir(os.path.join(source, "dat")):
        ext = os.path.splitext(item)[1].lower()
        if ext != ".prp":
            continue
        abspath = os.path.join(source, "dat", item)
        if os.lstat(abspath).st_size == 0:
            _deadPRPs.add(os.path.join("dat", item))

if __name__ == "__main__":
    _args = parser.parse_args()
    _make_droid_key()

    _use_defaults = (not _args.file_preloader and not _args.auth_preloader and not _args.client_manifests)
    _manifests = []

    if _use_defaults:
        _manifests = ["__client_with_preloader__", "__file_preloader__"]
    else:
        # Ordering is important with the client manifest.
        if _args.client_manifests:
            if _args.file_preloader:
                _manifests.append("__client_with_preloader__")
            else:
                _manifests.append("__client__")
        if _args.auth_preloader:
            _manifests.append("__auth_lists__")
        if _args.file_preloader:
            _manifests.append("__file_preloader__")

    # Deleted PRP files generally do not appear in .age files, so we will be unable to deal with them
    # the normal way. So, we need this hack here to check every single PRP to see if it's deleted...
    # We won't worry about deleted oggs. Too much work to even think about predicting that!
    if not _args.no_ages:
        _find_dead_prps(_args.source)

    if _args.age:
        agefile = _args.age
        if not agefile.endswith(".age"):
            agefile += ".age"
        _manifests.append(agefile)
    elif not _args.no_ages:
        # add all the ages to the list
        agedir = os.path.join(_args.source, "dat")
        for i in os.listdir(agedir):
            if i.endswith(".age"):
                _manifests.append(i)
    make_manifests(_manifests)

    # Now to abide by Cyan's "rules"
    if _args.blacklist:
        print("Blacklisting Cyan content...")
        _blacklist(_args.blacklist)
