#!/usr/bin/env python3
"""encounter_panel.py — Encounter card widget and encounter preview panel."""

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from dh_constants import _ADJ_DELTAS, _ADJ_SHORT, _ROLE_COSTS
from budget_dialog import BudgetDialog


# ── Encounter card ────────────────────────────────────────────────────────────

class EncounterCard(QFrame):
    """One stat-block card for a group of adversaries in the encounter."""
    delete_all_requested = Signal(object)
    delete_one_requested = Signal(object, int)
    edit_requested       = Signal(dict, int)

    def __init__(self, adv: dict, count: int, parent=None):
        super().__init__(parent)
        self.adv = adv
        self._rows: list[QWidget] = []
        self._damage_bonus = False

        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(1)

        root = QVBoxLayout(self)
        root.setSpacing(2)
        root.setContentsMargins(6, 4, 6, 4)

        hdr = QHBoxLayout()
        self._title_lbl = QLabel()
        self._title_lbl.setWordWrap(True)
        edit_btn = QPushButton('Edit')
        edit_btn.setFixedWidth(40)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.adv, self.count))
        del_all = QPushButton('Remove all')
        del_all.setFixedWidth(80)
        del_all.clicked.connect(lambda: self.delete_all_requested.emit(self))
        hdr.addWidget(self._title_lbl, 1)
        hdr.addWidget(edit_btn)
        hdr.addWidget(del_all)
        root.addLayout(hdr)

        self._stats1_lbl = QLabel()
        self._stats2_lbl = QLabel()
        root.addWidget(self._stats1_lbl)
        root.addWidget(self._stats2_lbl)
        self._refresh_labels()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(1)
        root.addLayout(self._rows_layout)

        for _ in range(count):
            self._add_row()

    def _refresh_labels(self) -> None:
        adv = self.adv
        self._title_lbl.setText(
            f"<b>{adv.get('name', '?')}</b>"
            f"  ·  Tier {adv.get('tier', '?')}"
            f"  ·  {adv.get('role', '')}"
        )
        self._stats1_lbl.setText(
            f"Difficulty: {adv.get('difficulty', '?')}  ·  "
            f"HP: {adv.get('hp', '?')}  ·  "
            f"Stress: {adv.get('stress', '?')}  ·  "
            f"Thresholds: {adv.get('thresholds', '?')}"
        )
        dmg = adv.get('damage', '?') or '?'
        if self._damage_bonus and dmg and dmg != '?':
            dmg = f'{dmg}+1d4'
        self._stats2_lbl.setText(
            f"ATK: {adv.get('atk', '?')}  ·  "
            f"{adv.get('weapon', '?')}: {adv.get('range', '?')}  ·  "
            f"{dmg} {adv.get('damage_type', '')}"
        )

    def set_damage_bonus(self, enabled: bool) -> None:
        if self._damage_bonus != enabled:
            self._damage_bonus = enabled
            self._refresh_labels()

    def update(self, adv: dict, new_count: int) -> None:
        self.adv = adv
        self._refresh_labels()
        while len(self._rows) > new_count:
            w = self._rows.pop()
            self._rows_layout.removeWidget(w)
            w.deleteLater()
        while len(self._rows) < new_count:
            self._add_row()
        for i, rw in enumerate(self._rows):
            rw.layout().itemAt(0).widget().setText(self._row_label(i))

    def _row_label(self, idx: int) -> str:
        return f"  #{idx + 1}   HP {self.adv.get('hp', '?')}  |  Stress {self.adv.get('stress', '?')}"

    def _add_row(self) -> None:
        row_widget = QWidget()
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        lbl = QLabel(self._row_label(len(self._rows)))
        del_btn = QPushButton('✕')
        del_btn.setFixedWidth(24)
        del_btn.setFixedHeight(20)
        del_btn.clicked.connect(
            lambda checked=False, w=row_widget: self.delete_one_requested.emit(self, self._rows.index(w))
        )
        row.addWidget(lbl, 1)
        row.addWidget(del_btn)
        self._rows_layout.addWidget(row_widget)
        self._rows.append(row_widget)

    def add_individuals(self, count: int) -> None:
        for _ in range(count):
            self._add_row()

    def remove_individual(self, idx: int) -> None:
        if 0 <= idx < len(self._rows):
            w = self._rows.pop(idx)
            self._rows_layout.removeWidget(w)
            w.deleteLater()
            for i, rw in enumerate(self._rows):
                rw.layout().itemAt(0).widget().setText(self._row_label(i))

    @property
    def count(self) -> int:
        return len(self._rows)


