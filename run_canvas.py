#!/usr/bin/env python3
"""run_canvas.py — Run-mode canvas widgets (circle trackers, flow layout, adversary cards)."""

from PySide6.QtCore import Qt, QRect, QSize, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QLayoutItem,
    QSizePolicy, QVBoxLayout, QWidget,
)

_CARD_MIN_W = 300
_CARD_MAX_W = 480


# ── Circle tracker ────────────────────────────────────────────────────────────

class _CircleTracker(QWidget):
    """A row of N clickable circles for tracking spent HP or stress.

    Click an empty circle → fill it and everything to the left.
    Click a filled circle → clear it and everything to the right.
    """
    changed = Signal()

    _D   = 14   # circle diameter (px)
    _GAP =  3   # gap between circles (px)

    def __init__(self, total: int, parent=None):
        super().__init__(parent)
        self._total  = max(0, total)
        self._filled = 0
        step = self._D + self._GAP
        w    = self._total * step - (self._GAP if self._total else 0)
        self.setFixedSize(max(w, 1), self._D + 4)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        if not self._total:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        step = self._D + self._GAP
        for i in range(self._total):
            p.setBrush(QBrush(QColor('#b03030') if i < self._filled else QColor('#3a3a3a')))
            p.setPen(QPen(QColor('#888888'), 1))
            p.drawEllipse(QRect(i * step, 2, self._D, self._D))
        p.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._total:
            x    = int(event.position().x())
            step = self._D + self._GAP
            for i in range(self._total):
                if i * step <= x < i * step + self._D:
                    self._filled = i if i < self._filled else i + 1
                    self.update()
                    self.changed.emit()
                    break
        super().mousePressEvent(event)

    @property
    def filled(self) -> int:
        return self._filled

    def set_filled(self, n: int) -> None:
        self._filled = max(0, min(n, self._total))
        self.update()


# ── Flow container ────────────────────────────────────────────────────────────

class _FlowContainer(QWidget):
    """QWidget that reports the correct height-for-width to its QScrollArea parent."""

    def hasHeightForWidth(self) -> bool:
        lay = self.layout()
        return lay is not None and lay.hasHeightForWidth()

    def heightForWidth(self, w: int) -> int:
        lay = self.layout()
        return lay.heightForWidth(w) if lay and lay.hasHeightForWidth() else super().heightForWidth(w)

    def sizeHint(self) -> QSize:
        lay = self.layout()
        if lay and lay.hasHeightForWidth():
            return QSize(self.width(), lay.heightForWidth(self.width()))
        return super().sizeHint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.updateGeometry()


# ── Flow layout ───────────────────────────────────────────────────────────────

class _FlowLayout(QLayout):
    """Left-to-right wrapping layout that reflows cards on resize."""

    def __init__(self, parent=None, h_spacing: int = 8, v_spacing: int = 8):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_gap = h_spacing
        self._v_gap = v_spacing

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test=True)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        m  = self.contentsMargins()
        sz = QSize()
        for item in self._items:
            sz = sz.expandedTo(item.minimumSize())
        return sz + QSize(m.left() + m.right(), m.top() + m.bottom())

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test=False)

    def _do_layout(self, rect: QRect, test: bool) -> int:
        m          = self.contentsMargins()
        left       = rect.x() + m.left()
        top        = rect.y() + m.top()
        right_edge = rect.right() - m.right()
        x, y, row_h = left, top, 0

        for item in self._items:
            hint    = item.sizeHint()
            iw, ih  = hint.width(), hint.height()
            if x + iw > right_edge and x > left:
                x, y, row_h = left, y + row_h + self._v_gap, 0
            if not test:
                item.setGeometry(QRect(x, y, iw, ih))
            x    += iw + self._h_gap
            row_h = max(row_h, ih)

        return y + row_h - rect.y() + m.bottom()


# ── Card helpers ──────────────────────────────────────────────────────────────

def _parse_bubbles(val) -> int | None:
    if val is None:
        return None
    try:
        n = int(str(val).strip().lstrip('+'))
        return n if 1 <= n <= 20 else None
    except ValueError:
        return None


def _hsep(parent=None) -> QFrame:
    f = QFrame(parent)
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


def _lbl(text: str, *, bold=False, pt=9, color='', wrap=False, rich=False,
         indent=0) -> QLabel:
    w = QLabel(text)
    f = QFont()
    f.setPointSize(pt)
    f.setBold(bold)
    w.setFont(f)
    if color:
        w.setStyleSheet(f'color: {color};')
    if wrap:
        w.setWordWrap(True)
    if rich:
        w.setTextFormat(Qt.TextFormat.RichText)
    if indent:
        w.setContentsMargins(indent, 0, 0, 0)
    return w


# ── Adversary run card ────────────────────────────────────────────────────────

