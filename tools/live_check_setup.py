"""The setup program, update, uninstall and signing (group AK), and the installer on a shared server (group AY).

Run by ``live_check.py``; see ``live_common.py`` for the rules every check keeps.
Nothing here is measured: every row installs, updates or removes Heron on a Windows
user account, which is the one thing the runner must never do to the PC it runs on
(it works in scratch drawings, D-118), and most need a second user, a second PC, a
second release, a click in a Windows or AutoCAD box, or what Windows says on screen.
Each row has its reason. A result already written by hand (AK12, AK14, AK15 and AK16
hold PASS) is never overwritten by these reasons.
"""

from __future__ import annotations

from live_common import Check

CHECKS: tuple[Check, ...] = ()

_INSTALLS = "runs the setup program, which installs, updates or removes Heron on this Windows user"
_WIZARD = "the setup's pages and the Windows boxes are read on screen"

BY_EYE: dict[str, str] = {
    "AK1": "needs a clean Windows user that is not an administrator, and " + _INSTALLS + "; " + _WIZARD,
    "AK2": _INSTALLS + ", and needs AutoCAD opened and closed by hand between the runs",
    "AK3": _INSTALLS + ", and needs Claude Desktop open and connected, then a dev server only",
    "AK4": _INSTALLS + " over an older version put in by the zip's Install.bat",
    "AK5": "needs a second release built with the setup, and " + _INSTALLS,
    "AK6": "removes Heron from Settings > Apps, first with AutoCAD open, then closed",
    "AK7": "needs the setup install of AK1 done first, then the zip's Uninstall.bat run by hand",
    "AK8": "opens the Start menu entry's window, which is read on screen",
    "AK9": "needs the setup downloaded in Edge, and what SmartScreen and the company antivirus show is written down",
    "AK10": "what AutoCAD's security box for the unsigned plug-in says is written down, with SECURELOAD read at its command line",
    "AK11": "needs AutoCAD restarted, then a newer version installed over it, and the box (or none) written down",
    "AK12": "runs the release's setup quietly on a Windows user with a source-installed plug-in, and compares files with the zip",
    "AK13": "needs a PC where Claude is only the desktop app, and the setup's last page read",
    "AK14": "needs AutoCAD started after the setup and the add-in log read",
    "AK15": "runs Install.ps1 from a terminal outside the Claude app on the owner's PC, and reads what it would do",
    "AK16": "runs Install.ps1 for real on the owner's PC with his yes, and starts new chats in two folders",
    "AY1": "needs a shared Windows server with a colleague's AutoCAD open in their own session, and the setup, Install.bat and Uninstall run on it",
    "AY2": "needs the same shared server, your own AutoCAD open and your Remote Desktop session disconnected and signed in again",
    "AY3": "needs a release's checksums.txt and files copied to a Linux or macOS machine, which is not this PC",
}
