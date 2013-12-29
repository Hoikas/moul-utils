/*    Uru Patcher Event
 *    Copyright (C) 2013  Adam Johnson
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
 *
 *    You should have received a copy of the GNU General Public License
 *   along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

namespace UruPatcherEvent
{
    class Program
    {
        static void Main(string[] args)
        {
            string clientExe = "UruExplorer.exe";
            if (args.Length > 0)
                clientExe = args[1];
            IntPtr handle = CreateEvent(IntPtr.Zero, true, false, "UruPatcherEvent");
            Process p = new Process();
            p.StartInfo.FileName = clientExe;
            p.Start();
            p.WaitForInputIdle();
            Thread.Sleep(1000);
            CloseHandle(handle);
        }

        [DllImport("kernel32.dll")]
        static extern IntPtr CreateEvent(IntPtr lpEventAttributes, bool bManualReset, bool bInitialState, string lpName);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        static extern bool CloseHandle(IntPtr hObject);
    }
}
