# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['spryta_startup.pyw'],
    pathex=['.', 'src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tools.process_manager',
        'ui.tray_icon',
        'ui.theme_dark',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PIL',
        'PIL.Image',
        'win32gui',
        'win32con',
        'win32api',
        'pywintypes',
        'psutil',
        'json',
        'configparser',
        'subprocess',
        'threading',
        'time',
        'ctypes',
        'ctypes.wintypes',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pygame',
        'cv2',
        'keyboard',
        'tkinter',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='spryta_startup',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icons/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='spryta_startup',
)
