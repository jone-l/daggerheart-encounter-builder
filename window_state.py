#!/usr/bin/env python3
"""window_state.py — Shared helpers for persisting window sizes in state.json."""

import json
from pathlib import Path

_STATE_FILE = Path.home() / '.daggerheart' / 'state.json'


def load_window_size(key: str) -> tuple[int, int] | None:
    """Return (width, height) for the named window, or None if not saved."""
    if not _STATE_FILE.exists():
        return None
    try:
        entry = json.loads(_STATE_FILE.read_text(encoding='utf-8')).get('windows', {}).get(key)
        if isinstance(entry, list) and len(entry) == 2:
            w, h = entry
            if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
                return w, h
    except (OSError, json.JSONDecodeError):
        pass
    return None


def save_window_size(key: str, width: int, height: int) -> None:
    """Merge (width, height) for the named window into the state.json windows block."""
    try:
        state = json.loads(_STATE_FILE.read_text(encoding='utf-8')) if _STATE_FILE.exists() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    state.setdefault('windows', {})[key] = [width, height]
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')
    except OSError:
        pass
