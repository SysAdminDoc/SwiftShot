# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['app', 'config', 'theme', 'hotkeys', 'capture', 'capture_menu', 'overlay', 'window_picker', 'monitor_picker', 'editor', 'settings_dialog', 'ocr', 'ocr_dialog', 'pin_window', 'capture_history', 'countdown_overlay', 'scrolling_capture', 'utils', 'PyQt5.QtPrintSupport', 'PyQt5.sip', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets']
hiddenimports += collect_submodules('PyQt5.QtCore')
hiddenimports += collect_submodules('PyQt5.QtGui')
hiddenimports += collect_submodules('PyQt5.QtWidgets')
hiddenimports += collect_submodules('PyQt5.QtPrintSupport')
hiddenimports += collect_submodules('PyQt5.sip')


a = Analysis(
    ['C:\\Users\\--\\Downloads\\swiftshot_upload\\main.py'],
    pathex=['C:\\Users\\--\\Downloads\\swiftshot_upload'],
    binaries=[],
    datas=[('C:\\Users\\--\\Downloads\\swiftshot_upload\\swiftshot.ico', '.'), ('C:\\Users\\--\\Downloads\\swiftshot_upload\\swiftshot.png', '.')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas', 'test', 'unittest', 'pydoc', 'doctest', 'lib2to3', 'setuptools', 'PyQt5.Qt3D', 'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtSql', 'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtSensors', 'PyQt5.QtSerialPort', 'PyQt5.QtLocation', 'PyQt5.QtPositioning', 'PyQt5.QtRemoteObjects', 'PyQt5.QtWebSockets', 'PyQt5.QtWebChannel', 'PyQt5.QtDesigner', 'PyQt5.uic'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SwiftShot',
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
    version='C:\\Users\\--\\Downloads\\swiftshot_upload\\version_info.txt',
    icon=['C:\\Users\\--\\Downloads\\swiftshot_upload\\swiftshot.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SwiftShot',
)
