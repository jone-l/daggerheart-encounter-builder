#!/usr/bin/env python3
"""print_encounter.py — Daggerheart Encounter Builder — A4 two-column print renderer."""

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPainter, QPageLayout, QPageSize, QPen,
)
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QMessageBox, QWidget


_MARGIN_MM     = 12.0
_COL_GAP_MM    =  6.0
_PAD_MM        =  3.0
_SEP_V_MM      =  1.5   # vertical space on each side of a separator line
_BUBBLE_MM     =  2.8
_BUBBLE_GAP_MM =  0.6
_CARD_GAP_MM   =  3.0
_LINE_SPACING  =  1.3

_BLACK  = QColor('#111111')
_GREY   = QColor('#777777')
_DGREY  = QColor('#aaaaaa')   # dotted separator / FEATURES label


def _px(mm: float, dpi: int) -> float:
    return mm * dpi / 25.4


class _Renderer:

    def __init__(self, state: dict, printer: QPrinter):
        self._state = state
        self._pr    = printer
        self._dpi   = printer.resolution()

        def p(mm): return _px(mm, self._dpi)

        self._pad      = p(_PAD_MM)
        self._sep_v    = p(_SEP_V_MM)
        self._bub_d    = p(_BUBBLE_MM)
        self._bub_gap  = p(_BUBBLE_GAP_MM)
        self._card_gap = p(_CARD_GAP_MM)

        rect = printer.pageRect(QPrinter.Unit.DevicePixel)
        self._page_w  = rect.width()
        self._page_h  = rect.height()
        self._col_gap = p(_COL_GAP_MM)
        self._col_w   = (self._page_w - self._col_gap) / 2
        self._col_x   = [0.0, self._col_w + self._col_gap]

        # ── Fonts ─────────────────────────────────────────────────────────────
        f_flavor = QFont('Arial', 8)
        f_flavor.setItalic(True)

        self._f_enc   = QFont('Georgia', 14, QFont.Weight.Bold)
        self._f_name  = QFont('Arial', 13, QFont.Weight.Bold)
        self._f_tier  = QFont('Arial', 9)
        self._f_flav  = f_flavor
        self._f_grey  = QFont('Arial', 8)
        self._f_wpn   = QFont('Arial', 9, QFont.Weight.Bold)
        self._f_stats = QFont('Arial', 9)
        self._f_fhdr  = QFont('Arial', 8, QFont.Weight.Bold)
        self._f_fname = QFont('Arial', 9, QFont.Weight.Bold)
        self._f_fdesc = QFont('Arial', 8)
        self._f_tname = QFont('Arial', 9, QFont.Weight.Bold)
        self._f_row   = QFont('Arial', 9)

        # ── Metrics against printer device ────────────────────────────────────
        self._fm_enc   = QFontMetricsF(self._f_enc,   printer)
        self._fm_name  = QFontMetricsF(self._f_name,  printer)
        self._fm_tier  = QFontMetricsF(self._f_tier,  printer)
        self._fm_flav  = QFontMetricsF(self._f_flav,  printer)
        self._fm_grey  = QFontMetricsF(self._f_grey,  printer)
        self._fm_wpn   = QFontMetricsF(self._f_wpn,   printer)
        self._fm_stats = QFontMetricsF(self._f_stats, printer)
        self._fm_fhdr  = QFontMetricsF(self._f_fhdr,  printer)
        self._fm_fname = QFontMetricsF(self._f_fname, printer)
        self._fm_fdesc = QFontMetricsF(self._f_fdesc, printer)
        self._fm_tname = QFontMetricsF(self._f_tname, printer)
        self._fm_row   = QFontMetricsF(self._f_row,   printer)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _lh(self, fm: QFontMetricsF) -> float:
        return fm.height() * _LINE_SPACING

    def _wrap(self, text: str, width: float, fm: QFontMetricsF) -> list[str]:
        if not text or not text.strip():
            return []
        words = text.split()
        lines, cur = [], ''
        for word in words:
            candidate = (cur + ' ' + word).strip()
            if fm.horizontalAdvance(candidate) <= width:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines or ['']

    def _parse_bubbles(self, val) -> int | None:
        if val is None:
            return None
        try:
            n = int(str(val).strip().lstrip('+'))
            return n if 1 <= n <= 20 else None
        except ValueError:
            return None

    def _sep_h(self) -> float:
        return self._sep_v * 2

    def _row_h(self) -> float:
        return max(self._bub_d + _px(2.0, self._dpi), self._lh(self._fm_row))

    # ── Height calculation ─────────────────────────────────────────────────────

    def _card_h(self, adv: dict, count: int) -> float:
        inner_w = self._col_w - self._pad * 2
        h = self._pad

        h += self._lh(self._fm_name)                  # name (large bold)
        h += self._lh(self._fm_tier)                  # tier / type
        h += self._sep_h()                            # separator

        flavor = (adv.get('flavor') or '').strip()
        if flavor:
            h += len(self._wrap(flavor, inner_w, self._fm_flav)) * self._lh(self._fm_flav)
            h += self._pad * 0.3

        motives = (adv.get('motives') or '').strip()
        if motives:
            mt = f"Motives & Tactics: {motives}"
            h += len(self._wrap(mt, inner_w, self._fm_grey)) * self._lh(self._fm_grey)
            h += self._pad * 0.3

        weapon = (adv.get('weapon') or '').strip()
        rng    = (adv.get('range') or '').strip()
        dmg    = (adv.get('damage') or '').strip()
        if weapon or (rng and dmg):
            h += self._lh(self._fm_wpn)

        h += self._lh(self._fm_stats) * 2            # 2-row stats grid

        exp = (adv.get('experience') or '').strip()
        if exp:
            h += self._lh(self._fm_grey)

        h += self._lh(self._fm_fhdr) + self._sep_h() # FEATURES + dotted sep

        for feat in adv.get('features', []):
            h += self._lh(self._fm_fname)
            h += len(self._wrap(feat.get('desc', ''), inner_w - self._pad, self._fm_fdesc)) * self._lh(self._fm_fdesc)
            h += self._pad * 0.4

        h += self._sep_h()                            # separator before tracker rows

        row_h = self._row_h()
        for i in range(count):
            h += self._lh(self._fm_tname)             # individual name
            h += row_h                                 # HP / Stress bubbles
            if i < count - 1:
                h += self._sep_h()                    # between individuals

        h += self._pad
        return h

    # ── Drawing ────────────────────────────────────────────────────────────────

    def _txt(self, p: QPainter, font: QFont, color: QColor,
             x: float, y: float, w: float, h: float, text: str,
             flags=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft) -> None:
        p.setFont(font)
        p.setPen(color)
        p.drawText(QRectF(x, y, w, h), flags, text)

    def _full_sep(self, p: QPainter, x: float, y: float, dotted: bool = False) -> float:
        """Draw a separator; solid ones span the full card width, dotted ones are padded."""
        line_y = y + self._sep_v
        pen = QPen(_DGREY if dotted else QColor('#222222'), max(1, _px(0.3, self._dpi)))
        if dotted:
            pen.setStyle(Qt.PenStyle.DotLine)
            x0, x1 = x + self._pad, x + self._col_w - self._pad
        else:
            x0, x1 = x, x + self._col_w
        p.setPen(pen)
        p.drawLine(QPointF(x0, line_y), QPointF(x1, line_y))
        return y + self._sep_h()

    def _bubbles(self, p: QPainter, x: float, cy: float, row_h: float, n: int) -> float:
        by = cy + (row_h - self._bub_d) / 2
        p.setPen(QPen(_BLACK, max(1, _px(0.35, self._dpi))))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(n):
            bx = x + i * (self._bub_d + self._bub_gap)
            p.drawEllipse(QRectF(bx, by, self._bub_d, self._bub_d))
        return x + n * (self._bub_d + self._bub_gap)

    def _draw_card(self, p: QPainter, adv: dict, count: int, col: int, cy: float) -> None:
        x       = self._col_x[col]
        h       = self._card_h(adv, count)
        inner_w = self._col_w - self._pad * 2
        thin    = max(1, _px(0.3, self._dpi))

        # Card border
        p.setPen(QPen(QColor('#222222'), thin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(x, cy, self._col_w, h), _px(1.5, self._dpi), _px(1.5, self._dpi))

        y = cy + self._pad

        # ── Name (large bold) ─────────────────────────────────────────────────
        self._txt(p, self._f_name, _BLACK,
                  x + self._pad, y, inner_w, self._lh(self._fm_name),
                  adv.get('name', '?'))
        y += self._lh(self._fm_name)

        # ── Tier / type ───────────────────────────────────────────────────────
        tier      = adv.get('tier', '?')
        role      = adv.get('role', '')
        horde_qty = (adv.get('horde_qty') or '').strip()
        tier_str  = f"Tier {tier} {role}".strip()
        if horde_qty:
            tier_str += f" ({horde_qty}/HP)"
        self._txt(p, self._f_tier, _GREY,
                  x + self._pad, y, inner_w, self._lh(self._fm_tier), tier_str)
        y += self._lh(self._fm_tier)

        # ── Separator ─────────────────────────────────────────────────────────
        y = self._full_sep(p, x, y)

        # ── Flavor (italic) ───────────────────────────────────────────────────
        flavor = (adv.get('flavor') or '').strip()
        if flavor:
            for line in self._wrap(flavor, inner_w, self._fm_flav):
                self._txt(p, self._f_flav, _BLACK,
                          x + self._pad, y, inner_w, self._lh(self._fm_flav), line)
                y += self._lh(self._fm_flav)
            y += self._pad * 0.3

        # ── Motives & Tactics (grey) ──────────────────────────────────────────
        motives = (adv.get('motives') or '').strip()
        if motives:
            for line in self._wrap(f"Motives & Tactics: {motives}", inner_w, self._fm_grey):
                self._txt(p, self._f_grey, _GREY,
                          x + self._pad, y, inner_w, self._lh(self._fm_grey), line)
                y += self._lh(self._fm_grey)
            y += self._pad * 0.3

        # ── Weapon (bold): "<weapon>: <range> — <damage> <type>" ─────────────
        weapon = (adv.get('weapon') or '').strip()
        rng    = (adv.get('range') or '').strip()
        dmg    = (adv.get('damage') or '').strip()
        dmg_t  = (adv.get('damage_type') or '').strip()
        wpn_str = ''
        if weapon:
            right = ' — '.join(s for s in [rng, f"{dmg} {dmg_t}".strip() if dmg else ''] if s)
            wpn_str = f"{weapon}: {right}" if right else weapon
        elif rng and dmg:
            wpn_str = f"{rng} — {dmg} {dmg_t}".strip()
        if wpn_str:
            self._txt(p, self._f_wpn, _BLACK,
                      x + self._pad, y, inner_w, self._lh(self._fm_wpn), wpn_str)
            y += self._lh(self._fm_wpn)

        # ── Stats 2×2 grid ────────────────────────────────────────────────────
        left_w = inner_w * 0.38
        right_w = inner_w - left_w
        lx = x + self._pad
        rx = lx + left_w
        sh = self._lh(self._fm_stats)

        atk    = adv.get('atk') or '—'
        hp     = adv.get('hp') or '—'
        thresh = adv.get('thresholds') or '—'
        diff   = adv.get('difficulty') or '—'
        stress = adv.get('stress') or '—'

        self._txt(p, self._f_stats, _BLACK, lx, y, left_w,  sh, f"ATK: {atk}")
        self._txt(p, self._f_stats, _BLACK, rx, y, right_w, sh, f"HP: {hp}     Thresholds: {thresh}")
        y += sh
        self._txt(p, self._f_stats, _BLACK, lx, y, left_w,  sh, f"Difficulty: {diff}")
        self._txt(p, self._f_stats, _BLACK, rx, y, right_w, sh, f"Stress: {stress}")
        y += sh

        # ── Experience (grey) ─────────────────────────────────────────────────
        exp = (adv.get('experience') or '').strip()
        if exp:
            self._txt(p, self._f_grey, _GREY,
                      x + self._pad, y, inner_w, self._lh(self._fm_grey),
                      f"Experience: {exp}")
            y += self._lh(self._fm_grey)

        # ── FEATURES + dotted separator ───────────────────────────────────────
        self._txt(p, self._f_fhdr, _DGREY,
                  x + self._pad, y, inner_w, self._lh(self._fm_fhdr), 'FEATURES')
        y += self._lh(self._fm_fhdr)
        y = self._full_sep(p, x, y, dotted=True)

        # ── Feature list ──────────────────────────────────────────────────────
        for feat in adv.get('features', []):
            fname    = feat.get('name', '')
            ftype    = feat.get('type', '')
            desc     = feat.get('desc', '')
            feat_hdr = f"{fname} — {ftype}:" if ftype else f"{fname}:"

            self._txt(p, self._f_fname, _BLACK,
                      x + self._pad, y, inner_w, self._lh(self._fm_fname), feat_hdr)
            y += self._lh(self._fm_fname)

            for line in self._wrap(desc, inner_w - self._pad, self._fm_fdesc):
                self._txt(p, self._f_fdesc, _BLACK,
                          x + self._pad * 2, y, inner_w - self._pad, self._lh(self._fm_fdesc), line)
                y += self._lh(self._fm_fdesc)
            y += self._pad * 0.4

        # ── Separator before tracker rows ─────────────────────────────────────
        y = self._full_sep(p, x, y)

        # ── Individual tracker rows ───────────────────────────────────────────
        hp_n     = self._parse_bubbles(adv.get('hp'))
        stress_n = self._parse_bubbles(adv.get('stress'))
        row_h    = self._row_h()
        adv_name = adv.get('name', '')

        for i in range(count):
            # Name in bold; append #N only when there are multiple
            tname = f"{adv_name} #{i + 1}" if count > 1 else adv_name
            self._txt(p, self._f_tname, _BLACK,
                      x + self._pad, y, inner_w, self._lh(self._fm_tname), tname)
            y += self._lh(self._fm_tname)

            # "HP: ○○○    Stress: ○○"
            rx_pos = x + self._pad

            lbl_hp = 'HP: '
            p.setFont(self._f_row)
            p.setPen(_BLACK)
            lw = self._fm_row.horizontalAdvance(lbl_hp)
            p.drawText(QRectF(rx_pos, y, lw, row_h), Qt.AlignmentFlag.AlignVCenter, lbl_hp)
            rx_pos += lw

            if hp_n:
                rx_pos = self._bubbles(p, rx_pos, y, row_h, hp_n)
            else:
                txt = str(adv.get('hp') or '?')
                tw = self._fm_row.horizontalAdvance(txt)
                self._txt(p, self._f_row, _BLACK, rx_pos, y, tw, row_h, txt)
                rx_pos += tw

            lbl_st = '    Stress: '
            p.setFont(self._f_row)
            p.setPen(_BLACK)
            lw = self._fm_row.horizontalAdvance(lbl_st)
            p.drawText(QRectF(rx_pos, y, lw, row_h), Qt.AlignmentFlag.AlignVCenter, lbl_st)
            rx_pos += lw

            if stress_n:
                self._bubbles(p, rx_pos, y, row_h, stress_n)
            else:
                txt = str(adv.get('stress') or '?')
                self._txt(p, self._f_row, _BLACK, rx_pos, y, self._col_w, row_h, txt)

            y += row_h

            # Full-width separator between individuals (not after the last)
            if i < count - 1:
                y = self._full_sep(p, x, y)

    # ── Page layout ───────────────────────────────────────────────────────────

    def render(self, p: QPainter) -> None:
        entries  = [e for e in self._state.get('entries', []) if e.get('adversary')]
        enc_name = (self._state.get('name') or '').strip()

        # Encounter title at top of first page
        start_y = 0.0
        if enc_name:
            enc_lh = self._lh(self._fm_enc)
            self._txt(p, self._f_enc, _BLACK,
                      0, 0, self._page_w, enc_lh, enc_name,
                      Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            start_y = enc_lh + _px(5.0, self._dpi)

        # Track each column's current Y independently so cards can fill gaps in
        # whichever column has the most remaining space, rather than a strict
        # left-then-right sequential pass that strands small cards on new pages.
        col_y = [start_y, start_y]

        for entry in entries:
            adv   = entry.get('adversary', {})
            count = max(1, entry.get('count', 1))
            if not adv:
                continue

            card_h = self._card_h(adv, count)

            # Pick the column with the most remaining space that still fits the card.
            # Ties go to column 0 so the left column fills naturally first.
            best_col   = None
            best_space = -1.0
            for col in [0, 1]:
                space = self._page_h - col_y[col]
                if space >= card_h and space > best_space:
                    best_col   = col
                    best_space = space

            if best_col is None:
                # Card fits in neither column: start a new page
                self._pr.newPage()
                col_y   = [0.0, 0.0]
                start_y = 0.0
                best_col = 0

            self._draw_card(p, adv, count, best_col, col_y[best_col])
            col_y[best_col] += card_h + self._card_gap


# ── Public entry point ────────────────────────────────────────────────────────

def print_encounter(state: dict, parent: QWidget = None) -> None:
    """Show a print-preview dialog for the given encounter state dict."""
    if not state.get('entries'):
        QMessageBox.information(parent, 'Print', 'Add some adversaries to the encounter first.')
        return

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageLayout(QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Portrait,
        QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
        QPageLayout.Unit.Millimeter,
    ))

    def _do_render(pr: QPrinter) -> None:
        renderer = _Renderer(state, pr)
        painter  = QPainter(pr)
        try:
            renderer.render(painter)
        finally:
            painter.end()

    dlg = QPrintPreviewDialog(printer, parent)
    dlg.paintRequested.connect(_do_render)
    dlg.exec()
