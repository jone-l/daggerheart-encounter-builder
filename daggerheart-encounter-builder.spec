# -*- mode: python ; coding: utf-8 -*-
import sys

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

_icon = 'assets/icons/DH_CGL_logo.png'

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
    icon=_icon,
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

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='DaggerheartEncounterBuilder.app',
        icon=_icon,
        bundle_identifier='org.sublevel3.daggerheart.encounter-builder',
        info_plist={
            'NSHighResolutionCapable': True,
            'NSPrincipalClass': 'NSApplication',
        },
    )
