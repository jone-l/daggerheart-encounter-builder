#!/usr/bin/env python3
"""main.py — Daggerheart Encounter Builder — main window and entry point."""

import ctypes
import json
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QGridLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QProgressDialog, QSpinBox,
    QSplitter, QStyle, QTabWidget, QVBoxLayout, QWidget,
)

from encounter_tab import EncounterTab
from print_encounter import print_encounter
import extract


def _resource_path(relative: str) -> Path:
    """Resolve a bundled resource path; works both frozen (PyInstaller) and in development."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    return base / relative


_FROZEN   = getattr(sys, 'frozen', False)
_USER_DIR = Path.home() / '.daggerheart'

# Adversary data lives in the user dir when frozen (no bundled data),
# and in the project datastore when running from source.
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
    """Runs PDF extraction off the UI thread."""
    succeeded = Signal(list, list)  # (adversaries, environments)
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
    """Let the user pick a known source or enter custom page ranges."""

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

        # Page range inputs — shown only when Custom is selected
        self._custom_frame = QWidget()
        grid = QGridLayout(self._custom_frame)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(6)

        grid.addWidget(QLabel('Adversary pages:'), 0, 0)
        self._adv_start = QSpinBox()
        self._adv_start.setRange(1, 9999)
        self._adv_start.setValue(1)
        grid.addWidget(self._adv_start, 0, 1)
        grid.addWidget(QLabel('to'), 0, 2)
        self._adv_end = QSpinBox()
        self._adv_end.setRange(1, 9999)
        self._adv_end.setValue(999)
        grid.addWidget(self._adv_end, 0, 3)

        grid.addWidget(QLabel('Environment pages:'), 1, 0)
        self._env_start = QSpinBox()
        self._env_start.setRange(0, 9999)
        self._env_start.setValue(1)
        grid.addWidget(self._env_start, 1, 1)
        grid.addWidget(QLabel('to'), 1, 2)
        self._env_end = QSpinBox()
        self._env_end.setRange(0, 9999)
        self._env_end.setValue(999)
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


# ── Adversary list panel ──────────────────────────────────────────────────────

class AdversaryListPanel(QWidget):
    adversary_selected      = Signal(dict)
    delete_custom_requested = Signal(dict)

    def __init__(self, adversaries: list[dict], parent=None):
        super().__init__(parent)
        self._all = adversaries
        self._enabled_tiers: set[int] = {1, 2, 3, 4}
        self._enabled_roles: set[str] = {a['role'] for a in adversaries if a.get('role')}
        self._enabled_sources: set[str] = {'official', 'homebrew'}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._search = QLineEdit()
        self._search.setPlaceholderText('Search (regex)...')
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.itemClicked.connect(self._on_click)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list)

        self._populate(adversaries)

    def _populate(self, adversaries: list[dict]) -> None:
        self._list.clear()
        current_tier = None
        for adv in adversaries:
            tier = adv['tier']
            if tier != current_tier:
                current_tier = tier
                header = QListWidgetItem(f'  TIER {tier}')
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                f = header.font()
                f.setBold(True)
                header.setFont(f)
                self._list.addItem(header)
            suffix = ' (hb)' if adv.get('homebrew') else ''
            item = QListWidgetItem(f"    {adv['name']}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, adv)
            self._list.addItem(item)

    def _filter(self, text: str) -> None:
        try:
            pattern = re.compile(text, re.IGNORECASE) if text else None
            self._search.setStyleSheet('')
        except re.error:
            pattern = None
            self._search.setStyleSheet('background: #5c1a1a;')
        filtered = [
            a for a in self._all
            if a.get('tier') in self._enabled_tiers
            and a.get('role') in self._enabled_roles
            and ('homebrew' if a.get('homebrew') else 'official') in self._enabled_sources
            and (not pattern or pattern.search(a['name']))
        ]
        self._populate(filtered)

    def _on_click(self, item: QListWidgetItem) -> None:
        adv = item.data(Qt.ItemDataRole.UserRole)
        if adv:
            self.adversary_selected.emit(adv)

    def _on_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if not item:
            return
        adv = item.data(Qt.ItemDataRole.UserRole)
        if not adv or not adv.get('homebrew'):
            return
        menu = QMenu(self)
        delete_act = menu.addAction('Delete Custom Entry')
        if menu.exec(self._list.mapToGlobal(pos)) == delete_act:
            self.delete_custom_requested.emit(adv)

    def set_tier_filter(self, tiers: set[int]) -> None:
        self._enabled_tiers = tiers
        self._filter(self._search.text())

    def set_role_filter(self, roles: set[str]) -> None:
        self._enabled_roles = roles
        self._filter(self._search.text())

    def set_source_filter(self, sources: set[str]) -> None:
        self._enabled_sources = sources
        self._filter(self._search.text())

    def set_adversaries(self, adversaries: list[dict]) -> None:
        self._all = adversaries
        self._filter(self._search.text())


# ── Stay-open menu ────────────────────────────────────────────────────────────

class StayOpenMenu(QMenu):
    """QMenu that stays open when clicking checkable or bulk-toggle actions."""
    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        if action:
            action.trigger()

# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Daggerheart Encounter Builder')
        self.setWindowIcon(QIcon(str(_resource_path('assets/icons/DH_CGL_logo.png'))))
        self.resize(1400, 800)

        self._official_adversaries = load_adversaries()
        self._custom_adversaries   = load_custom_adversaries()

        self._list_panel = AdversaryListPanel(self._merged_adversaries())
        self._list_panel.adversary_selected.connect(self._on_adversary_selected)
        self._list_panel.delete_custom_requested.connect(self._delete_custom_adversary)

        self._last_save_dir  = ''
        self._last_load_dir  = ''
        self._layout_mode    = '3col'
        self._recent_files: list[str] = []

        # ── Menu bar ──
        file_menu = self.menuBar().addMenu('File')
        si = self.style().standardIcon
        new_act = QAction(si(QStyle.StandardPixmap.SP_FileIcon), 'New Encounter', self)
        new_act.triggered.connect(self._new_encounter)
        file_menu.addAction(new_act)

        self._save_action = QAction(si(QStyle.StandardPixmap.SP_DialogSaveButton), 'Save Encounter', self)
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
        self._print_action.setToolTip('Print Encounter')
        self._print_action.setIcon(QIcon.fromTheme('document-print', si(QStyle.StandardPixmap.SP_FileDialogDetailedView)))
        self._print_action.setEnabled(False)
        self._print_action.triggered.connect(self._print_encounter)
        file_menu.addAction(self._print_action)

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

        view_menu = self.menuBar().addMenu('View')

        tier_sub = StayOpenMenu('Filter by Tier', self)
        view_menu.addMenu(tier_sub)
        for label, slot in [('Check All', lambda: self._set_all_tiers(True)),
                             ('Uncheck All', lambda: self._set_all_tiers(False))]:
            a = QAction(label, self); a.triggered.connect(slot); tier_sub.addAction(a)
        tier_sub.addSeparator()
        self._tier_actions: dict[int, QAction] = {}
        for t in range(1, 5):
            act = QAction(f'Tier {t}', self, checkable=True, checked=True)
            act.triggered.connect(self._on_tier_filter_changed)
            tier_sub.addAction(act)
            self._tier_actions[t] = act

        role_sub = StayOpenMenu('Filter by Role', self)
        view_menu.addMenu(role_sub)
        for label, slot in [('Check All', lambda: self._set_all_roles(True)),
                             ('Uncheck All', lambda: self._set_all_roles(False))]:
            a = QAction(label, self); a.triggered.connect(slot); role_sub.addAction(a)
        role_sub.addSeparator()
        self._role_actions: dict[str, QAction] = {}
        for role in sorted({a['role'] for a in self._merged_adversaries() if a.get('role')}):
            act = QAction(role, self, checkable=True, checked=True)
            act.triggered.connect(self._on_role_filter_changed)
            role_sub.addAction(act)
            self._role_actions[role] = act

        source_sub = StayOpenMenu('Filter by Source', self)
        view_menu.addMenu(source_sub)
        for label, slot in [('Check All', lambda: self._set_all_sources(True)),
                             ('Uncheck All', lambda: self._set_all_sources(False))]:
            a = QAction(label, self); a.triggered.connect(slot); source_sub.addAction(a)
        source_sub.addSeparator()
        self._source_actions: dict[str, QAction] = {}
        for source, label in [('official', 'Official'), ('homebrew', 'Homebrew')]:
            act = QAction(label, self, checkable=True, checked=True)
            act.triggered.connect(self._on_source_filter_changed)
            source_sub.addAction(act)
            self._source_actions[source] = act

        view_menu.addSeparator()
        layout_group = QActionGroup(self)
        layout_group.setExclusive(True)
        self._layout_3col_act = QAction('Side by side', self, checkable=True, checked=True)
        self._layout_3col_act.triggered.connect(lambda: self._set_layout('3col'))
        layout_group.addAction(self._layout_3col_act)
        view_menu.addAction(self._layout_3col_act)
        self._layout_2col_act = QAction('Stacked', self, checkable=True)
        self._layout_2col_act.triggered.connect(lambda: self._set_layout('2col'))
        layout_group.addAction(self._layout_2col_act)
        view_menu.addAction(self._layout_2col_act)

        # ── Toolbar: file actions ──
        file_tb = self.addToolBar('File')
        file_tb.setMovable(False)
        file_tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        file_tb.addAction(new_act)
        file_tb.addAction(self._save_action)
        file_tb.addAction(self._print_action)
        print_btn = file_tb.widgetForAction(self._print_action)
        if print_btn and hasattr(print_btn, 'setToolButtonStyle'):
            print_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        # ── Outer splitter: list | tabs ──
        self._outer = QSplitter(Qt.Orientation.Horizontal)
        self._list_panel.setMinimumWidth(180)
        self._outer.addWidget(self._list_panel)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._update_save_actions)
        self._outer.addWidget(self._tabs)

        self._outer.setSizes([250, 1150])
        self.setCentralWidget(self._outer)

        self._status_label = QLabel()
        self.statusBar().addWidget(self._status_label, 1)
        self._update_status()
        self._load_state()

        if not self._official_adversaries:
            QTimer.singleShot(0, self._prompt_import_if_empty)

    # ── Tab management ────────────────────────────────────────────────────────

    def _current_tab(self) -> EncounterTab | None:
        w = self._tabs.currentWidget()
        return w if isinstance(w, EncounterTab) else None

    def _on_adversary_selected(self, adv: dict) -> None:
        tab = self._current_tab()
        if tab:
            tab.adv_preview.load(adv)

    def _new_encounter(self) -> None:
        tab = EncounterTab(self._layout_mode)
        tab.title_changed.connect(lambda title, t=tab: self._update_tab_title(t, title))
        tab.title_changed.connect(lambda _: self._update_save_actions())
        tab.form_dialog.save_to_custom.connect(self._save_custom_adversary)
        tab.form_dialog.save_as_new_custom.connect(self._add_new_custom_adversary)
        self._tabs.addTab(tab, 'Untitled')
        self._tabs.setCurrentWidget(tab)

    def _close_tab(self, idx: int) -> None:
        w = self._tabs.widget(idx)
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

    def _update_tab_title(self, tab: EncounterTab, title: str) -> None:
        idx = self._tabs.indexOf(tab)
        if idx >= 0:
            self._tabs.setTabText(idx, title)

    # ── Filters ───────────────────────────────────────────────────────────────

    def _on_tier_filter_changed(self) -> None:
        enabled = {t for t, act in self._tier_actions.items() if act.isChecked()}
        self._list_panel.set_tier_filter(enabled)
        self._update_status()
        self._save_state()

    def _on_role_filter_changed(self) -> None:
        enabled = {r for r, act in self._role_actions.items() if act.isChecked()}
        self._list_panel.set_role_filter(enabled)
        self._update_status()
        self._save_state()

    def _update_status(self) -> None:
        parts = []
        active_tiers = {t for t, act in self._tier_actions.items() if act.isChecked()}
        if active_tiers != set(self._tier_actions):
            parts.append(', '.join(f'Tier {t}' for t in sorted(active_tiers)) or 'no tiers')
        active_roles = {r for r, act in self._role_actions.items() if act.isChecked()}
        if active_roles != set(self._role_actions):
            parts.append(', '.join(sorted(active_roles)) or 'no roles')
        active_sources = {s for s, act in self._source_actions.items() if act.isChecked()}
        if active_sources != set(self._source_actions):
            labels = {'official': 'Official', 'homebrew': 'Homebrew'}
            parts.append(', '.join(labels[s] for s in sorted(active_sources)) or 'no sources')
        self._status_label.setText('Filters: ' + ('  ·  '.join(parts) if parts else 'none'))

    def _set_all_tiers(self, checked: bool) -> None:
        for act in self._tier_actions.values():
            act.setChecked(checked)
        self._on_tier_filter_changed()

    def _set_all_roles(self, checked: bool) -> None:
        for act in self._role_actions.values():
            act.setChecked(checked)
        self._on_role_filter_changed()

    def _on_source_filter_changed(self) -> None:
        enabled = {s for s, act in self._source_actions.items() if act.isChecked()}
        self._list_panel.set_source_filter(enabled)
        self._update_status()
        self._save_state()

    def _set_all_sources(self, checked: bool) -> None:
        for act in self._source_actions.values():
            act.setChecked(checked)
        self._on_source_filter_changed()

    # ── State persistence ─────────────────────────────────────────────────────

    def _save_state(self) -> None:
        if getattr(self, '_loading_state', False):
            return
        state = {
            'filters': {
                'tiers':   sorted(t for t, act in self._tier_actions.items() if act.isChecked()),
                'roles':   sorted(r for r, act in self._role_actions.items() if act.isChecked()),
                'sources': sorted(s for s, act in self._source_actions.items() if act.isChecked()),
            },
            'last_save_dir': self._last_save_dir,
            'last_load_dir': self._last_load_dir,
            'recent_files':  self._recent_files,
            'window':        {'width': self.width(), 'height': self.height()},
        }
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')
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
            tiers = set(filters.get('tiers', list(self._tier_actions)))
            for t, act in self._tier_actions.items():
                act.setChecked(t in tiers)
            self._on_tier_filter_changed()
            roles = set(filters.get('roles', list(self._role_actions)))
            for r, act in self._role_actions.items():
                act.setChecked(r in roles)
            self._on_role_filter_changed()
            sources = set(filters.get('sources', list(self._source_actions)))
            for s, act in self._source_actions.items():
                act.setChecked(s in sources)
            self._on_source_filter_changed()
            self._last_save_dir = state.get('last_save_dir', '')
            self._last_load_dir = state.get('last_load_dir', '')
            self._recent_files = [p for p in state.get('recent_files', []) if isinstance(p, str)]
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
        tab = self._current_tab()
        self._save_action.setEnabled(bool(tab and tab.save_path and tab.dirty))
        self._save_as_action.setEnabled(tab is not None)
        self._print_action.setEnabled(tab is not None)

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
        self._list_panel.set_adversaries(self._merged_adversaries())
        self._update_status()

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
            # Overwrite by original name so renames work correctly
            self._custom_adversaries = [
                a for a in self._custom_adversaries if a.get('name') != original.get('name')
            ]
        else:
            # Official source → remove any custom entry with the same new name
            self._custom_adversaries = [
                a for a in self._custom_adversaries if a.get('name') != entry.get('name')
            ]
        self._custom_adversaries.append(entry)
        self._save_custom_file()
        self._refresh_adversary_list()

    def _delete_custom_adversary(self, adv: dict) -> None:
        self._custom_adversaries = [
            a for a in self._custom_adversaries if a.get('name') != adv.get('name')
        ]
        self._save_custom_file()
        self._refresh_adversary_list()

    def _save_custom_file(self) -> None:
        entries = [{k: v for k, v in a.items() if k != 'homebrew'} for a in self._custom_adversaries]
        try:
            CUSTOM_FILE.parent.mkdir(parents=True, exist_ok=True)
            CUSTOM_FILE.write_text(json.dumps({'adversaries': entries}, indent=2), encoding='utf-8')
        except OSError:
            pass

    def _refresh_adversary_list(self) -> None:
        self._list_panel.set_adversaries(self._merged_adversaries())

    def _add_new_custom_adversary(self, new: dict) -> None:
        entry = {k: v for k, v in new.items() if k != 'homebrew'}
        entry['homebrew'] = True
        self._custom_adversaries = [
            a for a in self._custom_adversaries if a.get('name') != entry.get('name')
        ]
        self._custom_adversaries.append(entry)
        self._save_custom_file()
        self._refresh_adversary_list()

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
        raw = data.get('name', '')
        safe = re.sub(r'[^\w\s-]', '', raw.lower())
        safe = re.sub(r'\s+', '_', safe.strip())
        filename = (safe or 'encounter') + '.json'
        initial = str(Path(self._last_save_dir) / filename) if self._last_save_dir else filename
        path, _ = QFileDialog.getSaveFileName(
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
        if path:
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

    # ── Layout ────────────────────────────────────────────────────────────────

    def _set_layout(self, mode: str) -> None:
        self._layout_mode = mode
        orientation = Qt.Orientation.Horizontal if mode == '3col' else Qt.Orientation.Vertical
        for i in range(self._tabs.count()):
            tab = self._tabs.widget(i)
            if isinstance(tab, EncounterTab):
                tab.set_orientation(orientation)
        self._layout_3col_act.setChecked(mode == '3col')
        self._layout_2col_act.setChecked(mode == '2col')


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
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('sublevel3.daggerheart.encounter-builder')
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
