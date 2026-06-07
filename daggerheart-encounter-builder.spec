# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Daggerheart Encounter Builder

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('sources.json', '.'),   # source manifest bundled at _internal root
        ('assets',       'assets'),
    ],
    # QPrinter / QPrintPreviewDialog live in QtPrintSupport — not always auto-detected.
    # pdfplumber is pulled in via extract.py but declare it explicitly for safety.
    hiddenimports=['PySide6.QtPrintSupport', 'pdfplumber'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DaggerheartEncounterBuilder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/icons/DH_CGL_logo.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DaggerheartEncounterBuilder',
)
