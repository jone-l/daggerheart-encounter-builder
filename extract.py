#!/usr/bin/env python3
"""
extract.py — Extract adversary and environment stat blocks from the
Daggerheart Core Rulebook PDF into adversaries.json and environments.json.

Usage (manifest mode — default):
    python extract.py
    Place the PDF in sources/, list it in sources.json with page ranges,
    and the script finds it automatically.

Usage (standalone mode):
    python extract.py --pdf sources/rulebook.pdf \
                      --adv-pages 211 240 \
                      --env-pages 244 252 \
                      [--out path/to/output/dir]

    --adv-pages  START END   1-indexed PDF page range for adversary stat blocks (inclusive)
    --env-pages  START END   1-indexed PDF page range for environment stat blocks (inclusive)
    --out        DIR         Output directory (default: ./datastore/)

Requires: pdfplumber  (pip install pdfplumber)
"""

import re
import sys
import json
import argparse
from pathlib import Path

import pdfplumber

MANIFEST_FILE = Path(__file__).parent / 'sources.json'
SOURCES_DIR   = Path(__file__).parent / 'sources'
DATASTORE     = Path(__file__).parent / 'datastore'


def load_source() -> tuple[dict, Path]:
    """Read sources.json; return (source_entry, pdf_path) for the first PDF found in sources/."""
    if not MANIFEST_FILE.exists():
        sys.exit(f'Error: manifest not found: {MANIFEST_FILE}')
    with MANIFEST_FILE.open(encoding='utf-8') as f:
        manifest = json.load(f)
    for source in manifest.get('sources', []):
        pdf_path = SOURCES_DIR / source['filename']
        if pdf_path.exists():
            return source, pdf_path
    names = [s['filename'] for s in manifest.get('sources', [])]
    sys.exit(
        f'Error: no matching PDF found in {SOURCES_DIR}/\n'
        f'Expected one of: {", ".join(names)}'
    )


# ── text cleanup ──────────────────────────────────────────────────────────────

# Ligature characters extracted by pdfplumber often leave a trailing space
# before the continuation: "Diffi culty" -> "Difficulty", "fl ying" -> "flying"
_LIGATURE_FIXES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'ffi (?=[a-z])'), 'ffi'),
    (re.compile(r'fi (?=[a-z])'),  'fi'),
    (re.compile(r'fl (?=[a-z])'),  'fl'),
    (re.compile(r'ff (?=[a-z])'),  'ff'),
]
_FOOTER = re.compile(r'\nChapter \d+:.*$', re.MULTILINE)


def clean_text(t: str) -> str:
    if not t:
        return ''
    # Normalize typographic characters to ASCII equivalents
    t = t.replace('−', '-')   # MINUS SIGN
    t = t.replace('–', '-')   # EN DASH
    t = t.replace('—', '--')  # EM DASH
    t = t.replace('’', "'")  # RIGHT SINGLE QUOTATION MARK
    t = t.replace('“', '"')  # LEFT DOUBLE QUOTATION MARK
    t = t.replace('”', '"')  # RIGHT DOUBLE QUOTATION MARK
    for pat, rep in _LIGATURE_FIXES:
        t = pat.sub(rep, t)
    return t


def strip_footer(t: str) -> str:
    return _FOOTER.sub('', t).strip()


# ── column extraction ─────────────────────────────────────────────────────────

def get_columns(page) -> tuple[str, str]:
    """Crop page into left / right halves and return cleaned text for each."""
    w = page.width
    left  = page.crop((0,       0, w * 0.50, page.height)).extract_text() or ''
    right = page.crop((w * 0.50, 0, w,       page.height)).extract_text() or ''
    return clean_text(left), clean_text(right)


# ── shared patterns ───────────────────────────────────────────────────────────

# Tier die glyphs sit in Unicode Private Use Area; we track tier from headers.
_PUA = r'[-]'

