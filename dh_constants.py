#!/usr/bin/env python3
"""dh_constants.py — Daggerheart game constants used across the encounter builder."""

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

_ADJ_SHORT: dict[str, str] = {
    'adj_less_difficult': 'less difficult',
    'adj_two_plus_solos': '2+ solos',
    'adj_damage_bonus':   '+1d4 dmg',
    'adj_lower_tier':     'lower tier',
    'adj_no_heavy_roles': 'no heavy roles',
    'adj_more_dangerous': 'more dangerous',
}
