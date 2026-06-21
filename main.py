#!/usr/bin/env python3
"""main.py — Daggerheart Encounter Builder — main window and entry point."""

import ctypes
import json
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QGridLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QProgressDialog, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from adversary import AdversaryFormDialog
from version import __version__
from adversary_table import AdversaryPanel
from encounter_tab import EncounterTab
from icons import file_plus_icon, play_icon, printer_icon, save_icon, stop_icon
from print_encounter import print_encounter
import extract


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    return base / relative


_FROZEN   = getattr(sys, 'frozen', False)
_USER_DIR = Path.home() / '.daggerheart'

if _FROZEN:
    ADV_FILE = _USER_DIR / 'adversaries.json'
    ENV_FILE = _USER_DIR / 'environments.json'
else:
    ADV_FILE = Path(__file__).parent / 'datastore' / 'adversaries.json'
    ENV_FILE = Path(__file__).parent / 'datastore' / 'environments.json'

STATE_FILE  = _USER_DIR / 'state.json'
CUSTOM_FILE = _USER_DIR / 'custom_adversaries.json'


def load_adversaries() -> list[dict]:
    if not ADV_FILE.exists():
        print(f'Error: {ADV_FILE} not found. Run extract.py first.', file=sys.stderr)
        return []
    with ADV_FILE.open(encoding='utf-8') as f:
        data = json.load(f)
    return data.get('adversaries', [])


def load_custom_adversaries() -> list[dict]:
    if not CUSTOM_FILE.exists():
        return []
    try:
        entries = json.loads(CUSTOM_FILE.read_text(encoding='utf-8')).get('adversaries', [])
        for a in entries:
            a['homebrew'] = True
        return entries
    except (OSError, json.JSONDecodeError):
        return []


# ── PDF import worker ─────────────────────────────────────────────────────────

class _ImportWorker(QThread):
    succeeded = Signal(list, list)
    failed    = Signal(str)

    def __init__(self, pdf_path: str, source: dict, parent=None):
        super().__init__(parent)
        self._pdf_path = pdf_path
        self._source   = source

    def run(self) -> None:
        try:
            import pdfplumber
            s = self._source
            adv_range = range(s['adversary_pages'][0] - 1, s['adversary_pages'][1])
            env_pages = s.get('environment_pages', [0, 0])
            env_range = range(env_pages[0] - 1, env_pages[1]) if env_pages[1] > 0 else range(0)
            with pdfplumber.open(self._pdf_path) as pdf:
                adversaries  = extract.extract_adversaries(pdf, adv_range)
                environments = extract.extract_environments(pdf, env_range) if env_range else []
            self.succeeded.emit(adversaries, environments)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Source selection dialog ───────────────────────────────────────────────────

