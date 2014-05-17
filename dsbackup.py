#    DirtSand Backup
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
import argparse
from datetime import date
from ftplib import FTP
import gzip
import os
import subprocess
import sys

parser = argparse.ArgumentParser(description="DirtSand Backup")
parser.add_argument("-n", "--database-name", help="Postgres DB Name", default="dirtsand")
parser.add_argument("-f", "--ftp-host", help="FTP Hostname")
parser.add_argument("-u", "--ftp-user", help="FTP Username")
parser.add_argument("-p", "--ftp-password", help="FTP Password")
parser.add_argument("-d", "--ftp-directory", help="Directory to upload to", default="backups/gehn_vault")

if __name__ == "__main__":
    _args = parser.parse_args()

    fn = "{}.sql".format(date.today().isoformat())
    print("Dumping database '{}' to '{}'...".format(_args.database_name, fn), end="")
    with open(fn, "w") as out:
        cmd = "pg_dump --no-password {}".format(_args.database_name)
        subprocess.check_call(cmd, stdout=out, shell=True)
    print(" Done!")

    # gzip result
    gz_fn = "{}.gz".format(fn)
    print("Compressing to '{}'".format(gz_fn), end="")

    with open(gz_fn, "wb") as handle:
        with gzip.GzipFile(fn, "wb", fileobj=handle) as gz:
            with open(fn, "rb") as infile:
                HAX = 1024 * 1024 * 5 # proc 5mb at once
                while True:
                    data = infile.read(HAX)
                    if not data:
                        break
                    gz.write(data)
                    print(".", end="")
                    sys.stdout.flush()
    os.unlink(fn)
    print(" Done!")

    # FTP that bad boy...
    if not _args.ftp_host:
        print("WARNING: Not uploading to remote server...")
        sys.exit()

    ftp = FTP(_args.ftp_host)
    ftp.login(_args.ftp_user, _args.ftp_password)
    ftp.cwd(_args.ftp_directory)

    hack = 0 # don't flood the console
    def write_dot(wtf):
        global hack

        hack += 1
        if hack % 20 == 0:
            print(".", end="")
            sys.stdout.flush()

    print("Uploading '{}' to '{}'".format(gz_fn, _args.ftp_host), end="")
    with open(gz_fn, "rb") as infile:
        ftp.storbinary("STOR {}".format(gz_fn), infile, callback=write_dot)
    print(" Done!")
    ftp.quit()