# ── Encounter preview panel ───────────────────────────────────────────────────

class EncounterPreviewPanel(QWidget):
    edit_requested        = Signal(dict, int)
    encounter_changed     = Signal()
    name_loaded           = Signal(str)
    budget_config_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[EncounterCard] = []
        self._loading = False
        self._budget: dict | None = None
        self._encounter_name_str = ''

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Name + budget row (moved here from EncounterTab header)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('Name:'))
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self._name_edit, 1)
        root.addLayout(name_row)

        self._budget_btn = QPushButton('Click to configure budget')
        self._budget_btn.setFlat(True)
        self._budget_btn.setStyleSheet('text-align: left; padding-left: 2px;')
        self._budget_btn.clicked.connect(self.configure_budget)
        budget_row = QHBoxLayout()
        budget_row.addWidget(self._budget_btn)
        budget_row.addStretch()
        root.addLayout(budget_row)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep1)

        self._budget_result_lbl = QLabel()
        self._budget_result_lbl.setVisible(False)
        root.addWidget(self._budget_result_lbl)

        self._count_lbl = QLabel('0 adversaries')
        root.addWidget(self._count_lbl)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._cards_layout = QVBoxLayout(self._container)
        self._cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._cards_layout.setSpacing(8)
        scroll.setWidget(self._container)
        root.addWidget(scroll)

    @property
    def encounter_name(self) -> str:
        return self._encounter_name_str

    def set_encounter_name(self, name: str) -> None:
        if self._encounter_name_str != name:
            self._encounter_name_str = name
            self._name_edit.blockSignals(True)
            self._name_edit.setText(name)
            self._name_edit.blockSignals(False)

    def _on_name_changed(self, text: str) -> None:
        self._encounter_name_str = text
        if not self._loading:
            self.encounter_changed.emit()

    def set_budget_icon(self, icon) -> None:
        self._budget_btn.setIcon(icon)

    def _budget_config_text(self) -> str:
        if not self._budget:
            return 'Click to configure budget'
        parts = [f"{self._budget.get('num_pcs', 4)} PCs",
                 f"Tier {self._budget.get('party_tier', 1)}"]
        for key, label in _ADJ_SHORT.items():
            if self._budget.get(key):
                parts.append(label)
        return '  ·  '.join(parts)

    def _auto_adjust_budget(self) -> None:
        if not self._budget or not self._budget.get('dynamic', False):
            return
        party_tier  = self._budget.get('party_tier', 1)
        heavy_roles = {'Bruiser', 'Horde', 'Leader', 'Solo'}
        solo_count  = sum(c.count for c in self._cards if c.adv.get('role') == 'Solo')
        has_heavy   = any(c.adv.get('role') in heavy_roles for c in self._cards)
        has_lower   = any(c.adv.get('tier', party_tier) < party_tier for c in self._cards)
        self._budget['adj_two_plus_solos'] = solo_count >= 2
        self._budget['adj_no_heavy_roles'] = bool(self._cards) and not has_heavy
        self._budget['adj_lower_tier']     = has_lower

    def add_entry(self, adv: dict, count: int) -> None:
        name = adv.get('name', '')
        for card in self._cards:
            if card.adv.get('name', '') == name:
                card.add_individuals(count)
                self._update_count()
                return
        card = EncounterCard(adv, count)
        card.set_damage_bonus(bool(self._budget and self._budget.get('adj_damage_bonus')))
        card.delete_all_requested.connect(self._on_delete_all)
        card.delete_one_requested.connect(self._on_delete_one)
        card.edit_requested.connect(self.edit_requested)
        self._cards_layout.addWidget(card)
        self._cards.append(card)
        self._update_count()

    def _on_delete_all(self, card: EncounterCard) -> None:
        self._cards.remove(card)
        self._cards_layout.removeWidget(card)
        card.deleteLater()
        self._update_count()

    def _on_delete_one(self, card: EncounterCard, idx: int) -> None:
        card.remove_individual(idx)
        if card.count == 0:
            self._on_delete_all(card)
        else:
            self._update_count()

    def _update_count(self) -> None:
        self._auto_adjust_budget()
        total = sum(c.count for c in self._cards)
        role_counts: dict[str, int] = {}
        for card in self._cards:
            role = card.adv.get('role', '')
            if role:
                role_counts[role] = role_counts.get(role, 0) + card.count
        base = f'{total} adversar{"y" if total == 1 else "ies"}'
        if role_counts:
            parts = ', '.join(
                f'{n} {r}' for r, n in sorted(role_counts.items(), key=lambda x: -x[1])
            )
            self._count_lbl.setText(f'{base}  ({parts})')
        else:
            self._count_lbl.setText(base)
        self._update_budget_display()
        if not self._loading:
            self.encounter_changed.emit()

    # ── Budget ────────────────────────────────────────────────────────────────

    def configure_budget(self) -> None:
        dlg = BudgetDialog(self._budget, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._budget = dlg.get_settings()
            self._auto_adjust_budget()
            self._update_budget_display()
            if not self._loading:
                self.encounter_changed.emit()

    def _budget_total(self) -> int:
        if not self._budget:
            return 0
        n = self._budget.get('num_pcs', 4)
        base = 3 * n + 2
        adj = sum(delta for key, delta in _ADJ_DELTAS.items() if self._budget.get(key))
        return base + adj

    def _budget_spent(self) -> int:
        if not self._budget:
            return 0
        num_pcs = self._budget.get('num_pcs', 4)
        total = 0
        for card in self._cards:
            role  = card.adv.get('role', '')
            count = card.count
            cost  = _ROLE_COSTS.get(role, 2)
            if cost is None:
                total += math.ceil(count / max(1, num_pcs))
            else:
                total += cost * count
        return total

    def _update_budget_display(self) -> None:
        cfg_text = self._budget_config_text()
        self._budget_btn.setText(cfg_text)
        self.budget_config_changed.emit(cfg_text)
        bonus = bool(self._budget and self._budget.get('adj_damage_bonus'))
        for card in self._cards:
            card.set_damage_bonus(bonus)
        if not self._budget:
            self._budget_result_lbl.setVisible(False)
            return
        budget    = self._budget_total()
        spent     = self._budget_spent()
        remaining = budget - spent
        if remaining > 0:
            rem_html = f'<span style="color: grey;">{remaining} remaining</span>'
        elif remaining == 0:
            rem_html = '<span style="color: #4a9e4a; font-weight: bold;">On budget</span>'
        else:
            rem_html = f'<span style="color: #c0392b; font-weight: bold;">{-remaining} over budget</span>'
        self._budget_result_lbl.setText(
            f'Budget {budget} pts  ·  Spent {spent} pts  ·  {rem_html}'
        )
        self._budget_result_lbl.setVisible(True)

    def update_entry(self, original_adv: dict, new_adv: dict, new_count: int) -> None:
        original_name = original_adv.get('name', '')
        for card in self._cards:
            if card.adv.get('name', '') == original_name:
                if new_count <= 0:
                    self._on_delete_all(card)
                else:
                    card.update(new_adv, new_count)
                    self._update_count()
                return

    def get_encounter_state(self) -> dict:
        state = {
            'name': self._encounter_name_str,
            'entries': [
                {'adversary': card.adv, 'count': card.count}
                for card in self._cards
            ],
        }
        if self._budget is not None:
            state['budget'] = self._budget
        return state

    def load_encounter_state(self, data: dict) -> None:
        self._loading = True
        try:
            for card in list(self._cards):
                self._cards_layout.removeWidget(card)
                card.deleteLater()
            self._cards.clear()
            name = data.get('name', '')
            self._encounter_name_str = name
            self._name_edit.blockSignals(True)
            self._name_edit.setText(name)
            self._name_edit.blockSignals(False)
            self._budget = data.get('budget') or None
            for entry in data.get('entries', []):
                adv = entry.get('adversary', {})
                count = entry.get('count', 1)
                if adv and count > 0:
                    self.add_entry(adv, count)
            self._update_count()
        finally:
            self._loading = False
        self.name_loaded.emit(self._encounter_name_str)
