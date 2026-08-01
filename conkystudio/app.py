"""QApplication bootstrap -- applies Griffin Dark once, globally, at startup."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from conkystudio.theme import build_qss
import conkystudio.nodes  # noqa: F401 -- populates the node registry as a side effect
from conkystudio.ui.main_window import MainWindow


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName("Conky Studio")
    app.setStyleSheet(build_qss())
    app.setStyle("Fusion")  # base platform style Griffin Dark's QSS is layered over

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
