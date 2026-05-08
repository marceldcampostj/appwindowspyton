# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main_interface.py'],
    pathex=[],
    binaries=[],
    datas=[('788.ico', '.')],
    hiddenimports=[
        'asyncio',
        'aiomysql',
        'pystray',
        'pystray._win32',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageTk',
        'tkinter',
        'tkinter.scrolledtext',
        'tkinter.ttk',
        'tkinter.font',
        'tkinter.messagebox',
        'json',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SincronizadorLoja7',
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
    icon=['788.ico'],
)
