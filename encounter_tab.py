#!/usr/bin/env python3
"""encounter_tab.py — EncounterTab widget and pencil icon helper."""

from PySide6.QtCore import Qt, QByteArray, QTimer, Signal
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

from adversary import AdversaryFormDialog, AdversaryPreviewPanel
from encounter_panel import EncounterPreviewPanel


_PENCIL_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
    b'<path fill="#cccccc" d="M12.854.146a.5.5 0 0 0-.707 0L10.5 1.793 14.207 5.5'
    b' l1.647-1.646a.5.5 0 0 0 0-.708zm.646 6.061L9.793 2.5 3.293 9H3.5a.5.5 0 0 1'
    b' .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.207'
    b'l6.5-6.5zm-7.468 7.468A.5.5 0 0 1 6 13.5V13h-.5a.5.5 0 0 1-.5-.5V12h-.5a.5.5'
    b' 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.5-.5V10h-.5a.499.499 0 0 1-.175-.032l-.179.178'
    b'a.5.5 0 0 0-.11.168l-2 5a.5.5 0 0 0 .65.65l5-2a.5.5 0 0 0 .168-.11l.178-.178z"/>'
    b'</svg>'
)


def _pencil_icon(size: int = 14) -> QIcon:
    renderer = QSvgRenderer(QByteArray(_PENCIL_SVG))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return QIcon(pm)


class EncounterTab(QWidget):
    """Self-contained encounter workspace: adversary preview + encounter panel in a splitter."""
    title_changed = Signal(str)

    def __init__(self, layout_mode: str = '3col', parent=None):
        super().__init__(parent)
        self._dirty = False
        self._saving = False
        self._loading = False
        self._save_path = ''
        self._initial_split_done = False

        self._adv_preview   = AdversaryPreviewPanel()
        self._preview_panel = EncounterPreviewPanel()
        self._form_dialog   = AdversaryFormDialog(self)

        # ── Encounter header (spans full width above both panels) ──
        header = QWidget()
        hdr = QGridLayout(header)
        hdr.setContentsMargins(4, 4, 4, 2)
        hdr.setSpacing(4)
        hdr.setColumnStretch(1, 1)

        hdr.addWidget(QLabel('Name:'), 0, 0)
        self._encounter_name = QLineEdit()
        hdr.addWidget(self._encounter_name, 0, 1)

        self._budget_btn = QPushButton('Click to configure budget')
        self._budget_btn.setFlat(True)
        self._budget_btn.setStyleSheet('text-align: left; padding-left: 2px;')
        self._budget_btn.setIcon(_pencil_icon())
        self._budget_btn.clicked.connect(self._preview_panel.configure_budget)
        budget_row = QHBoxLayout()
        budget_row.setContentsMargins(0, 0, 0, 0)
        budget_row.addWidget(self._budget_btn)
        budget_row.addStretch()
        hdr.addLayout(budget_row, 1, 1)

        # ── Splitter: adversary preview | encounter cards ──
        self._splitter = QSplitter(
            Qt.Orientation.Horizontal if layout_mode == '3col' else Qt.Orientation.Vertical
        )
        self._splitter.addWidget(self._adv_preview)
        self._splitter.addWidget(self._preview_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._splitter, 1)

        self._adv_preview.add_to_encounter.connect(self._preview_panel.add_entry)
        self._adv_preview.edit_requested.connect(self._open_form_for_preview)
        self._form_dialog.add_to_encounter.connect(self._preview_panel.add_entry)
        self._form_dialog.update_in_encounter.connect(self._preview_panel.update_entry)
        self._preview_panel.edit_requested.connect(self._open_form_for_edit)
        self._preview_panel.encounter_changed.connect(self._on_changed)
        self._encounter_name.textChanged.connect(self._on_name_changed)
        self._preview_panel.name_loaded.connect(self._encounter_name.setText)
        self._preview_panel.budget_config_changed.connect(self._budget_btn.setText)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_split_done:
            self._initial_split_done = True
            QTimer.singleShot(0, self._set_initial_split)

    def _set_initial_split(self) -> None:
        w = self._splitter.width()
        if w > 0:
            self._splitter.setSizes([w // 2, w // 2])

    def set_orientation(self, orientation: Qt.Orientation) -> None:
        self._splitter.setOrientation(orientation)

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def save_path(self) -> str:
        return self._save_path

    @property
    def adv_preview(self) -> AdversaryPreviewPanel:
        return self._adv_preview

    @property
    def form_dialog(self) -> AdversaryFormDialog:
        return self._form_dialog

    @property
    def preview_panel(self) -> EncounterPreviewPanel:
        return self._preview_panel

    def _open_form_for_preview(self, adv: dict) -> None:
        self._form_dialog.load(adv)
        self._form_dialog.exec()

    def _open_form_for_edit(self, adv: dict, count: int) -> None:
        self._form_dialog.load_for_edit(adv, count)
        self._form_dialog.exec()

    def _on_changed(self) -> None:
        if not self._saving and not self._loading:
            self._dirty = True
        self.title_changed.emit(self._tab_title())

    def _on_name_changed(self, name: str) -> None:
        self._preview_panel.set_encounter_name(name)
        self._on_changed()

    def load_encounter_state(self, data: dict) -> None:
        self._loading = True
        try:
            self._preview_panel.load_encounter_state(data)
        finally:
            self._loading = False

    def get_encounter_state(self) -> dict:
        return self._preview_panel.get_encounter_state()

    def _tab_title(self) -> str:
        name = self._preview_panel.encounter_name
        base = name if name else 'Untitled'
        return f'{base} (*)' if self._dirty else base

    def mark_saved(self, path: str, name: str = '') -> None:
        """Record that this tab has been saved to `path`; optionally set encounter name."""
        self._saving = True
        try:
            self._save_path = path
            if name:
                self._encounter_name.setText(name)
            self._dirty = False
        finally:
            self._saving = False
        self.title_changed.emit(self._tab_title())
