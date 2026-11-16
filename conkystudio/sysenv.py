"""Environment for running SYSTEM tools from inside the AppImage.

The AppImage's bootloader prepends its own library directory to LD_LIBRARY_PATH. That is
right for the app itself but wrong for system programs it launches: a C++ tool such as
`conky` then loads the bundle's older libstdc++ and fails ("GLIBCXX_3.4.32 not found"),
which looks like "Conky is not installed / unreadable". PyInstaller keeps the user's
original value in LD_LIBRARY_PATH_ORIG, so give children that (or nothing).
"""
from __future__ import annotations

import os


def system_env(base: dict | None = None) -> dict:
    env = dict(os.environ if base is None else base)
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    if orig:
        env["LD_LIBRARY_PATH"] = orig
    return env
