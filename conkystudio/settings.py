"""Tiny persistent-settings helper (QSettings). Keys are namespaced like "deps/suppress_popup"."""
from __future__ import annotations


def _s():
    from PyQt6.QtCore import QSettings
    return QSettings("ConkyStudio", "ConkyStudio")


def get_bool(key: str, default: bool = False) -> bool:
    v = _s().value(key, default)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")


def set_bool(key: str, value: bool) -> None:
    s = _s(); s.setValue(key, bool(value)); s.sync()


def get_str(key: str, default: str = "") -> str:
    return str(_s().value(key, default) or "")


def set_str(key: str, value: str) -> None:
    s = _s(); s.setValue(key, value); s.sync()
