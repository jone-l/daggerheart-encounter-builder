#!/usr/bin/env python3
"""adversary_table.py — Filter panel + sortable adversary table with inline preview."""

import html
import re

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from dh_constants import _ROLE_COSTS
from icons import chevron_right_icon, chevron_down_icon, chevron_up_icon, chevrons_up_down_icon

_ALL_ROLES    = sorted(_ROLE_COSTS.keys())
_ALL_TIERS    = [1, 2, 3, 4]
_ALL_SOURCES  = [('official', 'Official'), ('homebrew', 'Homebrew')]

# Fixed pixel widths for non-name columns (keeps header and rows aligned)
_ROLE_W   = 100
_TIER_W   = 50
_ACTION_W = 216   # Edit + − + spinbox + + + Add


# ── Helpers ───────────────────────────────────────────────────────────────────

class _ClickableWidget(QWidget):
    """QWidget that emits clicked() on left mouse press (child buttons suppress it)."""
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── Filter section ────────────────────────────────────────────────────────────

class _FilterSection(QWidget):
    changed = Signal()

    def __init__(self, title: str, items: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self._items = items
        self._checks: dict[str, QCheckBox] = {}
        self._collapsed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(0)

        self._hdr_btn = QPushButton(f' {title}')
        self._hdr_btn.setFlat(True)
        self._hdr_btn.setStyleSheet('text-align: left; font-weight: bold; padding: 2px 4px;')
        self._hdr_btn.setIcon(chevron_down_icon())
        self._hdr_btn.setIconSize(QSize(16, 16))
        self._hdr_btn.clicked.connect(self._toggle)
        root.addWidget(self._hdr_btn)

        self._content = QWidget()
        cl = QVBoxLayout(self._content)
        cl.setContentsMargins(16, 0, 4, 4)
        cl.setSpacing(2)
        for value, label in items:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.stateChanged.connect(self.changed)
            cl.addWidget(cb)
            self._checks[value] = cb
        root.addWidget(self._content)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._hdr_btn.setIcon(chevron_right_icon() if self._collapsed else chevron_down_icon())

    def get_checked(self) -> set[str]:
        return {v for v, _ in self._items if self._checks[v].isChecked()}

    def set_all(self, checked: bool) -> None:
        for cb in self._checks.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self.changed.emit()

    def restore(self, values: set[str]) -> None:
        for v, cb in self._checks.items():
            cb.blockSignals(True)
            cb.setChecked(v in values)
            cb.blockSignals(False)


# ── Filter panel ──────────────────────────────────────────────────────────────

class FilterPanel(QWidget):
    filters_changed = Signal(set, set, set)   # tiers(int), roles(str), sources(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(140)
        self.setMaximumWidth(220)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        root.addWidget(QLabel('<b>Filters</b>'))

        self._tier_sec   = _FilterSection('Tier',   [(str(t), f'Tier {t}') for t in _ALL_TIERS])
        self._role_sec   = _FilterSection('Role',   [(r, r) for r in _ALL_ROLES])
        self._source_sec = _FilterSection('Source', _ALL_SOURCES)

        for sec in (self._tier_sec, self._role_sec, self._source_sec):
            sec.changed.connect(self._emit)
            root.addWidget(sec)

        root.addStretch()

        clear_btn = QPushButton('Clear Filters')
        clear_btn.clicked.connect(self._clear)
        root.addWidget(clear_btn)

    def _emit(self) -> None:
        self.filters_changed.emit(
            {int(v) for v in self._tier_sec.get_checked()},
            self._role_sec.get_checked(),
            self._source_sec.get_checked(),
        )

    def _clear(self) -> None:
        for sec in (self._tier_sec, self._role_sec, self._source_sec):
            sec.set_all(True)
        self._emit()

    def get_filters(self) -> tuple[set, set, set]:
        return (
            {int(v) for v in self._tier_sec.get_checked()},
            self._role_sec.get_checked(),
            self._source_sec.get_checked(),
        )

    def restore(self, tiers: set[int], roles: set[str], sources: set[str]) -> None:
        self._tier_sec.restore({str(t) for t in tiers})
        self._role_sec.restore(roles)
        self._source_sec.restore(sources)
        self._emit()


# ── Adversary row ─────────────────────────────────────────────────────────────

class _AdversaryRow(QWidget):
    add_requested    = Signal(dict, int)
    edit_requested   = Signal(dict)
    expand_requested = Signal(object)   # emits self; parent handles accordion

    def __init__(self, adv: dict, encounter_open: bool = False, parent=None):
        super().__init__(parent)
        self.adv = adv
        self._expanded = False
        self._expand_built = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Row header (always visible) ───────────────────────────────────────
        self._hdr = _ClickableWidget()
        self._hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hdr.clicked.connect(lambda: self.expand_requested.emit(self))
        hbox = QHBoxLayout(self._hdr)
        hbox.setContentsMargins(4, 3, 4, 3)
        hbox.setSpacing(0)

        # Expand indicator
        self._indicator = QLabel()
        self._indicator.setFixedWidth(20)
        self._indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._indicator.setPixmap(chevron_right_icon().pixmap(16, 16))
        hbox.addWidget(self._indicator)

        # Col 1: name only (flavor moves to expanded section)
        name_text = f'<b>{html.escape(adv.get("name", ""))}</b>'
        if adv.get('homebrew'):
            name_text += ' <span style="color: grey; font-weight: normal;">(hb)</span>'
        name_lbl = QLabel(name_text)
        name_lbl.setTextFormat(Qt.TextFormat.RichText)
        name_lbl.setContentsMargins(2, 0, 8, 0)
        hbox.addWidget(name_lbl, 1)

        # Col 2: role
        role_lbl = QLabel(adv.get('role', ''))
        role_lbl.setFixedWidth(_ROLE_W)
        role_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        hbox.addWidget(role_lbl)

        # Col 3: tier
        tier_lbl = QLabel(str(adv.get('tier', '')))
        tier_lbl.setFixedWidth(_TIER_W)
        tier_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        hbox.addWidget(tier_lbl)

        # Col 4: actions
        action_w = QWidget()
        action_w.setFixedWidth(_ACTION_W)
        av = QHBoxLayout(action_w)
        av.setContentsMargins(4, 0, 4, 0)
        av.setSpacing(3)

        edit_btn = QPushButton('Edit')
        edit_btn.setFixedWidth(44)
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.adv))

        self._minus = QPushButton('−')
        self._minus.setFixedWidth(24)
        self._qty = QSpinBox()
        self._qty.setRange(1, 99)
        self._qty.setValue(1)
        self._qty.setFixedWidth(36)
        self._qty.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._plus = QPushButton('+')
        self._plus.setFixedWidth(24)
        self._add_btn = QPushButton('Add')
        self._add_btn.setFixedWidth(44)

        self._minus.clicked.connect(lambda: self._qty.setValue(max(1, self._qty.value() - 1)))
        self._plus.clicked.connect(lambda: self._qty.setValue(self._qty.value() + 1))
        self._add_btn.clicked.connect(self._on_add)

        av.addStretch()
        av.addWidget(self._minus)
        av.addWidget(self._qty)
        av.addWidget(self._plus)
        av.addWidget(self._add_btn)
        av.addWidget(edit_btn)

        hbox.addWidget(action_w)
        root.addWidget(self._hdr)

        # Placeholder for lazy-built expanded content
        self._expand_widget: QWidget | None = None
        self._root = root

        # Row separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        self.set_encounter_open(encounter_open)

    # ── Lazy expand build ─────────────────────────────────────────────────────

    def _build_expand(self) -> None:
        if self._expand_built:
            return
        self._expand_built = True
        adv = self.adv

        ew = QWidget()
        ev = QVBoxLayout(ew)
        ev.setContentsMargins(24, 4, 8, 8)
        ev.setSpacing(4)

        def _e(v) -> str:
            return html.escape(str(v)) if v else ''

        # Flavor (shown here instead of in the row header)
        flavor = (adv.get('flavor') or '').strip()
        if flavor:
            flav_lbl = QLabel(f'<i>{html.escape(flavor)}</i>')
            flav_lbl.setTextFormat(Qt.TextFormat.RichText)
            flav_lbl.setWordWrap(True)
            ev.addWidget(flav_lbl)

        # Stats frame
        stats_frame = QFrame()
        stats_frame.setStyleSheet('background-color: palette(base); border-radius: 4px;')
        stats_frame.setAutoFillBackground(True)
        sf = QVBoxLayout(stats_frame)
        sf.setContentsMargins(8, 6, 8, 6)
        sf.setSpacing(2)

        row1 = ' | '.join(
            f'<b>{k}:</b> {v}' for k, v in [
                ('Difficulty', _e(adv.get('difficulty'))),
                ('Thresholds', _e(adv.get('thresholds'))),
                ('HP',         _e(adv.get('hp'))),
                ('Stress',     _e(adv.get('stress'))),
            ] if v
        )
        if row1:
            lbl = QLabel(row1); lbl.setWordWrap(True); sf.addWidget(lbl)

        row2_parts = []
        atk    = _e(adv.get('atk'))
        weapon = html.escape(adv.get('weapon', '') or '')
        rng    = html.escape(adv.get('range', '') or '')
        dmg    = html.escape(adv.get('damage', '') or '')
        dmg_t  = html.escape(adv.get('damage_type', '') or '')
        if atk:    row2_parts.append(f'<b>ATK:</b> {atk}')
        if weapon: row2_parts.append(f'<b>{weapon}:</b> {rng}')
        elif rng:  row2_parts.append(f'<b>Range:</b> {rng}')
        if dmg:    row2_parts.append(f'{dmg} {dmg_t}'.strip())
        if row2_parts:
            lbl = QLabel(' | '.join(row2_parts)); lbl.setWordWrap(True); sf.addWidget(lbl)

        exp = _e(adv.get('experience'))
        if exp:
            lbl = QLabel(f'<b>Experience:</b> {exp}'); lbl.setWordWrap(True); sf.addWidget(lbl)

        ev.addWidget(stats_frame)

        motives = (adv.get('motives') or '').strip()
        if motives:
            lbl = QLabel(f'<b>Motives & Tactics:</b> {html.escape(motives)}')
            lbl.setWordWrap(True)
            ev.addWidget(lbl)

        feats = adv.get('features', [])
        if feats:
            ev.addWidget(QLabel('<b>FEATURES</b>'))
            feat_html = ''.join(
                f'<p style="margin:0 0 4px 0;"><b>{html.escape(f.get("name",""))}'
                f' - {html.escape(f.get("type",""))}:</b> {html.escape(f.get("desc",""))}</p>'
                for f in feats
            )
            lbl = QLabel(feat_html)
            lbl.setWordWrap(True)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            ev.addWidget(lbl)

        ew.setVisible(False)
        # Insert before the separator (last item)
        self._root.insertWidget(self._root.count() - 1, ew)
        self._expand_widget = ew

    # ── Public interface ──────────────────────────────────────────────────────

    def set_encounter_open(self, open: bool) -> None:
        self._minus.setVisible(open)
        self._qty.setVisible(open)
        self._plus.setVisible(open)
        self._add_btn.setVisible(open)

    def toggle(self) -> None:
        if self._expanded:
            self.collapse()
        else:
            self._build_expand()
            self._expanded = True
            self._expand_widget.setVisible(True)
            self._indicator.setPixmap(chevron_down_icon().pixmap(16, 16))

    def collapse(self) -> None:
        self._expanded = False
        if self._expand_widget:
            self._expand_widget.setVisible(False)
        self._indicator.setPixmap(chevron_right_icon().pixmap(16, 16))

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def _on_add(self) -> None:
        self.add_requested.emit(self.adv, self._qty.value())
        self._qty.setValue(1)


