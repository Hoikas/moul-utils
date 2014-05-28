#    PyPlasMOUL
#    Copyright (C) 2014  Adam Johnson
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
import struct
import sys

if sys.version_info[0] > 2:
    xrange = range


class uoid:
    location = (0, 0)
    class_type = 0x8000
    name = None

    def __eq__(self, rhs):
        if self.location == rhs.location:
            if self.class_type == rhs.class_type:
                if self.name == rhs.name:
                    return True
        return False

    def read(self, s):
        contents = s.readu8()
        self.location = s.read_location()

        # load mask
        if contents & 0x02:
            s.readu8()

        self.class_type = s.readu16()
        s.readu32() # object ID -- we don't give a rat's
        self.name = s.read_safe_string()

        # clone IDs
        if contents & 0x01:
            s.readu16() # clone ID
            s.readu16() # garbage
            s.readu32() # clone player ID


class _stream:
    def __init__(self, file):
        self._file = file

    def close(self):
        self._file.close()

    def read_location(self):
        #self._file.read(6) # seqnum (32) + flags (16)
        num = self.readu32()
        flags = self.readu16()

        if num & 0x80000000:
            num -= 0xFF000001
            prefix = num >> 16
            suffix = num - (prefix << 16)
            prefix *= -1
        else:
            num -= 33
            prefix = num >> 16
            suffix = num - (prefix << 16)
        return (prefix, suffix)

    def read_safe_string(self):
        _chars = self.readu16()
        if (_chars & 0xF000) == 0:
            self._file.read(2) # old style 32-bit count
        _chars &= ~0xF000
        if not _chars:
            return ""

        _buf = bytearray(self._file.read(_chars))
        if _buf[0] & 0x80:
            for i in xrange(_chars):
                _buf[i] = ~_buf[i] & 0xFF
        return _buf.decode("latin_1")

    def readu8(self):
        return int(struct.unpack("<B", self._file.read(1))[0])

    def readu16(self):
        return int(struct.unpack("<H", self._file.read(2))[0])

    def readu32(self):
        return int(struct.unpack("<I", self._file.read(4))[0])

    def read_uoid(self):
        if self.readu8():
            u = uoid()
            u.read(self)
            return u
        return None

    def set_position(self, pos):
        self._file.seek(pos, 0)


class key(uoid):
    uoid = None
    pos = None
    length = -1

    def read(self, s):
        self.uoid = uoid()
        self.uoid.read(s)
        self.pos = s.readu32()
        self.length = s.readu32()


class hsKeyedObject:
    class_type = 0x0002

    def read(self, s):
        self.uoid = s.read_uoid()
        assert self.uoid


class plSoundBuffer(hsKeyedObject):
    class_type = 0x0029

    IS_EXTERNAL = 0x01
    ALWAYS_EXTERNAL = 0x02
    ONLY_LEFT_CHANNEL = 0x04
    ONLY_RIGHT_CHANNEL = 0x08
    STREAM_COMPRESSED = 0x10

    @property
    def has_ogg_file(self):
        return bool(self.flags & plSoundBuffer.IS_EXTERNAL)

    @property
    def split_channel(self):
        if self.flags & plSoundBuffer.ONLY_LEFT_CHANNEL:
            return True
        elif self.flags & plSoundBuffer.ONLY_RIGHT_CHANNEL:
            return True
        else:
            return False

    @property
    def stream(self):
        return bool(self.flags & plSoundBuffer.STREAM_COMPRESSED)

    def read(self, s):
        hsKeyedObject.read(self, s)

        self.flags = s.readu32()
        self.data_length = s.readu32()
        self.file_name = s.read_safe_string()

        self.format_tag = s.readu16()
        self.channels = s.readu16()
        self.samples_per_sec = s.readu32()
        self.avg_bytes_per_sec = s.readu32()
        self.block_align = s.readu16()
        self.bits_per_sample = s.readu16()


# all plasma classes -- leave out ABCs to save time.
_pClasses = (plSoundBuffer,)


class page:
    def __init__(self, fn):
        self._stream = _stream(open(fn, "rb"))

    def __enter__(self):
        self._read_header()
        self._read_keyring()
        return self

    def __exit__(self, type, value, tb):
        self._stream.close()

    def __str__(self):
        return "[AGE: {}] [PAGE: {}] [LOC: {}]".format(self._age, self._page, self._location)

    def _read_header(self):
        s = self._stream # lazy

        assert s.readu32() == 6 # PRP Version
        self._location = s.read_location()
        self._age = s.read_safe_string()
        self._page = s.read_safe_string()
        self._version = s.readu16()
        s.readu32() # checksum
        s.readu32() # data start
        self._index_pos = s.readu32()

    def _read_keyring(self):
        s = self._stream # lazy
        s.set_position(self._index_pos)

        self._keyring = {}

        types = s.readu32()
        for i in xrange(types):
            pClass = s.readu16()
            s.readu32() # key list length (in bytes) -- garbage
            s.readu8() # nonsense
            numKeys = s.readu32()

            self._keyring[pClass] = [None] * numKeys
            for j in xrange(numKeys):
                self._keyring[pClass][j] = key()
                self._keyring[pClass][j].read(s)

    def get_keys(self, pClass):
        try:
            return tuple(self._keyring[pClass])
        except LookupError:
            return tuple()

    def get_object(self, key):
        s = self._stream
        assert key.pos
        s.set_position(key.pos)

        # pCre idx
        pClass = s.readu16()
        assert pClass == key.uoid.class_type

        for i in _pClasses:
            if i.class_type == pClass:
                obj = i()
                break
        else:
            raise RuntimeError("need to implement 0x{}".format(pClass, "04x"))

        obj.read(s)
        return obj

# Test code
if __name__ == "__main__":
    with page("GuildPub-Writers_District_Pub.prp") as prp:
        print(str(prp), end="\n\n")
        print("Sound Buffers:")
        for key in prp.get_keys(plSoundBuffer.class_type):
            sfx = prp.get_object(key)
            print("[OBJ: {}] [FILE: {}]".format(key.uoid.name, sfx.file_name))