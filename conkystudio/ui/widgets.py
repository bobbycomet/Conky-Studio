"""Small reusable widgets shared across the Studio's property panel and elsewhere."""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QSlider, QDoubleSpinBox, QColorDialog, QSizePolicy
from PyQt6.QtGui import QColor
from PyQt6.QtCore import Qt, pyqtSignal

from conkystudio.theme import PALETTE


class ColorSwatchButton(QPushButton):
    """A small button showing the current colour as its fill; click opens
    QColorDialog. Emits colorChanged(hex_str) -- '#rrggbb'."""

    colorChanged = pyqtSignal(str)

    def __init__(self, initial_hex: str = "#FFFFFF", parent=None):
        super().__init__(parent)
        self._hex = initial_hex
        # Scope the stylesheet to this instance only -- an unscoped
        # "QPushButton { background: ... }" rule is inherited by every
        # push button inside QColorDialog when the dialog is parented
        # under this widget (or shares the cascade), which is why the
        # dialog's OK/Cancel buttons used to take the last picked colour.
        self.setObjectName("ColorSwatch")
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._apply_style()

    def _apply_style(self):
        self.setStyleSheet(
            f"#ColorSwatch {{ background-color: {self._hex}; border: 1px solid {PALETTE['border_strong']}; "
            f"border-radius: 4px; }}"
            f"#ColorSwatch:hover {{ border-color: {PALETTE['teal']}; }}"
        )

    def hex(self) -> str:
        return self._hex

    def set_hex(self, hex_str: str):
        self._hex = hex_str
        self._apply_style()

    def _pick(self):
        # Parent to the top-level window, not the swatch, so the dialog
        # does not sit under the swatch's stylesheet cascade.
        parent = self.window() if self.window() is not None else self
        color = QColorDialog.getColor(QColor(self._hex), parent, "Choose colour")
        if color.isValid():
            self._hex = color.name()
            self._apply_style()
            self.colorChanged.emit(self._hex)


class SliderSpin(QWidget):
    """A QSlider synced to a QDoubleSpinBox, for numeric properties that
    benefit from both quick dragging and precise typing. Emits
    valueChanged(float) once per settled change (not on every slider
    pixel, to avoid flooding live-preview rebuilds while dragging).

    Sized to actually shrink in a narrow dock rather than forcing one --
    the spinbox is narrower than it used to be and the slider is allowed
    to compress down to a small minimum instead of demanding its full
    natural width, which is what was pushing property-panel rows past
    the edge of the dock."""

    valueChanged = pyqtSignal(float)

    def __init__(self, minimum: float, maximum: float, step: float, value: float, decimals: int = 2, parent=None):
        super().__init__(parent)
        self._scale = max(1, round(1 / step)) if step < 1 else 1
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(int(minimum * self._scale))
        self.slider.setMaximum(int(maximum * self._scale))
        self.slider.setValue(int(value * self._scale))
        self.slider.setMinimumWidth(40)
        self.slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimals if step < 1 else 0)
        self.spin.setMinimum(minimum)
        self.spin.setMaximum(maximum)
        self.spin.setSingleStep(step)
        self.spin.setValue(value)
        self.spin.setFixedWidth(58)

        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)

        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)
        self.slider.sliderReleased.connect(lambda: self.valueChanged.emit(self.spin.value()))
        self._suppress = False

    def _on_slider(self, raw: int):
        if self._suppress:
            return
        self._suppress = True
        self.spin.setValue(raw / self._scale)
        self._suppress = False

    def _on_spin(self, val: float):
        if self._suppress:
            return
        self._suppress = True
        self.slider.setValue(int(val * self._scale))
        self._suppress = False
        self.valueChanged.emit(val)

    def value(self) -> float:
        return self.spin.value()

    def set_value(self, v: float):
        self.spin.setValue(v)
