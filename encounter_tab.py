#!/usr/bin/env python3
"""encounter_tab.py — EncounterTab widget (edit + run modes via QStackedWidget)."""

import json
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from adversary import AdversaryFormDialog
from encounter_panel import EncounterPreviewPanel
from icons import pencil_icon
from run_canvas import RunAdversaryCard, _FlowContainer, _FlowLayout


class EncounterTab(QWidget):
    """Encounter workspace with two modes: edit (page 0) and run (page 1)."""
    title_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dirty      = False
        self._saving     = False
        self._loading    = False
        self._save_path  = ''
        self._is_running = False
        self._run_state: dict       = {}
        self._run_entries: list     = []
        self._run_cards: list[RunAdversaryCard] = []

        # ── Edit page ─────────────────────────────────────────────────────────
        self._preview_panel = EncounterPreviewPanel()
        self._preview_panel.set_budget_icon(pencil_icon())
        self._form_dialog = AdversaryFormDialog(self)

        edit_page = QWidget()
        el = QVBoxLayout(edit_page)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(self._preview_panel)

        # ── Run page ──────────────────────────────────────────────────────────
        self._run_flow_widget = _FlowContainer()
        self._run_flow_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        self._run_flow = _FlowLayout(self._run_flow_widget, h_spacing=8, v_spacing=8)
        self._run_flow.setContentsMargins(8, 8, 8, 8)

        run_scroll = QScrollArea()
        run_scroll.setWidget(self._run_flow_widget)
        run_scroll.setWidgetResizable(True)
        run_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # ── Stack ─────────────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.addWidget(edit_page)   # index 0 — edit
        self._stack.addWidget(run_scroll)  # index 1 — run

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        # ── Signal wiring ─────────────────────────────────────────────────────
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

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def save_path(self) -> str:
        return self._save_path

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def preview_panel(self) -> EncounterPreviewPanel:
        return self._preview_panel

    @property
    def form_dialog(self) -> AdversaryFormDialog:
        return self._form_dialog

    # ── Edit mode ─────────────────────────────────────────────────────────────

    def load_encounter_state(self, data: dict) -> None:
        self._loading = True
        try:
            self._preview_panel.load_encounter_state(data)
        finally:
            self._loading = False
        self._run_state = data.get('run_state', {})

    def get_encounter_state(self) -> dict:
        state = self._preview_panel.get_encounter_state()
        if self._run_state:
            state['run_state'] = self._run_state
        return state

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

    # ── Run mode ──────────────────────────────────────────────────────────────

    def start_run(self) -> None:
        self._is_running = True
        self._clear_run_canvas()
        entries = [
            e for e in self._preview_panel.get_encounter_state().get('entries', [])
            if e.get('adversary')
        ]
        self._run_entries = entries
        for idx, entry in enumerate(entries):
            adv   = entry.get('adversary', {})
            count = max(1, entry.get('count', 1))
            name  = adv.get('name', f'_entry_{idx}')
            saved_entry = self._run_state.get(name, {})
            saved = list(saved_entry.get('instances', []) if isinstance(saved_entry, dict) else [])
            while len(saved) < count:
                saved.append({'hp_spent': 0, 'stress_spent': 0})
            saved = saved[:count]
            card = RunAdversaryCard(adv, count, saved)
            card.state_changed.connect(self._autosave_run_state)
            self._run_flow.addWidget(card)
            self._run_cards.append(card)
        self._stack.setCurrentIndex(1)

    def stop_run(self) -> None:
        self._run_state = self._collect_run_state()
        self._is_running = False
        self._clear_run_canvas()
        self._stack.setCurrentIndex(0)

    def _clear_run_canvas(self) -> None:
        while self._run_flow.count():
            item = self._run_flow.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
        self._run_cards.clear()
        self._run_entries.clear()

    def _collect_run_state(self) -> dict:
        result = {}
        for idx, (entry, card) in enumerate(zip(self._run_entries, self._run_cards)):
            name = entry.get('adversary', {}).get('name', f'_entry_{idx}')
            result[name] = {'instances': card.get_instance_states()}
        return result

    def _autosave_run_state(self) -> None:
        self._run_state = self._collect_run_state()
        if not self._save_path:
            return
        try:
            data = json.loads(Path(self._save_path).read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return
        data['run_state'] = self._run_state
        try:
            Path(self._save_path).write_text(json.dumps(data, indent=2), encoding='utf-8')
        except OSError:
            pass