class _SourceSelectDialog(QDialog):
    def __init__(self, sources: list[dict], pdf_name: str = '', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Select Source')
        self.setMinimumWidth(420)
        self._sources = sources

        root = QVBoxLayout(self)
        root.setSpacing(8)

        if pdf_name:
            note = QLabel(f'<i>"{pdf_name}" did not match any known source.</i>')
            note.setWordWrap(True)
            root.addWidget(note)

        root.addWidget(QLabel('Source:'))
        self._combo = QComboBox()
        for s in sources:
            self._combo.addItem(s.get('label', s['filename']))
        self._combo.addItem('Custom (enter page ranges manually)…')
        self._combo.currentIndexChanged.connect(self._on_selection_changed)
        root.addWidget(self._combo)

        self._custom_frame = QWidget()
        grid = QGridLayout(self._custom_frame)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(6)

        grid.addWidget(QLabel('Adversary pages:'), 0, 0)
        self._adv_start = QSpinBox(); self._adv_start.setRange(1, 9999); self._adv_start.setValue(1)
        grid.addWidget(self._adv_start, 0, 1)
        grid.addWidget(QLabel('to'), 0, 2)
        self._adv_end = QSpinBox(); self._adv_end.setRange(1, 9999); self._adv_end.setValue(999)
        grid.addWidget(self._adv_end, 0, 3)

        grid.addWidget(QLabel('Environment pages:'), 1, 0)
        self._env_start = QSpinBox(); self._env_start.setRange(0, 9999); self._env_start.setValue(1)
        grid.addWidget(self._env_start, 1, 1)
        grid.addWidget(QLabel('to'), 1, 2)
        self._env_end = QSpinBox(); self._env_end.setRange(0, 9999); self._env_end.setValue(999)
        grid.addWidget(self._env_end, 1, 3)
        grid.addWidget(QLabel('(set environment pages to 0 to skip)'), 2, 0, 1, 4)

        self._custom_frame.setVisible(False)
        root.addWidget(self._custom_frame)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_selection_changed(self, index: int) -> None:
        self._custom_frame.setVisible(index == self._combo.count() - 1)
        self.adjustSize()

    def get_source(self) -> dict:
        idx = self._combo.currentIndex()
        if idx < len(self._sources):
            return self._sources[idx]
        return {
            'filename': '',
            'label': 'Custom',
            'adversary_pages':   [self._adv_start.value(), self._adv_end.value()],
            'environment_pages': [self._env_start.value(), self._env_end.value()],
        }


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'Daggerheart Encounter Builder {__version__}')
        self.setWindowIcon(QIcon(str(_resource_path('assets/icons/DH_CGL_logo.png'))))
        self.resize(1400, 800)

        self._official_adversaries = load_adversaries()
        self._custom_adversaries   = load_custom_adversaries()

        self._last_save_dir  = ''
        self._last_load_dir  = ''
        self._recent_files: list[str] = []
        self._pre_run_sizes: list | None = None

        # Adversary panel (filter + table) — always visible on the left
        self._adv_panel = AdversaryPanel(self._merged_adversaries())
        self._adv_panel.add_requested.connect(self._on_add_to_encounter)
        self._adv_panel.edit_requested.connect(self._on_edit_from_list)
        self._adv_panel.filters_changed.connect(self._on_filters_changed)

        # Form dialog for editing adversaries from the list
        self._list_form_dialog = AdversaryFormDialog(self)
        self._list_form_dialog.add_to_encounter.connect(self._on_add_to_encounter)
        self._list_form_dialog.save_to_custom.connect(self._save_custom_adversary)
        self._list_form_dialog.save_as_new_custom.connect(self._add_new_custom_adversary)

        # Encounter tabs (right pane — hidden when no encounters open)
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._update_save_actions)
        self._tabs.currentChanged.connect(self._update_list_encounter_state)
        self._tabs.currentChanged.connect(lambda _: self._update_left_panel())

        # Outer splitter
        self._outer = QSplitter(Qt.Orientation.Horizontal)
        self._outer.addWidget(self._adv_panel)
        self._outer.addWidget(self._tabs)
        self._outer.setCollapsible(0, False)
        self._outer.setCollapsible(1, False)
        self._tabs.setVisible(False)
        self._outer.setSizes([10000, 0])

        self.setCentralWidget(self._outer)

        # ── Menu bar ──
        file_menu = self.menuBar().addMenu('File')
        new_act = QAction(file_plus_icon(), 'New Encounter', self)
        new_act.triggered.connect(self._new_encounter)
        file_menu.addAction(new_act)

        self._save_action = QAction(save_icon(), 'Save Encounter', self)
        self._save_action.setShortcut('Ctrl+S')
        self._save_action.setEnabled(False)
        self._save_action.triggered.connect(self._save_encounter_quick)
        file_menu.addAction(self._save_action)

        self._save_as_action = QAction('Save As…', self)
        self._save_as_action.setShortcut('Ctrl+Shift+S')
        self._save_as_action.setEnabled(False)
        self._save_as_action.triggered.connect(self._save_encounter_file)
        file_menu.addAction(self._save_as_action)

        self._print_action = QAction('Print Encounter…', self)
        self._print_action.setShortcut('Ctrl+P')
        self._print_action.setIcon(printer_icon())
        self._print_action.setEnabled(False)
        self._print_action.triggered.connect(self._print_encounter)
        file_menu.addAction(self._print_action)

        self._run_action = QAction(play_icon(), 'Run Encounter', self)
        self._run_action.setShortcut('Ctrl+R')
        self._run_action.setEnabled(False)
        self._run_action.triggered.connect(self._run_encounter)
        file_menu.addAction(self._run_action)

        self._stop_action = QAction(stop_icon(), 'Stop Encounter', self)
        self._stop_action.setEnabled(False)
        self._stop_action.triggered.connect(self._stop_encounter)
        file_menu.addAction(self._stop_action)

        load_act = QAction('Load Encounter…', self)
        load_act.triggered.connect(self._load_encounter_file)
        file_menu.addAction(load_act)

        self._recent_menu = QMenu('Open Recent', self)
        file_menu.addMenu(self._recent_menu)
        self._update_recent_menu()

        file_menu.addSeparator()
        import_act = QAction('Import Source…', self)
        import_act.triggered.connect(self._import_source)
        file_menu.addAction(import_act)
        file_menu.addSeparator()
        exit_act = QAction('Exit', self)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # ── Toolbar ──
        file_tb = self.addToolBar('File')
        file_tb.setMovable(False)
        file_tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        file_tb.addAction(new_act)
        file_tb.addAction(self._save_action)
        file_tb.addAction(self._print_action)
        file_tb.addAction(self._run_action)
        file_tb.addAction(self._stop_action)

        # ── Status bar ──
        self._status_label = QLabel()
        self.statusBar().addWidget(self._status_label, 1)
        self._update_status(set(), set(), set())
        self._load_state()

        if not self._official_adversaries:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._prompt_import_if_empty)

    # ── Tab management ────────────────────────────────────────────────────────

    def _current_tab(self) -> EncounterTab | None:
        w = self._tabs.currentWidget()
        return w if isinstance(w, EncounterTab) else None

    def _find_tab_by_path(self, path: str) -> int | None:
        resolved = str(Path(path).resolve())
        for i in range(self._tabs.count()):
            w = self._tabs.widget(i)
            if isinstance(w, EncounterTab) and str(Path(w.save_path).resolve()) == resolved:
                return i
        return None

    def _new_encounter(self) -> None:
        tab = EncounterTab()
        tab.title_changed.connect(lambda title, t=tab: self._update_tab_title(t, title))
        tab.title_changed.connect(lambda _: self._update_save_actions())
        tab.save_to_custom.connect(self._save_custom_adversary)
        tab.save_as_new_custom.connect(self._add_new_custom_adversary)
        self._tabs.addTab(tab, 'Untitled')
        self._tabs.setCurrentWidget(tab)
        self._show_right_pane(True)

    def _close_tab(self, idx: int) -> None:
        w = self._tabs.widget(idx)
        if isinstance(w, EncounterTab) and w.is_running:
            w.stop_run()
        if isinstance(w, EncounterTab) and w.dirty:
            msg = QMessageBox(self)
            msg.setWindowTitle('Unsaved Changes')
            msg.setText(f'"{self._tabs.tabText(idx)}" has unsaved changes.')
            msg.setStandardButtons(
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            msg.setDefaultButton(QMessageBox.StandardButton.Save)
            result = msg.exec()
            if result == QMessageBox.StandardButton.Cancel:
                return
            if result == QMessageBox.StandardButton.Save:
                self._tabs.setCurrentIndex(idx)
                if w.save_path:
                    self._save_encounter_quick()
                else:
                    self._save_encounter_file()
                if w.dirty:
                    return
        self._tabs.removeTab(idx)
        w.deleteLater()
        if self._tabs.count() == 0:
            self._show_right_pane(False)

    def _update_left_panel(self) -> None:
        tab     = self._current_tab()
        running = tab is not None and tab.is_running
        if running and self._adv_panel.isVisible():
            self._pre_run_sizes = self._outer.sizes()
            self._adv_panel.setVisible(False)
        elif not running and not self._adv_panel.isVisible():
            self._adv_panel.setVisible(True)
            if self._pre_run_sizes:
                self._outer.setSizes(self._pre_run_sizes)
                self._pre_run_sizes = None

    def _show_right_pane(self, visible: bool) -> None:
        self._tabs.setVisible(visible)
        if visible:
            w = self._outer.width()
            self._outer.setSizes([w * 6 // 10, w * 4 // 10])
        else:
            self._outer.setSizes([10000, 0])
        self._adv_panel.set_encounter_open(visible)
        self._update_list_form_dialog_mode()

    def _update_list_encounter_state(self) -> None:
        self._update_list_form_dialog_mode()

    def _update_list_form_dialog_mode(self) -> None:
        has_encounter = self._tabs.count() > 0
        # Show/hide add buttons in any open list form dialog
        panel = self._list_form_dialog.form_panel
        panel._add_btn.setVisible(has_encounter)

    def _update_tab_title(self, tab: EncounterTab, title: str) -> None:
        idx = self._tabs.indexOf(tab)
        if idx >= 0:
            self._tabs.setTabText(idx, title)

    # ── Adversary panel callbacks ─────────────────────────────────────────────

    def _on_add_to_encounter(self, adv: dict, count: int) -> None:
        tab = self._current_tab()
        if tab:
            tab.preview_panel.add_entry(adv, count)

    def _on_edit_from_list(self, adv: dict) -> None:
        self._list_form_dialog.load(adv)
        self._update_list_form_dialog_mode()
        self._list_form_dialog.exec()

    def _on_filters_changed(self, tiers: set, roles: set, sources: set) -> None:
        self._update_status(tiers, roles, sources)
        self._save_state()

    # ── Status bar ────────────────────────────────────────────────────────────

    def _update_status(self, tiers: set[int], roles: set[str], sources: set[str]) -> None:
        from adversary_table import _ALL_ROLES, _ALL_TIERS, _ALL_SOURCES
        all_tiers   = set(_ALL_TIERS)
        all_roles   = set(_ALL_ROLES)
        all_sources = {v for v, _ in _ALL_SOURCES}
        parts = []
        if tiers != all_tiers and tiers:
            parts.append(', '.join(f'Tier {t}' for t in sorted(tiers)) or 'no tiers')
        if roles != all_roles and roles:
            parts.append(', '.join(sorted(roles)) or 'no roles')
        if sources != all_sources and sources:
            labels = {'official': 'Official', 'homebrew': 'Homebrew'}
            parts.append(', '.join(labels[s] for s in sorted(sources)) or 'no sources')
        self._status_label.setText('Filters: ' + ('  ·  '.join(parts) if parts else 'none'))

    # ── State persistence ─────────────────────────────────────────────────────

    def _save_state(self) -> None:
        if getattr(self, '_loading_state', False):
            return
        tiers, roles, sources = self._adv_panel.filter_panel.get_filters()
        updates = {
            'filters': {
                'tiers':   sorted(tiers),
                'roles':   sorted(roles),
                'sources': sorted(sources),
            },
            'last_save_dir': self._last_save_dir,
            'last_load_dir': self._last_load_dir,
            'recent_files':  self._recent_files,
            'window':        {'width': self.width(), 'height': self.height()},
        }
        try:
            existing = json.loads(STATE_FILE.read_text(encoding='utf-8')) if STATE_FILE.exists() else {}
        except (OSError, json.JSONDecodeError):
            existing = {}
        existing.update(updates)
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(existing, indent=2), encoding='utf-8')
        except OSError:
            pass

    def _load_state(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            state = json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return
        self._loading_state = True
        try:
            filters = state.get('filters', {})
            tiers   = set(filters.get('tiers',   [1, 2, 3, 4]))
            roles   = set(filters.get('roles',   list(__import__('adversary_table')._ALL_ROLES)))
            sources = set(filters.get('sources', ['official', 'homebrew']))
            self._adv_panel.filter_panel.restore(tiers, roles, sources)
            self._last_save_dir = state.get('last_save_dir', '')
            self._last_load_dir = state.get('last_load_dir', '')
            self._recent_files  = [p for p in state.get('recent_files', []) if isinstance(p, str)]
            self._update_recent_menu()
            win = state.get('window', {})
            if win.get('width') and win.get('height'):
                self.resize(win['width'], win['height'])
        finally:
            self._loading_state = False
            self._save_state()

    def _add_recent(self, path: str) -> None:
        path = str(Path(path).resolve())
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:5]
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        self._recent_menu.clear()
        if not self._recent_files:
            act = QAction('(empty)', self)
            act.setEnabled(False)
            self._recent_menu.addAction(act)
            return
        for path in self._recent_files:
            act = QAction(Path(path).name, self)
            act.setToolTip(path)
            act.triggered.connect(lambda _=False, p=path: self._open_recent(p))
            self._recent_menu.addAction(act)

    def _open_recent(self, path: str) -> None:
        existing = self._find_tab_by_path(path)
        if existing is not None:
            self._tabs.setCurrentIndex(existing)
            return
        p = Path(path)
        if not p.exists():
            QMessageBox.critical(self, 'File Not Found', f'"{p.name}" no longer exists.')
            if path in self._recent_files:
                self._recent_files.remove(path)
            self._update_recent_menu()
            self._save_state()
            return
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            QMessageBox.critical(self, 'Load Error', f'Could not read "{p.name}".')
            return
        self._new_encounter()
        tab = self._current_tab()
        tab.load_encounter_state(data)
        tab.mark_saved(path)
        self._last_load_dir = str(p.parent)
        self._add_recent(path)
        self._save_state()

    def _update_save_actions(self) -> None:
        tab     = self._current_tab()
        running = tab is not None and tab.is_running
        self._save_action.setEnabled(bool(tab and tab.save_path and tab.dirty and not running))
        self._save_as_action.setEnabled(tab is not None and not running)
        self._print_action.setEnabled(tab is not None and not running)
        self._run_action.setEnabled(
            bool(tab and tab.save_path and not tab.dirty and not running))
        self._stop_action.setEnabled(running)

    def _run_encounter(self) -> None:
        tab = self._current_tab()
        if not tab:
            return
        if not tab.save_path or tab.dirty:
            QMessageBox.information(
                self, 'Save Required',
                'Please save the encounter before running it.\n\n'
                'Save with Ctrl+S or File → Save As… first.'
            )
            return
        tab.start_run()
        self._update_save_actions()
        self._update_left_panel()

    def _stop_encounter(self) -> None:
        tab = self._current_tab()
        if tab and tab.is_running:
            tab.stop_run()
            self._update_save_actions()
            self._update_left_panel()

    # ── Source import ─────────────────────────────────────────────────────────

    def _prompt_import_if_empty(self) -> None:
        reply = QMessageBox.question(
            self, 'No Adversary Data',
            'No adversary data has been imported yet.\n\nImport from a PDF now?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._import_source()

    def _import_source(self) -> None:
        pdf_path, _ = QFileDialog.getOpenFileName(
            self, 'Select Daggerheart PDF', '', 'PDF Files (*.pdf)')
        if not pdf_path:
            return
        try:
            manifest = json.loads(_resource_path('sources.json').read_text(encoding='utf-8'))
            sources = manifest.get('sources', [])
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Cannot read sources.json:\n{e}')
            return
        pdf_name = Path(pdf_path).name
        matched  = next(
            (s for s in sources if s.get('filename', '').lower() == pdf_name.lower()), None
        )
        if matched is not None:
            label = matched.get('label', matched['filename'])
            reply = QMessageBox.question(
                self, 'Import Source',
                f'Matched: {label}\n\nExtract adversary data from this PDF?\nThis may take a minute.',
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return
            source = matched
        else:
            dlg = _SourceSelectDialog(sources, pdf_name, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            source = dlg.get_source()

        progress = QProgressDialog('Extracting data from PDF…', None, 0, 0, self)
        progress.setWindowTitle('Importing')
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        self._worker = _ImportWorker(pdf_path, source, self)
        self._worker.succeeded.connect(
            lambda advs, envs: self._on_import_done(advs, envs, source.get('label', 'Custom'), progress)
        )
        self._worker.failed.connect(lambda err: self._on_import_error(err, progress))
        self._worker.start()

    def _on_import_done(self, adversaries: list, environments: list,
                        label: str, progress: QProgressDialog) -> None:
        progress.close()
        dest = ADV_FILE.parent
        dest.mkdir(parents=True, exist_ok=True)
        adv_data = {'source': label,
                    'adversaries': sorted(adversaries, key=lambda a: (a['tier'], a['name']))}
        env_data = {'source': label,
                    'environments': sorted(environments, key=lambda e: (e['tier'], e['name']))}
        ADV_FILE.write_text(json.dumps(adv_data, indent=2, ensure_ascii=False), encoding='utf-8')
        ENV_FILE.write_text(json.dumps(env_data, indent=2, ensure_ascii=False), encoding='utf-8')
        self._reload_adversaries()
        QMessageBox.information(
            self, 'Import Complete',
            f'Imported {len(adversaries)} adversaries from {label}.'
        )

    def _on_import_error(self, error: str, progress: QProgressDialog) -> None:
        progress.close()
        QMessageBox.critical(self, 'Import Failed', f'Extraction failed:\n{error}')

    def _reload_adversaries(self) -> None:
        self._official_adversaries = load_adversaries()
        self._adv_panel.set_adversaries(self._merged_adversaries())

    # ── Custom adversaries ────────────────────────────────────────────────────

    def _merged_adversaries(self) -> list[dict]:
        return sorted(
            self._official_adversaries + self._custom_adversaries,
            key=lambda a: (a.get('tier', 0), a.get('name', ''))
        )

    def _save_custom_adversary(self, original: dict, new: dict) -> None:
        entry = {k: v for k, v in new.items() if k != 'homebrew'}
        entry['homebrew'] = True
        if original.get('homebrew'):
            self._custom_adversaries = [
                a for a in self._custom_adversaries if a.get('name') != original.get('name')
            ]
        else:
            self._custom_adversaries = [
                a for a in self._custom_adversaries if a.get('name') != entry.get('name')
            ]
        self._custom_adversaries.append(entry)
        self._save_custom_file()
        self._adv_panel.set_adversaries(self._merged_adversaries())

    def _add_new_custom_adversary(self, new: dict) -> None:
        entry = {k: v for k, v in new.items() if k != 'homebrew'}
        entry['homebrew'] = True
        self._custom_adversaries = [
            a for a in self._custom_adversaries if a.get('name') != entry.get('name')
        ]
        self._custom_adversaries.append(entry)
        self._save_custom_file()
        self._adv_panel.set_adversaries(self._merged_adversaries())

    def _save_custom_file(self) -> None:
        entries = [{k: v for k, v in a.items() if k != 'homebrew'} for a in self._custom_adversaries]
        try:
            CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
            CUSTOM_FILE.write_text(json.dumps({'adversaries': entries}, indent=2), encoding='utf-8')
        except OSError:
            pass

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _save_encounter_quick(self) -> None:
        tab = self._current_tab()
        if not tab or not tab.save_path:
            return
        data = tab.get_encounter_state()
        try:
            Path(tab.save_path).write_text(json.dumps(data, indent=2), encoding='utf-8')
            tab.mark_saved(tab.save_path)
            self._save_state()
        except OSError:
            pass

    def _save_encounter_file(self) -> None:
        tab = self._current_tab()
        if not tab:
            return
        data = tab.get_encounter_state()
        raw  = data.get('name', '')
        safe = re.sub(r'[^\w\s-]', '', raw.lower())
        safe = re.sub(r'\s+', '_', safe.strip())
        filename = (safe or 'encounter') + '.json'
        initial  = str(Path(self._last_save_dir) / filename) if self._last_save_dir else filename
        path, _  = QFileDialog.getSaveFileName(
            self, 'Save Encounter', initial, 'JSON files (*.json)'
        )
        if path:
            try:
                Path(path).write_text(json.dumps(data, indent=2), encoding='utf-8')
                self._last_save_dir = str(Path(path).parent)
                tab.mark_saved(path, Path(path).stem if not raw else '')
                self._add_recent(path)
                self._save_state()
            except OSError:
                pass

    def _print_encounter(self) -> None:
        tab = self._current_tab()
        if not tab:
            return
        print_encounter(tab.get_encounter_state(), self)

    def _load_encounter_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, 'Load Encounter', self._last_load_dir, 'JSON files (*.json)'
        )
        if not path:
            return
        existing = self._find_tab_by_path(path)
        if existing is not None:
            self._tabs.setCurrentIndex(existing)
            return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            self._last_load_dir = str(Path(path).parent)
            self._new_encounter()
            tab = self._current_tab()
            tab.load_encounter_state(data)
            tab.mark_saved(path)
            self._add_recent(path)
            self._save_state()
        except (OSError, json.JSONDecodeError):
            pass

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        self._save_state()
        dirty_tabs = [
            (i, self._tabs.tabText(i))
            for i in range(self._tabs.count())
            if isinstance(self._tabs.widget(i), EncounterTab)
            and self._tabs.widget(i).dirty
        ]
        if not dirty_tabs:
            event.accept()
            return
        names = '\n'.join(f'  • {title}' for _, title in dirty_tabs)
        msg = QMessageBox(self)
        msg.setWindowTitle('Unsaved Changes')
        msg.setText(f'The following encounters have unsaved changes:\n\n{names}')
        msg.setStandardButtons(
            QMessageBox.StandardButton.SaveAll |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        msg.setDefaultButton(QMessageBox.StandardButton.SaveAll)
        result = msg.exec()
        if result == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return
        if result == QMessageBox.StandardButton.SaveAll:
            for i, _ in dirty_tabs:
                tab = self._tabs.widget(i)
                self._tabs.setCurrentIndex(i)
                if isinstance(tab, EncounterTab) and tab.save_path:
                    self._save_encounter_quick()
                else:
                    self._save_encounter_file()
                if isinstance(tab, EncounterTab) and tab.dirty:
                    event.ignore()
                    return
        event.accept()


if __name__ == '__main__':
    if sys.platform == 'win32':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('sublevel3.daggerheart.encounter-builder')
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
