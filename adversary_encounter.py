#!/usr/bin/env python3
"""adversary_encounter.py — Re-export shim for backwards compatibility."""

from encounter_tab import EncounterTab
from encounter_panel import EncounterCard, EncounterPreviewPanel
from adversary import (
    AdversaryFormDialog, AdversaryFormPanel, AdversaryPreviewPanel, FeatureEditDialog,
)
from adversary_table import AdversaryPanel, FilterPanel
from budget_dialog import BudgetDialog
from dh_constants import _ADJ_DELTAS, _ADJ_SHORT, _ROLE_COSTS

__all__ = [
    'EncounterTab',
    'EncounterCard',
    'EncounterPreviewPanel',
    'AdversaryFormDialog',
    'AdversaryFormPanel',
    'AdversaryPreviewPanel',
    'AdversaryPanel',
    'FilterPanel',
    'FeatureEditDialog',
    'BudgetDialog',
    '_ADJ_DELTAS',
    '_ADJ_SHORT',
    '_ROLE_COSTS',
]