# ── Adversary table ───────────────────────────────────────────────────────────

class AdversaryTable(QWidget):
    """Search bar + sort header + scrollable list of _AdversaryRow widgets."""
    add_requested  = Signal(dict, int)
    edit_requested = Signal(dict)

    def __init__(self, adversaries: list[dict], parent=None):
        super().__init__(parent)
        self._all: list[dict] = adversaries
        self._visible: list[dict] = list(adversaries)
        self._rows: list[_AdversaryRow] = []
        self._expanded_row: _AdversaryRow | None = None
        self._encounter_open = False

        self._sort_col = 'tier'        # default sort
        self._sort_asc = True

        self._active_tiers:   set[int] = {1, 2, 3, 4}
        self._active_roles:   set[str] = set(_ALL_ROLES)
        self._active_sources: set[str] = {'official', 'homebrew'}
        self._search_text = ''

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText('Search (regex)…')
        self._search.textChanged.connect(self._on_search)
        search_wrap = QWidget()
        sl = QHBoxLayout(search_wrap)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.addWidget(self._search)
        root.addWidget(search_wrap)

        # Sort header
        hdr_widget = QWidget()
        hdr_widget.setAutoFillBackground(True)
        hdr_layout = QHBoxLayout(hdr_widget)
        hdr_layout.setContentsMargins(24, 0, 4, 0)  # 24 = 20 indicator + 4 row margin
        hdr_layout.setSpacing(0)

        self._sort_btns: dict[str, QPushButton] = {}
        name_btn = QPushButton('Name')
        name_btn.setFlat(True)
        name_btn.setStyleSheet('text-align: left; padding: 2px 8px 2px 2px;')
        name_btn.setIconSize(QSize(16, 16))
        name_btn.clicked.connect(lambda: self._set_sort('name'))
        hdr_layout.addWidget(name_btn, 1)
        self._sort_btns['name'] = name_btn

        role_btn = QPushButton('Role')
        role_btn.setFlat(True)
        role_btn.setFixedWidth(_ROLE_W)
        role_btn.setIconSize(QSize(16, 16))
        role_btn.clicked.connect(lambda: self._set_sort('role'))
        hdr_layout.addWidget(role_btn)
        self._sort_btns['role'] = role_btn

        tier_btn = QPushButton('Tier')
        tier_btn.setFlat(True)
        tier_btn.setFixedWidth(_TIER_W)
        tier_btn.setIconSize(QSize(16, 16))
        tier_btn.clicked.connect(lambda: self._set_sort('tier'))
        hdr_layout.addWidget(tier_btn)
        self._sort_btns['tier'] = tier_btn

        # Spacer matching action column width
        spacer = QWidget()
        spacer.setFixedWidth(_ACTION_W)
        hdr_layout.addWidget(spacer)

        root.addWidget(hdr_widget)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        root.addWidget(sep)

        # Scroll area for rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._container = QWidget()
        self._rows_layout = QVBoxLayout(self._container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch()
        scroll.setWidget(self._container)
        root.addWidget(scroll)

        self._update_sort_indicators()
        self._rebuild_rows()

    # ── Filtering / sorting ───────────────────────────────────────────────────

    def apply_filters(self, tiers: set[int], roles: set[str], sources: set[str]) -> None:
        self._active_tiers   = tiers
        self._active_roles   = roles
        self._active_sources = sources
        self._rebuild_rows()

    def _on_search(self, text: str) -> None:
        self._search_text = text
        try:
            re.compile(text, re.IGNORECASE)
            self._search.setStyleSheet('')
        except re.error:
            self._search.setStyleSheet('background: #5c1a1a;')
            return
        self._rebuild_rows()

    def _set_sort(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        self._update_sort_indicators()
        self._rebuild_rows()

    def _update_sort_indicators(self) -> None:
        for col, btn in self._sort_btns.items():
            if col == self._sort_col:
                btn.setIcon(chevron_up_icon() if self._sort_asc else chevron_down_icon())
            else:
                btn.setIcon(chevrons_up_down_icon())

    def _filtered_sorted(self) -> list[dict]:
        pattern = None
        if self._search_text:
            try:
                pattern = re.compile(self._search_text, re.IGNORECASE)
            except re.error:
                return []

        result = [
            a for a in self._all
            if a.get('tier') in self._active_tiers
            and a.get('role') in self._active_roles
            and ('homebrew' if a.get('homebrew') else 'official') in self._active_sources
            and (not pattern or pattern.search(a.get('name', '')))
        ]

        key = {
            'name': lambda a: (a.get('name', '').lower(), a.get('tier', 0)),
            'role': lambda a: (a.get('role', ''), a.get('tier', 0), a.get('name', '').lower()),
            'tier': lambda a: (a.get('tier', 0), a.get('name', '').lower()),
        }.get(self._sort_col, lambda a: (a.get('tier', 0), a.get('name', '').lower()))
        result.sort(key=key, reverse=not self._sort_asc)
        return result

    def _rebuild_rows(self) -> None:
        self._expanded_row = None
        # Remove old rows
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()

        filtered = self._filtered_sorted()
        stretch = self._rows_layout.takeAt(self._rows_layout.count() - 1)

        for adv in filtered:
            row = _AdversaryRow(adv, self._encounter_open)
            row.add_requested.connect(self.add_requested)
            row.edit_requested.connect(self.edit_requested)
            row.expand_requested.connect(self._on_expand_requested)
            self._rows_layout.addWidget(row)
            self._rows.append(row)

        self._rows_layout.addStretch()

    def _on_expand_requested(self, row: _AdversaryRow) -> None:
        if self._expanded_row and self._expanded_row is not row:
            self._expanded_row.collapse()
        row.toggle()
        self._expanded_row = row if row.is_expanded else None

    # ── Public interface ──────────────────────────────────────────────────────

    def set_adversaries(self, adversaries: list[dict]) -> None:
        self._all = adversaries
        self._rebuild_rows()

    def set_encounter_open(self, open: bool) -> None:
        self._encounter_open = open
        for row in self._rows:
            row.set_encounter_open(open)


# ── Combined adversary panel (filter + table) ─────────────────────────────────

class AdversaryPanel(QWidget):
    """Left main pane: narrow filter column | adversary table."""
    add_requested   = Signal(dict, int)
    edit_requested  = Signal(dict)
    filters_changed = Signal(set, set, set)   # tiers, roles, sources

    def __init__(self, adversaries: list[dict], parent=None):
        super().__init__(parent)

        self._filter_panel = FilterPanel()
        self._table        = AdversaryTable(adversaries)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._filter_panel)
        splitter.addWidget(self._table)
        splitter.setSizes([180, 9999])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(splitter)

        self._filter_panel.filters_changed.connect(self._table.apply_filters)
        self._filter_panel.filters_changed.connect(self.filters_changed)
        self._table.add_requested.connect(self.add_requested)
        self._table.edit_requested.connect(self.edit_requested)

    @property
    def filter_panel(self) -> FilterPanel:
        return self._filter_panel

    def set_adversaries(self, adversaries: list[dict]) -> None:
        self._table.set_adversaries(adversaries)

    def set_encounter_open(self, open: bool) -> None:
        self._table.set_encounter_open(open)
