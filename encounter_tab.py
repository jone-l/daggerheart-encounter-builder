#!/usr/bin/env python3
"""encounter_tab.py — EncounterTab widget and pencil icon helper."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from adversary import AdversaryFormDialog
from encounter_panel import EncounterPreviewPanel
from icons import pencil_icon


class EncounterTab(QWidget):
    """Encounter workspace: name/budget + encounter cards + form dialog for edits."""
    title_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dirty   = False
        self._saving  = False
        self._loading = False
        self._save_path = ''

        self._preview_panel = EncounterPreviewPanel()
        self._preview_panel.set_budget_icon(pencil_icon())
        self._form_dialog = AdversaryFormDialog(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._preview_panel)

        # Form dialog for editing encounter entries (opened from card's Edit button)
        self._preview_panel.edit_requested.connect(self._open_form_for_edit)
        self._form_dialog.update_in_encounter.connect(self._preview_panel.update_entry)
        self._form_dialog.save_to_custom.connect(self._relay_save_to_custom)
        self._form_dialog.save_as_new_custom.connect(self._relay_save_as_new_custom)
        self._preview_panel.encounter_changed.connect(self._on_changed)
        self._preview_panel.name_loaded.connect(self._on_name_loaded)

    # Relay save signals upward so MainWindow can connect to form_dialog
    save_to_custom     = Signal(dict, dict)
    save_as_new_custom = Signal(dict)

    def _relay_save_to_custom(self, orig: dict, new: dict) -> None:
        self.save_to_custom.emit(orig, new)

    def _relay_save_as_new_custom(self, new: dict) -> None:
        self.save_as_new_custom.emit(new)

    def _open_form_for_edit(self, adv: dict, count: int) -> None:
        self._form_dialog.load_for_edit(adv, count)
        self._form_dialog.exec()

    def _on_changed(self) -> None:
        if not self._saving and not self._loading:
            self._dirty = True
        self.title_changed.emit(self._tab_title())

    def _on_name_loaded(self, name: str) -> None:
        self.title_changed.emit(self._tab_title())

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def save_path(self) -> str:
        return self._save_path

    @property
    def preview_panel(self) -> EncounterPreviewPanel:
        return self._preview_panel

    @property
    def form_dialog(self) -> AdversaryFormDialog:
        return self._form_dialog

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
        self._saving = True
        try:
            self._save_path = path
            if name:
                self._preview_panel.set_encounter_name(name)
            self._dirty = False
        finally:
            self._saving = False
        self.title_changed.emit(self._tab_title())