# PUA digit glyphs used in Horde quantity notation (x/HP).
# Confirmed: =0, =1, =2, =3, =5.
# Pattern: digit n (1-9) = chr(0xe540 + n); 0 = chr(0xe53f).
_PUA_DIGITS: dict[str, str] = {chr(0xe53f): '0'} | {chr(0xe540 + n): str(n) for n in range(1, 10)}


def _decode_pua_qty(s: str) -> int | None:
    """Decode PUA digit chars to an integer, e.g. '\\ue541\\ue53f' -> 10."""
    digits = ''.join(_PUA_DIGITS.get(c, '') for c in s)
    return int(digits) if digits else None


def _decode_pua_digits_in(s: str) -> str:
    """Replace any PUA digit glyphs in s with their ASCII digit equivalents."""
    return ''.join(_PUA_DIGITS.get(c, c) for c in s)


_TIER_HDR  = re.compile(r'^TIER\s+(\d)\s+(?:ADVERSARIES|ENVIRONMENTS)', re.I)
_TIER_ROLE = re.compile(rf'^Tier\s+{_PUA}\s+(.+)$')
_NAME_LINE = re.compile(r"^[A-Z][A-Z0-9\s'\-\.\:]+$")  # ALL-CAPS name line (colons for e.g. FALLEN WARLORD:)
_FEAT_HDR  = re.compile(r'^(.+?)\s+-\s+(Passive|Action|Reaction):\s*', re.MULTILINE)


def _is_name(s: str) -> bool:
    """True if the line looks like an adversary/environment name (all-caps)."""
    s = s.strip()
    return (
        bool(_NAME_LINE.match(s))
        and not s.endswith('::')   # exclude decorative page-bottom labels
        and s not in ('FEATURES',)
        and not _TIER_HDR.match(s)
    )


def split_into_blocks(text: str) -> list[str]:
    """
    Split a single column's text into individual stat-block chunks.

    A new block starts at the first ALL-CAPS line (possibly followed by more
    ALL-CAPS continuation lines for multi-word names) whose next non-name line
    is a Tier line.  This avoids false positives from decorative name labels
    that appear at page bottoms without an accompanying Tier line.
    """
    lines = text.splitlines()
    starts: list[int] = []

    i = 0
    while i < len(lines):
        if not _is_name(lines[i].strip()):
            i += 1
            continue
        # Advance through consecutive ALL-CAPS lines (multi-word names)
        j = i + 1
        while j < len(lines) and _is_name(lines[j].strip()):
            j += 1
        # The first non-name line must be a Tier line to confirm a new block
        if j < len(lines) and _TIER_ROLE.match(lines[j].strip()):
            # Find the true name start: work back from the Tier line.
            # A two-part name (e.g. 'FALLEN WARLORD:\nREALM-BREAKER') has
            # the preceding line ending with ':'. Anything before that is
            # decorative section headers and should be discarded.
            name_start = j - 1
            if name_start > i and lines[name_start - 1].strip().endswith(':'):
                name_start -= 1
            starts.append(name_start)
            i = j + 1  # skip past all name lines and the Tier line
        else:
            i += 1

    blocks: list[str] = []
    for k, s in enumerate(starts):
        e = starts[k + 1] if k + 1 < len(starts) else len(lines)
        blocks.append('\n'.join(lines[s:e]))
    return blocks


# ── feature parsing ───────────────────────────────────────────────────────────

def parse_features(text: str) -> list[dict]:
    """Parse a block of feature text into a list of {name, type, desc}."""
    text = strip_footer(text)
    parts = _FEAT_HDR.split(text)
    features: list[dict] = []
    i = 1
    while i + 2 <= len(parts):
        name  = _decode_pua_digits_in(parts[i].strip())
        ftype = parts[i + 1].strip()
        raw   = strip_footer(parts[i + 2]) if i + 2 < len(parts) else ''
        desc  = ' '.join(ln.strip() for ln in raw.splitlines() if ln.strip())
        if name and ftype:
            features.append({'name': name, 'type': ftype, 'desc': desc})
        i += 3
    return features


