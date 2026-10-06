# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-спецификация: Windows-exe (onefile, без консоли).

Сборка на Windows:
    pyinstaller --noconfirm --clean finance.spec
Результат: dist/PersonalFinance.exe
База данных (finance.db) создаётся рядом с exe.
"""
a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=["finance.importers", "finance.ui.app"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PersonalFinance",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)