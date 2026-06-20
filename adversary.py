#!/usr/bin/env python3
"""adversary.py — Adversary preview panel, form panel, and related dialogs."""

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QTextEdit, QVBoxLayout, QWidget,
)


# ── Feature edit dialog ───────────────────────────────────────────────────────

class FeatureEditDialog(QDialog):
    def __init__(self, feature: dict | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit Feature' if feature else 'Add Feature')
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        layout.addWidget(QLabel('Name:'))
        self._name = QLineEdit(feature.get('name', '') if feature else '')
        layout.addWidget(self._name)

        layout.addWidget(QLabel('Type:'))
        self._type = QComboBox()
        self._type.addItems(['Passive', 'Action', 'Reaction'])
        current_type = feature.get('type', 'Passive') if feature else 'Passive'
        idx = self._type.findText(current_type)
        self._type.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addWidget(self._type)

        layout.addWidget(QLabel('Description:'))
        self._desc = QTextEdit()
        self._desc.setMinimumHeight(120)
        self._desc.setPlainText(feature.get('desc', '') if feature else '')
        layout.addWidget(self._desc)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_feature(self) -> dict:
        return {
            'name': self._name.text().strip(),
            'type': self._type.currentText(),
            'desc': self._desc.toPlainText().strip(),
        }


# ── Adversary preview panel ───────────────────────────────────────────────────

class AdversaryPreviewPanel(QWidget):
    """Compact read-only view of a selected adversary with Add/Edit buttons."""
    add_to_encounter = Signal(dict, int)
    edit_requested   = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._adv: dict | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        vbox = QVBoxLayout(content)
        vbox.setSpacing(4)
        vbox.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(content)
        root.addWidget(scroll)

        self._name_lbl = QLabel()
        nf = QFont()
        nf.setBold(True)
        nf.setPointSize(nf.pointSize() + 2)
        self._name_lbl.setFont(nf)
        self._name_lbl.setWordWrap(True)
        vbox.addWidget(self._name_lbl)

        self._tier_role_lbl = QLabel()
        vbox.addWidget(self._tier_role_lbl)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setFrameShadow(QFrame.Shadow.Sunken)
        vbox.addWidget(sep1)

        self._flavor_lbl = QLabel()
        self._flavor_lbl.setWordWrap(True)
        ff = QFont()
        ff.setItalic(True)
        self._flavor_lbl.setFont(ff)
        vbox.addWidget(self._flavor_lbl)

        self._motives_lbl = QLabel()
        self._motives_lbl.setWordWrap(True)
        vbox.addWidget(self._motives_lbl)

        stats_frame = QFrame()
        stats_frame.setStyleSheet('background-color: palette(base); border-radius: 4px;')
        stats_frame.setAutoFillBackground(True)
        sf = QVBoxLayout(stats_frame)
        sf.setContentsMargins(8, 6, 8, 6)
        sf.setSpacing(2)
        self._stats_row1 = QLabel()
        self._stats_row1.setWordWrap(True)
        self._stats_row2 = QLabel()
        self._stats_row2.setWordWrap(True)
        self._stats_exp = QLabel()
        self._stats_exp.setWordWrap(True)
        sf.addWidget(self._stats_row1)
        sf.addWidget(self._stats_row2)
        sf.addWidget(self._stats_exp)
        vbox.addWidget(stats_frame)

        feat_heading = QLabel('<b>FEATURES</b>')
        vbox.addWidget(feat_heading)
        self._feat_lbl = QLabel()
        self._feat_lbl.setWordWrap(True)
        self._feat_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._feat_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        vbox.addWidget(self._feat_lbl)
        vbox.addStretch()

        bottom = QHBoxLayout()
        self._minus_btn = QPushButton('−')
        self._minus_btn.setFixedWidth(28)
        self._qty = QSpinBox()
        self._qty.setRange(1, 99)
        self._qty.setValue(1)
        self._plus_btn = QPushButton('+')
        self._plus_btn.setFixedWidth(28)
        self._minus_btn.clicked.connect(lambda: self._qty.setValue(max(1, self._qty.value() - 1)))
        self._plus_btn.clicked.connect(lambda: self._qty.setValue(self._qty.value() + 1))
        self._add_btn  = QPushButton('Add to Encounter')
        self._add_btn.setEnabled(False)
        self._add_btn.clicked.connect(self._on_add)
        self._edit_btn = QPushButton('Edit Adversary')
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        bottom.addWidget(self._minus_btn)
        bottom.addWidget(self._qty)
        bottom.addWidget(self._plus_btn)
        bottom.addStretch()
        bottom.addWidget(self._add_btn)
        bottom.addWidget(self._edit_btn)
        root.addLayout(bottom)

    def load(self, adv: dict) -> None:
        self._adv = adv
        self._qty.setValue(1)
        self._name_lbl.setText(adv.get('name', ''))

        tier  = adv.get('tier', '?')
        role  = adv.get('role', '')
        hq    = adv.get('horde_qty', '')
        parts = [f'Tier {tier}', role]
        if hq:
            parts.append(f'Horde: {hq}/HP')
        self._tier_role_lbl.setText('  ·  '.join(p for p in parts if p))

        flavor = (adv.get('flavor') or '').strip()
        self._flavor_lbl.setText(flavor)
        self._flavor_lbl.setVisible(bool(flavor))

        motives = (adv.get('motives') or '').strip()
        self._motives_lbl.setText(f'<b>Motives & Tactics:</b> {html.escape(motives)}' if motives else '')
        self._motives_lbl.setVisible(bool(motives))

        def _e(v) -> str:
            return html.escape(str(v)) if v else ''

        diff   = _e(adv.get('difficulty'))
        thr    = _e(adv.get('thresholds'))
        hp     = _e(adv.get('hp'))
        stress = _e(adv.get('stress'))
        row1 = ' | '.join(f'<b>{k}:</b> {v}' for k, v in [
            ('Difficulty', diff), ('Thresholds', thr), ('HP', hp), ('Stress', stress),
        ] if v)
        self._stats_row1.setText(row1)

        atk    = _e(adv.get('atk'))
        weapon = html.escape(adv.get('weapon', '') or '')
        rng    = html.escape(adv.get('range', '') or '')
        dmg    = html.escape(adv.get('damage', '') or '')
        dmg_t  = html.escape(adv.get('damage_type', '') or '')
        row2_parts = []
        if atk:    row2_parts.append(f'<b>ATK:</b> {atk}')
        if weapon: row2_parts.append(f'<b>{weapon}:</b> {rng}')
        elif rng:  row2_parts.append(f'<b>Range:</b> {rng}')
        if dmg:    row2_parts.append(f'{dmg} {dmg_t}'.strip())
        self._stats_row2.setText(' | '.join(row2_parts))

        exp = html.escape(adv.get('experience', '') or '')
        self._stats_exp.setText(f'<b>Experience:</b> {exp}' if exp else '')
        self._stats_exp.setVisible(bool(exp))

        feats = adv.get('features', [])
        self._feat_lbl.setText(''.join(
            f'<p style="margin:0 0 6px 0;"><b>{html.escape(f.get("name",""))} - {html.escape(f.get("type",""))}:</b>'
            f' {html.escape(f.get("desc",""))}</p>'
            for f in feats
        ))
        self._feat_lbl.setVisible(bool(feats))
        self._add_btn.setEnabled(True)
        self._edit_btn.setEnabled(True)

    def _on_add(self) -> None:
        if self._adv:
            self.add_to_encounter.emit(self._adv, self._qty.value())
            self._qty.setValue(1)

    def _on_edit(self) -> None:
        if self._adv:
            self.edit_requested.emit(self._adv)


# ── Adversary form panel ──────────────────────────────────────────────────────

class AdversaryFormPanel(QWidget):
    add_to_encounter    = Signal(dict, int)
    update_in_encounter = Signal(dict, dict, int)
    save_to_custom      = Signal(dict, dict)
    save_as_new_custom  = Signal(dict)

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

        # ── Features ──
        feat_hdr = QHBoxLayout()
        feat_hdr.setContentsMargins(0, 0, 0, 0)
        feat_hdr.addWidget(QLabel('<b>Features</b>'))
        feat_hdr.addStretch()
        add_feat_btn = QPushButton('Add Feature')
        add_feat_btn.clicked.connect(self._add_feat)
        feat_hdr.addWidget(add_feat_btn)
        vbox.addLayout(feat_hdr)

        self._feat_container = QWidget()
        self._feat_list = QVBoxLayout(self._feat_container)
        self._feat_list.setContentsMargins(0, 0, 0, 0)
        self._feat_list.setSpacing(2)
        vbox.addWidget(self._feat_container)
        vbox.addStretch()

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
            self._rebuild_feat_list()
        finally:
            self._loading = False
        self._loaded_adv = dict(adv)
        self._loaded_clean = self._collect()
        self._update_save_button()

    def _on_field_changed(self) -> None:
        if not self._loading:
            self._update_save_button()

    def _rebuild_feat_list(self) -> None:
        while self._feat_list.count():
            item = self._feat_list.takeAt(0)
            if w := item.widget():
                w.setParent(None)
        for i, feat in enumerate(self._features):
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(
                f'<b>{html.escape(feat.get("name",""))} - {html.escape(feat.get("type",""))}:</b>'
                f' {html.escape(feat.get("desc",""))}'
            )
            lbl.setWordWrap(True)
            edit_btn = QPushButton('Edit')
            edit_btn.setFixedWidth(44)
            edit_btn.clicked.connect(lambda _, idx=i: self._open_feat_edit(idx))
            rem_btn = QPushButton('×')
            rem_btn.setFixedWidth(24)
            rem_btn.clicked.connect(lambda _, idx=i: self._remove_feat(idx))
            row.addWidget(lbl, 1)
            row.addWidget(edit_btn)
            row.addWidget(rem_btn)
            self._feat_list.addWidget(row_widget)

    def _add_feat(self) -> None:
        dlg = FeatureEditDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._features = list(self._features)
            self._features.append(dlg.get_feature())
            self._rebuild_feat_list()
            self._update_save_button()

    def _open_feat_edit(self, idx: int) -> None:
        dlg = FeatureEditDialog(self._features[idx], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._features = list(self._features)
            self._features[idx] = dlg.get_feature()
            self._rebuild_feat_list()
            self._update_save_button()

    def _remove_feat(self, idx: int) -> None:
        name = self._features[idx].get('name', 'this feature')
        if QMessageBox.question(
            self, 'Remove Feature', f'Remove "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._features = list(self._features)
            del self._features[idx]
            self._rebuild_feat_list()
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


# ── Adversary form dialog ─────────────────────────────────────────────────────

class AdversaryFormDialog(QDialog):
    """AdversaryFormPanel in a modal dialog; closes after Add/Update."""
    add_to_encounter    = Signal(dict, int)
    update_in_encounter = Signal(dict, dict, int)
    save_to_custom      = Signal(dict, dict)
    save_as_new_custom  = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit Adversary')
        self.setMinimumWidth(520)
        self.setMinimumHeight(650)

        self.form_panel = AdversaryFormPanel()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.form_panel)

        self.form_panel.add_to_encounter.connect(self._on_add)
        self.form_panel.update_in_encounter.connect(self._on_update)
        self.form_panel.save_to_custom.connect(self.save_to_custom)
        self.form_panel.save_as_new_custom.connect(self.save_as_new_custom)

    def load(self, adv: dict) -> None:
        self.form_panel.load(adv)

    def load_for_edit(self, adv: dict, count: int) -> None:
        self.form_panel.load_for_edit(adv, count)

    def _on_add(self, adv: dict, count: int) -> None:
        self.add_to_encounter.emit(adv, count)
        self.accept()

    def _on_update(self, original: dict, new: dict, count: int) -> None:
        self.update_in_encounter.emit(original, new, count)
        self.accept()