# ── adversary parsing ─────────────────────────────────────────────────────────

_STAT = re.compile(
    r'Difficulty:\s*(\d+)\s*\|\s*Thresholds?:\s*([^\|]+?)\s*\|\s*HP:\s*(\d+)\s*\|\s*Stress:\s*(\d+)',
    re.I,
)
_ATK = re.compile(
    r'ATK:\s*([+\-]?(?:\d+d\d+|\d+))\s*\|\s*(.+?):\s*([^|]+?)\s*\|\s*(.+?)\s+(phy(?:/mag)?|mag)\s*$',
    re.I,
)
_EXP = re.compile(r'^Experience:\s*(.+)$', re.I)


def parse_adversary(block: str, tier: int) -> dict | None:
    lines = [
        l for l in block.splitlines()
        if l.strip() and not l.strip().startswith('Chapter')
    ]
    if not lines:
        return None

    adv: dict = {
        'name': '', 'tier': tier, 'role': '',
        'flavor': '', 'motives': '',
        'weapon': '', 'range': '', 'damage': '', 'damage_type': '',
        'atk': '', 'difficulty': '', 'thresholds': '',
        'hp': 0, 'stress': 0,
        'experience': None, 'horde_qty': None, 'features': [],
    }

    i = 0

    # Name: join consecutive ALL-CAPS lines (handles multi-word names)
    name_parts: list[str] = []
    while i < len(lines) and _is_name(lines[i].strip()):
        candidate = lines[i].strip()
        # Skip if this line is just the previous parts joined (PDF layout artifact)
        if name_parts and candidate == ' '.join(name_parts):
            i += 1
            continue
        name_parts.append(candidate)
        i += 1
    adv['name'] = ' '.join(name_parts).title()

    # Tier / Role  e.g. "Tier ⚄ Horde (/HP)"
    if i < len(lines) and _TIER_ROLE.match(lines[i].strip()):
        role_raw = _TIER_ROLE.match(lines[i].strip()).group(1).strip()
        horde_m = re.search(r'\(([^)]+)/HP\)', role_raw)
        if horde_m:
            adv['horde_qty'] = _decode_pua_qty(horde_m.group(1))
        adv['role'] = re.sub(r'\s*\(.*?\)\s*$', '', role_raw).strip()
        i += 1

    # Flavor text: everything until "Motives" or the stat line
    flavor: list[str] = []
    while i < len(lines):
        ln = lines[i].strip()
        if ln.startswith('Motives') or _STAT.search(ln):
            break
        flavor.append(ln)
        i += 1
    adv['flavor'] = ' '.join(flavor)

    # Motives & Tactics (may wrap onto following lines)
    if i < len(lines) and lines[i].strip().startswith('Motives'):
        motives = [lines[i].strip().replace('Motives & Tactics:', '').strip()]
        i += 1
        while i < len(lines):
            ln = lines[i].strip()
            if _STAT.search(ln) or ln == 'FEATURES' or _TIER_ROLE.match(ln) or _is_name(ln):
                break
            if ln:
                motives.append(ln)
            i += 1
        adv['motives'] = ' '.join(motives)

    # Stats line  "Difficulty: N | Thresholds: N/N | HP: N | Stress: N"
    while i < len(lines):
        m = _STAT.search(lines[i])
        if m:
            adv['difficulty'] = m.group(1)
            adv['thresholds'] = m.group(2).strip()
            adv['hp']         = int(m.group(3))
            adv['stress']     = int(m.group(4))
            i += 1
            break
        i += 1

    # ATK line  "ATK: +N | Weapon: Range | damage phy/mag"
    while i < len(lines):
        m = _ATK.search(lines[i])
        if m:
            adv['atk']         = m.group(1)
            adv['weapon']      = m.group(2).strip()
            adv['range']       = m.group(3).strip()
            adv['damage']      = m.group(4).strip()
            adv['damage_type'] = m.group(5).lower()
            i += 1
            break
        i += 1

    # Experience (optional line)
    if i < len(lines):
        m = _EXP.match(lines[i].strip())
        if m:
            adv['experience'] = m.group(1).strip()
            i += 1

    # Skip blank lines and the FEATURES header, then parse features
    while i < len(lines) and lines[i].strip() in ('', 'FEATURES'):
        i += 1

    # Strip decorative page-bottom labels and image captions embedded in feature text.
    feat_lines = [
        l for l in lines[i:]
        if not l.strip().endswith('::')                       # ALL-CAPS:: decorative header
        and not re.match(r'^[a-z][a-z\s\-]+$', l.strip())   # lowercase-only label line
        and not _NAME_LINE.match(l.strip())                  # ALL-CAPS image caption / section label
    ]
    adv['features'] = parse_features('\n'.join(feat_lines))

    return adv if (adv['name'] and adv['role']) else None