class RunAdversaryCard(QFrame):
    """Full adversary card with interactive HP / stress trackers."""
    state_changed = Signal()

    def __init__(self, adv: dict, count: int, instance_states: list[dict], parent=None):
        super().__init__(parent)
        self._adv   = adv
        self._count = count
        self._hp_trackers: list[_CircleTracker | None] = []
        self._st_trackers: list[_CircleTracker | None] = []

        self.setMinimumWidth(_CARD_MIN_W)
        self.setMaximumWidth(_CARD_MAX_W)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(3)

        root.addWidget(_lbl(adv.get('name', '?'), bold=True, pt=12))

        tier     = adv.get('tier', '?')
        role     = adv.get('role', '')
        hq       = (adv.get('horde_qty') or '').strip()
        tier_str = f"Tier {tier} {role}".strip() + (f" ({hq}/HP)" if hq else '')
        root.addWidget(_lbl(tier_str, pt=8, color='#999999'))

        root.addWidget(_hsep())

        flavor = (adv.get('flavor') or '').strip()
        if flavor:
            root.addWidget(_lbl(f'<i>{flavor}</i>', pt=8, color='#cccccc', wrap=True, rich=True))

        motives = (adv.get('motives') or '').strip()
        if motives:
            root.addWidget(_lbl(f'<b>Motives & Tactics:</b> {motives}',
                                pt=8, color='#999999', wrap=True, rich=True))

        weapon = (adv.get('weapon') or '').strip()
        rng    = (adv.get('range') or '').strip()
        dmg    = (adv.get('damage') or '').strip()
        dmg_t  = (adv.get('damage_type') or '').strip()
        if weapon:
            right   = ' — '.join(s for s in [rng, f"{dmg} {dmg_t}".strip() if dmg else ''] if s)
            wpn_str = f"<b>{weapon}: {right}</b>" if right else f"<b>{weapon}</b>"
        elif rng and dmg:
            wpn_str = f"<b>{rng} — {dmg} {dmg_t}".strip() + '</b>'
        else:
            wpn_str = ''
        if wpn_str:
            root.addWidget(_lbl(wpn_str, pt=9, wrap=True, rich=True))

        atk    = adv.get('atk') or '—'
        hp     = adv.get('hp') or '—'
        thresh = adv.get('thresholds') or '—'
        diff   = adv.get('difficulty') or '—'
        stress = adv.get('stress') or '—'

        r1 = QHBoxLayout(); r1.setSpacing(8)
        r1.addWidget(_lbl(f'<b>ATK:</b> {atk}', pt=9, rich=True), 1)
        r1.addWidget(_lbl(f'<b>HP:</b> {hp}  <b>Thresholds:</b> {thresh}', pt=9, rich=True), 2)
        root.addLayout(r1)

        r2 = QHBoxLayout(); r2.setSpacing(8)
        r2.addWidget(_lbl(f'<b>Difficulty:</b> {diff}', pt=9, rich=True), 1)
        r2.addWidget(_lbl(f'<b>Stress:</b> {stress}', pt=9, rich=True), 2)
        root.addLayout(r2)

        exp = (adv.get('experience') or '').strip()
        if exp:
            root.addWidget(_lbl(f'Experience: {exp}', pt=8, color='#999999'))

        features = adv.get('features', [])
        if features:
            root.addWidget(_lbl('FEATURES', pt=8, bold=True, color='#888888'))
            root.addWidget(_hsep())
            for feat in features:
                fname = feat.get('name', '')
                ftype = feat.get('type', '')
                desc  = feat.get('desc', '')
                hdr   = f"<b>{fname} — {ftype}:</b>" if ftype else f"<b>{fname}:</b>"
                root.addWidget(_lbl(hdr, pt=9, rich=True))
                if desc:
                    root.addWidget(_lbl(desc, pt=8, wrap=True, indent=8))

        root.addWidget(_hsep())

        hp_n     = _parse_bubbles(adv.get('hp'))
        stress_n = _parse_bubbles(adv.get('stress'))
        adv_name = adv.get('name', '')

        for i in range(count):
            inst = instance_states[i] if i < len(instance_states) else {}

            label_text = f"{adv_name} #{i + 1}" if count > 1 else adv_name
            root.addWidget(_lbl(f'<b>{label_text}</b>', pt=9, rich=True))

            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(_lbl('HP:', pt=9))

            if hp_n:
                hp_t = _CircleTracker(hp_n)
                hp_t.set_filled(inst.get('hp_spent', 0))
                hp_t.changed.connect(self.state_changed)
                row.addWidget(hp_t)
                self._hp_trackers.append(hp_t)
            else:
                row.addWidget(_lbl(str(adv.get('hp') or '?'), pt=9))
                self._hp_trackers.append(None)

            row.addSpacing(12)
            row.addWidget(_lbl('Stress:', pt=9))

            if stress_n:
                st_t = _CircleTracker(stress_n)
                st_t.set_filled(inst.get('stress_spent', 0))
                st_t.changed.connect(self.state_changed)
                row.addWidget(st_t)
                self._st_trackers.append(st_t)
            else:
                row.addWidget(_lbl(str(adv.get('stress') or '?'), pt=9))
                self._st_trackers.append(None)

            row.addStretch()
            root.addLayout(row)

            if i < count - 1:
                root.addWidget(_hsep())

    def get_instance_states(self) -> list[dict]:
        return [
            {
                'hp_spent':     (self._hp_trackers[i].filled if self._hp_trackers[i] else 0),
                'stress_spent': (self._st_trackers[i].filled if self._st_trackers[i] else 0),
            }
            for i in range(self._count)
        ]
