from __future__ import annotations

import getpass
import ctypes
import os


def get_windows_username() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USERNAME", "user")


def is_admin_user() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