def extract_adversaries(pdf, pages: range) -> list[dict]:
    result: list[dict] = []
    tier = 1
    for idx in pages:
        page = pdf.pages[idx]
        left, right = get_columns(page)
        for col in (left, right):
            for line in col.splitlines():
                m = _TIER_HDR.match(line.strip())
                if m:
                    tier = int(m.group(1))
            for block in split_into_blocks(col):
                adv = parse_adversary(block, tier)
                if adv:
                    result.append(adv)
    return result


# ── environment parsing ───────────────────────────────────────────────────────

_IMPULSE = re.compile(r'^Impulses?:\s*(.+)$', re.I)
_DIFF_E  = re.compile(r'^Difficulty:\s*(.+)$', re.I)
_POT_ADV = re.compile(r'^Potential Adversar(?:y|ies)?:\s*(.+)$', re.I)


def parse_environment(block: str, tier: int) -> dict | None:
    lines = [
        l for l in block.splitlines()
        if l.strip() and not l.strip().startswith('Chapter')
    ]
    if not lines:
        return None

    env: dict = {
        'name': '', 'tier': tier, 'type': '',
        'flavor': '', 'impulses': '',
        'difficulty': '', 'potential_adversaries': '',
        'features': [],
    }

    i = 0

    # Name
    name_parts: list[str] = []
    while i < len(lines) and _is_name(lines[i].strip()):
        name_parts.append(lines[i].strip())
        i += 1
    env['name'] = ' '.join(name_parts).title()

    # Tier / Type  e.g. "Tier ⚄ Exploration"
    if i < len(lines) and _TIER_ROLE.match(lines[i].strip()):
        env['type'] = _TIER_ROLE.match(lines[i].strip()).group(1).strip()
        i += 1

    # Flavor text (until Impulses or Difficulty)
    flavor: list[str] = []
    while i < len(lines):
        ln = lines[i].strip()
        if _IMPULSE.match(ln) or _DIFF_E.match(ln):
            break
        flavor.append(ln)
        i += 1
    env['flavor'] = ' '.join(flavor)

    # Impulses (may wrap)
    if i < len(lines) and _IMPULSE.match(lines[i].strip()):
        imp = [_IMPULSE.match(lines[i].strip()).group(1).strip()]
        i += 1
        while i < len(lines):
            ln = lines[i].strip()
            if _DIFF_E.match(ln) or _POT_ADV.match(ln) or ln == 'FEATURES' or not ln:
                break
            imp.append(ln)
            i += 1
        env['impulses'] = ' '.join(imp)

    # Difficulty
    while i < len(lines):
        m = _DIFF_E.match(lines[i].strip())
        if m:
            env['difficulty'] = m.group(1).strip()
            i += 1
            break
        i += 1

    # Potential Adversaries (may span multiple lines)
    if i < len(lines) and _POT_ADV.match(lines[i].strip()):
        pa = [_POT_ADV.match(lines[i].strip()).group(1).strip()]
        i += 1
        while i < len(lines):
            ln = lines[i].strip()
            if ln == 'FEATURES' or _FEAT_HDR.match(ln) or not ln:
                break
            pa.append(ln)
            i += 1
        env['potential_adversaries'] = ' '.join(pa)

    # Features
    while i < len(lines) and lines[i].strip() in ('', 'FEATURES'):
        i += 1
    env['features'] = parse_features('\n'.join(lines[i:]))

    return env if (env['name'] and env['type']) else None


