#!/usr/bin/env python3
"""adversary_encounter.py — Adversary form, encounter cards, and encounter tab."""

import math

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QSpinBox, QSplitter,
    QTextEdit, QVBoxLayout, QWidget,
)


# ── Battle budget constants ───────────────────────────────────────────────────

# Points spent per individual adversary of each role.
# None = Minion special rule: 1 pt per group equal to party size.
_ROLE_COSTS: dict[str, int | None] = {
    'Minion':   None,
    'Social':   1,
    'Support':  1,
    'Horde':    2,
    'Ranged':   2,
    'Skulk':    2,
    'Standard': 2,
    'Leader':   3,
    'Bruiser':  4,
    'Solo':     5,
}

_ADJ_DELTAS: dict[str, int] = {
    'adj_less_difficult': -1,
    'adj_two_plus_solos': -2,
    'adj_damage_bonus':   -2,
    'adj_lower_tier':     +1,
    'adj_no_heavy_roles': +1,
    'adj_more_dangerous': +2,
}


# ── Budget dialog ─────────────────────────────────────────────────────────────

class BudgetDialog(QDialog):
    """Configure battle budget: PC count, party tier, and point adjustments."""

    _ADJUSTMENTS = [
        ('adj_less_difficult', '−1   Less difficult or shorter'),
        ('adj_two_plus_solos', '−2   Using 2 or more Solo adversaries'),
        ('adj_damage_bonus',   '−2   Adding +1d4 to all adversary damage'),
        ('adj_lower_tier',     '+1   Adversaries from a lower tier than the party'),
        ('adj_no_heavy_roles', '+1   No Bruisers, Hordes, Leaders, or Solos'),
        ('adj_more_dangerous', '+2   More dangerous or longer'),
    ]

    def __init__(self, settings: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Configure Battle Budget')
        self.setMinimumWidth(430)
        self._cleared = False
        s = settings or {}

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── PC count ──
        pc_row = QHBoxLayout()
        pc_row.addWidget(QLabel('Number of PCs:'))
        self._num_pcs = QSpinBox()
        self._num_pcs.setRange(1, 10)
        self._num_pcs.setValue(s.get('num_pcs', 4))
        self._num_pcs.valueChanged.connect(self._refresh)
        pc_row.addWidget(self._num_pcs)
        pc_row.addStretch()
        root.addLayout(pc_row)

        # ── Party tier ──
        tier_row = QHBoxLayout()
        tier_row.addWidget(QLabel('Party tier:'))
        self._party_tier = QSpinBox()
        self._party_tier.setRange(1, 4)
        self._party_tier.setValue(s.get('party_tier', 1))
        tier_row.addWidget(self._party_tier)
        tier_row.addStretch()
        root.addLayout(tier_row)

        # ── Adjustments ──
        root.addWidget(QLabel('<b>Adjustments</b>'))
        self._checks: dict[str, QCheckBox] = {}
        for key, label in self._ADJUSTMENTS:
            cb = QCheckBox(label)
            cb.setChecked(s.get(key, False))
            cb.stateChanged.connect(self._refresh)
            root.addWidget(cb)
            self._checks[key] = cb

        # ── Budget preview ──
        self._preview_lbl = QLabel()
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._preview_lbl)
        self._refresh()

        # ── Buttons ──
        btn_row = QHBoxLayout()
        clear_btn = QPushButton('Clear Budget')
        clear_btn.clicked.connect(self._on_clear)
        ok_btn = QPushButton('OK')
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    def _calc(self) -> tuple[int, int]:
        n = self._num_pcs.value()
        base = 3 * n + 2
        adj = sum(delta for key, delta in _ADJ_DELTAS.items() if self._checks[key].isChecked())
        return base, base + adj

    def _refresh(self) -> None:
        base, total = self._calc()
        n = self._num_pcs.value()
        adj = total - base
        text = f'Base ({n} PCs × 3 + 2) = {base} pts'
        if adj:
            text += f'  ·  Adjustments: {adj:+d}'
        text += f'  →  <b>Budget: {total} pts</b>'
        self._preview_lbl.setText(text)

    def _on_clear(self) -> None:
        self._cleared = True
        self.accept()

    def get_settings(self) -> dict | None:
        """Return settings dict, or None if the user chose to clear the budget."""
        if self._cleared:
            return None
        return {
            'num_pcs':    self._num_pcs.value(),
            'party_tier': self._party_tier.value(),
            **{key: self._checks[key].isChecked() for key, _ in self._ADJUSTMENTS},
        }


