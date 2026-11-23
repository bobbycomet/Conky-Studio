"""UI translation: loads the Qt translation catalogs at startup.

Catalogs are conkystudio_<lang>.ts files in this directory (the source of
truth, kept in git). The AppImage build compiles them to .qm with lrelease;
.qm files are never committed. English is the source language, so a missing
catalog simply means English.

Language: the system locale (LANG / LC_MESSAGES / LANGUAGE), or forced with
CONKY_STUDIO_LANG=<code> (e.g. ru, de, pt_BR); CONKY_STUDIO_LANG=en turns
translation off.

Rules for UI code (one approach for every part of the app):
  * methods of QObject/QWidget subclasses:  self.tr("Text")
  * everything else (QGraphicsItems, module functions, dataclasses):
        QCoreApplication.translate("Context", "Text")
  * strings defined at module level: mark with QT_TRANSLATE_NOOP("Context", "Text")
    and translate where they are shown
  * node metadata (NodeSpec / PropertySpec) stays plain strings with no Qt;
    show it through node_text(), see tools/i18n_node_strings.py
  * no f-strings inside tr(): self.tr("Saved {0}").format(path)
Update the catalogs with conkystudio/tools/update_translations.sh.
"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator

I18N_DIR = Path(__file__).resolve().parent

_translators: list[QTranslator] = []


def install_translators(app) -> str:
    """Install the app + Qt translators for the current language.

    Returns the language actually loaded ("en" when nothing was loaded)."""
    forced = os.environ.get("CONKY_STUDIO_LANG", "").strip()
    if forced.lower() in ("en", "en_us", "c", "posix"):
        return "en"
    locale = QLocale(forced) if forced else QLocale.system()

    app_tr = QTranslator(app)
    if not app_tr.load(locale, "conkystudio", "_", str(I18N_DIR)):
        return "en"
    app.installTranslator(app_tr)
    _translators.append(app_tr)

    # Qt's own strings (standard dialog buttons, context menus of text fields).
    import PyQt6
    qt_dirs = (QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath),
               str(Path(PyQt6.__file__).resolve().parent / "Qt6" / "translations"))
    for qt_dir in qt_dirs:
        qt_tr = QTranslator(app)
        if qt_tr.load(locale, "qtbase", "_", qt_dir):
            app.installTranslator(qt_tr)
            _translators.append(qt_tr)
            break
    return locale.name()


def node_text(text: str) -> str:
    """Translate node metadata (label, description, help, group, subcategory,
    enum labels) at display time. Never use the result as a key or write it
    into a project -- the English text stays the identifier."""
    return QCoreApplication.translate("Nodes", text) if text else text