def extract_environments(pdf, pages: range) -> list[dict]:
    result: list[dict] = []
    tier = 1
    for idx in pages:
        page = pdf.pages[idx]
        left, right = get_columns(page)
        for col in (left, right):
            for line in col.splitlines():
                m = _TIER_HDR.match(line.strip())
                if m:
                    tier = int(m.group(1))
            for block in split_into_blocks(col):
                env = parse_environment(block, tier)
                if env:
                    result.append(env)
    return result


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Extract Daggerheart stat blocks from a rulebook PDF.',
        epilog='With no arguments, reads sources.json and looks for the PDF in ./datastore/.',
    )
    parser.add_argument('--pdf', type=Path,
                        help='Path to the rulebook PDF (bypasses sources.json)')
    parser.add_argument('--adv-pages', type=int, nargs=2, metavar=('START', 'END'),
                        help='Adversary page range: 1-indexed PDF pages, inclusive')
    parser.add_argument('--env-pages', type=int, nargs=2, metavar=('START', 'END'),
                        help='Environment page range: 1-indexed PDF pages, inclusive')
    parser.add_argument('--out', type=Path, default=DATASTORE,
                        help='Output directory (default: ./datastore/)')
    args = parser.parse_args()

    if args.pdf:
        if not args.adv_pages or not args.env_pages:
            parser.error('--adv-pages and --env-pages are required when --pdf is given')
        if not args.pdf.exists():
            sys.exit(f'Error: PDF not found: {args.pdf}')
        pdf_path  = args.pdf
        adv_pages = range(args.adv_pages[0] - 1, args.adv_pages[1])
        env_pages  = range(args.env_pages[0] - 1, args.env_pages[1])
        label     = pdf_path.stem
    else:
        source, pdf_path = load_source()
        adv_pages = range(source['adversary_pages'][0] - 1, source['adversary_pages'][1])
        env_pages  = range(source['environment_pages'][0] - 1, source['environment_pages'][1])
        label = source.get('label', pdf_path.stem)

    print(f'Using: {pdf_path.name}')

    with pdfplumber.open(pdf_path) as pdf:
        print('Extracting adversaries...')
        adversaries = extract_adversaries(pdf, adv_pages)
        print(f'  -> {len(adversaries)} stat blocks found')

        print('Extracting environments...')
        environments = extract_environments(pdf, env_pages)
        print(f'  -> {len(environments)} stat blocks found')

    adv_payload = {
        'source': label,
        'adversaries': sorted(adversaries, key=lambda a: (a['tier'], a['name'])),
    }
    env_payload = {
        'source': label,
        'environments': sorted(environments, key=lambda e: (e['tier'], e['name'])),
    }

    args.out.mkdir(exist_ok=True)
    adv_path = args.out / 'adversaries.json'
    env_path = args.out / 'environments.json'
    adv_path.write_text(json.dumps(adv_payload, indent=2, ensure_ascii=False), encoding='utf-8')
    env_path.write_text(json.dumps(env_payload, indent=2, ensure_ascii=False), encoding='utf-8')

    print(f'\nWrote {adv_path}')
    print(f'Wrote {env_path}')

    incomplete = [a for a in adversaries if not a['weapon'] or not a['role'] or not a['atk']]
    if incomplete:
        print(f'\n! {len(incomplete)} adversaries with missing combat fields:')
        for a in incomplete:
            missing = [f for f in ('weapon', 'role', 'atk') if not a[f]]
            print(f'  Tier {a["tier"]} {a["role"] or "?"}: {a["name"]} - missing: {", ".join(missing)}')

if __name__ == '__main__':
    main()
