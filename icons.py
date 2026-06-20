#!/usr/bin/env python3
"""icons.py — Lucide SVG icon helpers."""

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_COLOR = '#cccccc'

# ── Inner SVG path content (Lucide, 24x24 viewBox) ───────────────────────────

_P_CHEVRON_RIGHT    = '<path d="m9 18 6-6-6-6"/>'
_P_CHEVRON_DOWN     = '<path d="m6 9 6 6 6-6"/>'
_P_CHEVRON_UP       = '<path d="m18 15-6-6-6 6"/>'
_P_CHEVRONS_UP_DOWN = '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>'
_P_PENCIL = (
    '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83'
    'l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>'
    '<path d="m15 5 4 4"/>'
)
_P_SAVE = (
    '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/>'
    '<path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/>'
    '<path d="M7 3v4a1 1 0 0 0 1 1h7"/>'
)
_P_PRINTER = (
    '<path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>'
    '<path d="M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6"/>'
    '<rect x="6" y="14" width="12" height="8" rx="1"/>'
)
_P_FILE_PLUS = (
    '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706'
    'l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
    '<path d="M14 2v5a1 1 0 0 0 1 1h5"/>'
    '<path d="M9 15h6"/>'
    '<path d="M12 18v-6"/>'
)


# ── Core helpers ──────────────────────────────────────────────────────────────

def _icon(inner: str, size: int, stroke_width: float, color: str = _COLOR) -> QIcon:
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"'
        f' stroke="{color}" stroke-width="{stroke_width}"'
        f' stroke-linecap="round" stroke-linejoin="round">'
        f'{inner}</svg>'
    ).encode()
    renderer = QSvgRenderer(QByteArray(svg))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return QIcon(pm)


# ── Public icon constructors ──────────────────────────────────────────────────
# size / stroke_width defaults suit toolbar use; pass explicit values for
# smaller in-layout indicators (e.g. 16 / 3).

def chevron_right_icon(size: int = 16, stroke_width: float = 2.25) -> QIcon:
    return _icon(_P_CHEVRON_RIGHT,    size, stroke_width)

def chevron_down_icon(size: int = 16, stroke_width: float = 2.25) -> QIcon:
    return _icon(_P_CHEVRON_DOWN,     size, stroke_width)

def chevron_up_icon(size: int = 16, stroke_width: float = 2.25) -> QIcon:
    return _icon(_P_CHEVRON_UP,       size, stroke_width)

def chevrons_up_down_icon(size: int = 16, stroke_width: float = 2.25) -> QIcon:
    return _icon(_P_CHEVRONS_UP_DOWN, size, stroke_width)

def pencil_icon(size: int = 16, stroke_width: float = 2.25) -> QIcon:
    return _icon(_P_PENCIL,           size, stroke_width)

def save_icon(size: int = 20, stroke_width: float = 2) -> QIcon:
    return _icon(_P_SAVE,             size, stroke_width)

def printer_icon(size: int = 20, stroke_width: float = 2)-> QIcon:
    return _icon(_P_PRINTER,          size, stroke_width)

def file_plus_icon(size: int = 20, stroke_width: float = 2) -> QIcon:
    return _icon(_P_FILE_PLUS,        size, stroke_width)