# ── Adversary form panel ──────────────────────────────────────────────────────

class AdversaryFormPanel(QWidget):
    add_to_encounter    = Signal(dict, int)
    update_in_encounter = Signal(dict, dict, int)  # (original, new, count)
    save_to_custom      = Signal(dict, dict)  # (original, new) — overwrites if homebrew
    save_as_new_custom  = Signal(dict)        # always creates a new entry

    def __init__(self, parent=None):
        super().__init__(parent)
        self._features: list[dict] = []
        self._edit_original: dict | None = None
        self._loaded_adv: dict | None = None
        self._loaded_clean: dict | None = None
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        vbox = QVBoxLayout(form_widget)
        vbox.setSpacing(6)
        vbox.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(form_widget)
        root.addWidget(scroll)

        # ── Name ──
        self._name = QLineEdit()
        self._save_custom_btn = QPushButton()
        self._save_custom_btn.setVisible(False)
        self._save_custom_btn.clicked.connect(self._emit_save_custom)
        self._save_as_new_btn = QPushButton('Save as New')
        self._save_as_new_btn.setVisible(False)
        self._save_as_new_btn.clicked.connect(self._emit_save_as_new)
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.addWidget(self._name, 1)
        name_row.addWidget(self._save_custom_btn)
        name_row.addWidget(self._save_as_new_btn)
        vbox.addLayout(name_row)

        # ── Tier | Role | Horde Qty ──
        self._role = ''
        self._role_lbl = QLabel('')
        self._tier = QComboBox()
        self._tier.addItems(['1', '2', '3', '4'])
        self._tier.setFixedWidth(52)
        self._horde_qty_label = QLabel('Horde:')
        self._horde_qty = QLineEdit()
        self._horde_qty.setFixedWidth(38)
        self._horde_qty_suffix = QLabel('/HP')
        self._horde_qty_label.hide()
        self._horde_qty.hide()
        self._horde_qty_suffix.hide()
        identity_row = QHBoxLayout()
        identity_row.setSpacing(4)
        identity_row.addWidget(QLabel('Tier:'))
        identity_row.addWidget(self._tier)
        identity_row.addSpacing(10)
        identity_row.addWidget(self._role_lbl)
        identity_row.addSpacing(10)
        identity_row.addWidget(self._horde_qty_label)
        identity_row.addWidget(self._horde_qty)
        identity_row.addWidget(self._horde_qty_suffix)
        identity_row.addStretch()
        vbox.addLayout(identity_row)

        # ── Flavor ──
        self._flavor = QTextEdit()
        self._flavor.setFixedHeight(56)
        vbox.addWidget(QLabel('Flavor'))
        vbox.addWidget(self._flavor)

        # ── Motives ──
        self._motives = QTextEdit()
        self._motives.setFixedHeight(56)
        vbox.addWidget(QLabel('Motives'))
        vbox.addWidget(self._motives)

        # ── Stats grid (Difficulty → Experience) ──
        self._difficulty  = QLineEdit()
        self._thresholds  = QLineEdit()
        self._hp          = QLineEdit()
        self._stress      = QLineEdit()
        self._atk         = QLineEdit()
        self._weapon      = QLineEdit()
        self._range       = QLineEdit()
        self._damage      = QLineEdit()
        self._damage_type = QLineEdit()
        self._experience  = QLineEdit()

        stats = QGridLayout()
        stats.setSpacing(4)
        stats.setColumnStretch(1, 2)
        stats.setColumnStretch(3, 3)
        stats.setColumnStretch(5, 2)

        stats.addWidget(QLabel('Difficulty:'),  0, 0)
        stats.addWidget(self._difficulty,       0, 1)
        stats.addWidget(QLabel('Thresholds:'),  0, 2)
        stats.addWidget(self._thresholds,       0, 3, 1, 3)

        stats.addWidget(QLabel('HP:'),          1, 0)
        stats.addWidget(self._hp,               1, 1)
        stats.addWidget(QLabel('Stress:'),      1, 2)
        stats.addWidget(self._stress,           1, 3, 1, 3)

        stats.addWidget(QLabel('ATK:'),         2, 0)
        stats.addWidget(self._atk,              2, 1)
        stats.addWidget(QLabel('Weapon:'),      2, 2)
        stats.addWidget(self._weapon,           2, 3, 1, 3)

        stats.addWidget(QLabel('Range:'),       3, 0)
        stats.addWidget(self._range,            3, 1)
        stats.addWidget(QLabel('Damage:'),      3, 2)
        stats.addWidget(self._damage,           3, 3)
        stats.addWidget(QLabel('Type:'),        3, 4)
        stats.addWidget(self._damage_type,      3, 5)

        stats.addWidget(QLabel('Experience:'),  4, 0)
        stats.addWidget(self._experience,       4, 1, 1, 5)

        vbox.addLayout(stats)

        # ── Features (read-only, grows to fill space) ──
        self._feat_display = QTextEdit()
        self._feat_display.setReadOnly(True)
        self._feat_display.setMinimumHeight(150)
        self._feat_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        vbox.addWidget(QLabel('Features'))
        vbox.addWidget(self._feat_display, stretch=1)

        # ── Quantity + Add to Encounter ──
        qty_row = QHBoxLayout()
        qty_row.addWidget(QLabel('Quantity:'))
        self._minus = QPushButton('−')
        self._minus.setFixedWidth(28)
        self._qty = QSpinBox()
        self._qty.setRange(1, 99)
        self._qty.setValue(1)
        self._plus = QPushButton('+')
        self._plus.setFixedWidth(28)
        self._minus.clicked.connect(lambda: self._qty.setValue(max(1, self._qty.value() - 1)))
        self._plus.clicked.connect(lambda: self._qty.setValue(self._qty.value() + 1))
        self._cancel_btn = QPushButton('Cancel')
        self._cancel_btn.clicked.connect(self._exit_edit_mode)
        self._cancel_btn.setVisible(False)
        self._add_btn = QPushButton('Add to Encounter')
        self._add_btn.clicked.connect(self._emit_action)
        qty_row.addWidget(self._minus)
        qty_row.addWidget(self._qty)
        qty_row.addWidget(self._plus)
        qty_row.addStretch()
        qty_row.addWidget(self._cancel_btn)
        qty_row.addWidget(self._add_btn)
        root.addLayout(qty_row)

        for w in (self._name, self._difficulty, self._thresholds, self._hp,
                  self._stress, self._atk, self._weapon, self._range,
                  self._damage, self._damage_type, self._experience, self._horde_qty):
            w.textChanged.connect(self._on_field_changed)
        self._tier.currentIndexChanged.connect(self._on_field_changed)
        self._flavor.textChanged.connect(self._on_field_changed)
        self._motives.textChanged.connect(self._on_field_changed)

    def load(self, adv: dict) -> None:
        self._loading = True
        try:
            self._exit_edit_mode()
            self._features = adv.get('features', [])
            self._name.setText(adv.get('name', ''))
            tier = str(adv.get('tier', 1))
            idx = self._tier.findText(tier)
            self._tier.setCurrentIndex(idx if idx >= 0 else 0)
            role = adv.get('role', '')
            self._role = role
            self._role_lbl.setText(role)
            is_horde = role == 'Horde'
            self._horde_qty_label.setVisible(is_horde)
            self._horde_qty.setVisible(is_horde)
            self._horde_qty_suffix.setVisible(is_horde)
            if is_horde:
                self._horde_qty.setText(str(adv.get('horde_qty') or ''))
            self._flavor.setPlainText(adv.get('flavor', '') or '')
            self._motives.setPlainText(adv.get('motives', '') or '')
            self._difficulty.setText(str(adv.get('difficulty', '') or ''))
            self._thresholds.setText(str(adv.get('thresholds', '') or ''))
            self._hp.setText(str(adv.get('hp', '') or ''))
            self._stress.setText(str(adv.get('stress', '') or ''))
            self._atk.setText(str(adv.get('atk', '') or ''))
            self._weapon.setText(adv.get('weapon', '') or '')
            self._range.setText(adv.get('range', '') or '')
            self._damage.setText(adv.get('damage', '') or '')
            self._damage_type.setText(adv.get('damage_type', '') or '')
            self._experience.setText(adv.get('experience', '') or '')
            feat_lines = [f"{f['name']} - {f['type']}:\n  {f['desc']}" for f in self._features]
            self._feat_display.setPlainText('\n\n'.join(feat_lines))
        finally:
            self._loading = False
        self._loaded_adv = dict(adv)
        self._loaded_clean = self._collect()
        self._update_save_button()

    def _on_field_changed(self) -> None:
        if not self._loading:
            self._update_save_button()

    def _is_dirty(self) -> bool:
        if self._loaded_clean is None:
            return False
        return self._collect() != self._loaded_clean

    def _update_save_button(self) -> None:
        if self._loaded_adv is None or not self._is_dirty():
            self._save_custom_btn.setVisible(False)
            self._save_as_new_btn.setVisible(False)
            return
        is_custom = bool(self._loaded_adv.get('homebrew'))
        if is_custom:
            self._save_custom_btn.setText('Save')
            self._save_custom_btn.setVisible(True)
            self._save_as_new_btn.setVisible(self._name.text() != self._loaded_adv.get('name', ''))
        else:
            self._save_custom_btn.setText('Save as Custom')
            self._save_custom_btn.setVisible(True)
            self._save_as_new_btn.setVisible(False)

    def _emit_save_custom(self) -> None:
        new = self._collect()
        self.save_to_custom.emit(self._loaded_adv, new)
        self._loaded_adv = dict(new)
        self._loaded_adv['homebrew'] = True
        self._loaded_clean = self._collect()
        self._update_save_button()

    def _emit_save_as_new(self) -> None:
        new = self._collect()
        self.save_as_new_custom.emit(new)
        self._loaded_adv = dict(new)
        self._loaded_adv['homebrew'] = True
        self._loaded_clean = self._collect()
        self._update_save_button()

    def _collect(self) -> dict:
        result = {
            'name':        self._name.text(),
            'tier':        int(self._tier.currentText()),
            'role':        self._role,
            'flavor':      self._flavor.toPlainText(),
            'motives':     self._motives.toPlainText(),
            'difficulty':  self._difficulty.text(),
            'thresholds':  self._thresholds.text(),
            'hp':          self._hp.text(),
            'stress':      self._stress.text(),
            'atk':         self._atk.text(),
            'weapon':      self._weapon.text(),
            'range':       self._range.text(),
            'damage':      self._damage.text(),
            'damage_type': self._damage_type.text(),
            'horde_qty':   self._horde_qty.text() or None if self._horde_qty.isVisible() else None,
            'experience':  self._experience.text(),
            'features':    self._features,
        }
        if self._loaded_adv and self._loaded_adv.get('homebrew'):
            result['homebrew'] = True
        return result

    def load_for_edit(self, adv: dict, count: int) -> None:
        self.load(adv)
        self._edit_original = adv
        self._qty.setValue(count)
        self._add_btn.setText('Update Encounter')
        self._cancel_btn.setVisible(True)

    def _exit_edit_mode(self) -> None:
        self._edit_original = None
        self._add_btn.setText('Add to Encounter')
        self._cancel_btn.setVisible(False)

    def _emit_action(self) -> None:
        if self._edit_original is not None:
            self.update_in_encounter.emit(self._edit_original, self._collect(), self._qty.value())
            self._exit_edit_mode()
        else:
            self.add_to_encounter.emit(self._collect(), self._qty.value())


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
        self._stats2_lbl.setText(
            f"ATK: {adv.get('atk', '?')}  ·  "
            f"{adv.get('weapon', '?')}: {adv.get('range', '?')}  ·  "
            f"{adv.get('damage', '?')} {adv.get('damage_type', '')}"
        )

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
    edit_requested    = Signal(dict, int)
    encounter_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[EncounterCard] = []
        self._loading = False
        self._budget: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        hdr = QHBoxLayout()
        hdr.addWidget(QLabel('<b>Encounter</b>'))
        hdr.addStretch()
        self._count_lbl = QLabel('0 adversaries')
        hdr.addWidget(self._count_lbl)
        budget_btn = QPushButton('⚙ Budget')
        budget_btn.setFixedHeight(22)
        budget_btn.clicked.connect(self._configure_budget)
        hdr.addWidget(budget_btn)
        root.addLayout(hdr)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel('Name:'))
        self._encounter_name = QLineEdit()
        self._encounter_name.textChanged.connect(self._emit_changed)
        name_row.addWidget(self._encounter_name, stretch=1)
        root.addLayout(name_row)

        self._budget_lbl = QLabel()
        self._budget_lbl.setVisible(False)
        root.addWidget(self._budget_lbl)

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
        return self._encounter_name.text()

    def set_encounter_name(self, name: str) -> None:
        self._encounter_name.setText(name)

    def _emit_changed(self) -> None:
        if not self._loading:
            self.encounter_changed.emit()

    def add_entry(self, adv: dict, count: int) -> None:
        name = adv.get('name', '')
        for card in self._cards:
            if card.adv.get('name', '') == name:
                card.add_individuals(count)
                self._update_count()
                return
        card = EncounterCard(adv, count)
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
        total = sum(c.count for c in self._cards)
        self._count_lbl.setText(f'{total} adversar{"y" if total == 1 else "ies"}')
        self._update_budget_display()
        self._emit_changed()

    # ── Budget ────────────────────────────────────────────────────────────────

    def _configure_budget(self) -> None:
        dlg = BudgetDialog(self._budget, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._budget = dlg.get_settings()
            self._update_budget_display()
            self._emit_changed()

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
        if not self._budget:
            self._budget_lbl.setVisible(False)
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
        self._budget_lbl.setText(
            f'Budget {budget} pts  ·  Spent {spent} pts  ·  {rem_html}'
        )
        self._budget_lbl.setVisible(True)

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
            'name': self._encounter_name.text(),
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
            self._encounter_name.setText(data.get('name', ''))
            self._budget = data.get('budget') or None
            for entry in data.get('entries', []):
                adv = entry.get('adversary', {})
                count = entry.get('count', 1)
                if adv and count > 0:
                    self.add_entry(adv, count)
            self._update_count()
        finally:
            self._loading = False


# ── Encounter tab ─────────────────────────────────────────────────────────────

class EncounterTab(QWidget):
    """Self-contained encounter workspace: form panel + preview panel in a splitter."""
    title_changed = Signal(str)

    def __init__(self, layout_mode: str = '3col', parent=None):
        super().__init__(parent)
        self._dirty = False
        self._saving = False
        self._save_path = ''
        self._initial_split_done = False

        self._form_panel    = AdversaryFormPanel()
        self._preview_panel = EncounterPreviewPanel()

        self._splitter = QSplitter(
            Qt.Orientation.Horizontal if layout_mode == '3col' else Qt.Orientation.Vertical
        )
        self._splitter.addWidget(self._form_panel)
        self._splitter.addWidget(self._preview_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)

        self._form_panel.add_to_encounter.connect(self._preview_panel.add_entry)
        self._form_panel.update_in_encounter.connect(self._preview_panel.update_entry)
        self._preview_panel.edit_requested.connect(self._form_panel.load_for_edit)
        self._preview_panel.encounter_changed.connect(self._on_changed)

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
    def form_panel(self) -> AdversaryFormPanel:
        return self._form_panel

    @property
    def preview_panel(self) -> EncounterPreviewPanel:
        return self._preview_panel

    def _on_changed(self) -> None:
        if not self._saving:
            self._dirty = True
        self.title_changed.emit(self._tab_title())

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
                self._preview_panel.set_encounter_name(name)
            self._dirty = False
        finally:
            self._saving = False
        self.title_changed.emit(self._tab_title())

