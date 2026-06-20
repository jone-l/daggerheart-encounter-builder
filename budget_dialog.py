#!/usr/bin/env python3
"""budget_dialog.py — Battle budget configuration dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout,
)

from dh_constants import _ADJ_DELTAS


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

    _AUTO_KEYS = frozenset({'adj_two_plus_solos', 'adj_lower_tier', 'adj_no_heavy_roles'})

    def __init__(self, settings: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Configure Battle Budget')
        self.setMinimumWidth(430)
        self._cleared = False
        s = settings or {}

        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Dynamic budget ──
        self._dynamic = QCheckBox('Dynamic budget (auto-applies party composition adjustments)')
        default_dynamic = True if settings is None else settings.get('dynamic', False)
        self._dynamic.setChecked(default_dynamic)
        root.addWidget(self._dynamic)

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
            if key == 'adj_less_difficult':
                cb.stateChanged.connect(self._on_less_difficult)
            elif key == 'adj_more_dangerous':
                cb.stateChanged.connect(self._on_more_dangerous)
            else:
                cb.stateChanged.connect(self._refresh)
            root.addWidget(cb)
            self._checks[key] = cb

        # ── Budget preview ──
        self._preview_lbl = QLabel()
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._preview_lbl)

        self._dynamic.stateChanged.connect(self._on_dynamic_changed)
        self._on_dynamic_changed()  # sets enabled state and calls _refresh()

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

    def _on_dynamic_changed(self) -> None:
        is_dynamic = self._dynamic.isChecked()
        for key in self._AUTO_KEYS:
            self._checks[key].setEnabled(not is_dynamic)
        self._refresh()

    def _on_less_difficult(self, state: int) -> None:
        if state:
            self._checks['adj_more_dangerous'].blockSignals(True)
            self._checks['adj_more_dangerous'].setChecked(False)
            self._checks['adj_more_dangerous'].blockSignals(False)
        self._refresh()

    def _on_more_dangerous(self, state: int) -> None:
        if state:
            self._checks['adj_less_difficult'].blockSignals(True)
            self._checks['adj_less_difficult'].setChecked(False)
            self._checks['adj_less_difficult'].blockSignals(False)
        self._refresh()

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
            'dynamic':    self._dynamic.isChecked(),
            **{key: self._checks[key].isChecked() for key, _ in self._ADJUSTMENTS},
        }
