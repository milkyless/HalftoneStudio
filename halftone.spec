# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包設定：單檔 exe。

本程式只用到 QtCore / QtGui / QtWidgets，因此排除所有用不到的
Qt 模組。其中 Qt6WebEngineCore.dll 單一檔案就達 194 MB，
排除後可大幅縮小體積。

產生方式：
    .venv\\Scripts\\python.exe -m PyInstaller halftone.spec --noconfirm
"""
import sys

block_cipher = None

# ── 排除清單 ───────────────────────────────────
# WebEngine：194 MB，本程式完全未使用
EXCLUDE_WEB = [
    'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngineQuick', 'PySide6.WebEngine',
    'PySide6.QtWebChannel', 'PySide6.QtWebSockets',
]

# QML / Quick：本程式為純 Widgets 介面，不需要
EXCLUDE_QML = [
    'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D',
    'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2',
    'PySide6.QtQmlModels', 'PySide6.QtQmlWorkerScript',
]

# 其餘未使用的進階模組
EXCLUDE_OTHER = [
    'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets',
    'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools',
    'PySide6.QtTest', 'PySide6.QtSql', 'PySide6.QtSpatialAudio',
    'PySide6.QtTextToSpeech', 'PySide6.QtRemoteObjects',
    'PySide6.QtScxml', 'PySide6.QtSensors', 'PySide6.QtSerialPort',
    'PySide6.QtPositioning', 'PySide6.QtNfc', 'PySide6.QtBluetooth',
    'PySide6.QtWebChannel', 'PySide6.QtHttpServer',
    'PySide6.QtConcurrent', 'PySide6.QtStateMachine',
]

# 標準函式庫中確定用不到的部分。
#
# 注意：不可排除 argparse / pydoc / email / http 等 —— PySide6 的
# shibokensupport 會 import argparse，一旦排除就會在啟動時直接崩潰
# （ModuleNotFoundError: No module named 'argparse'）。
# 這裡只保留確定無疑的項目，減少風險。
EXCLUDE_STDLIB = [
    'unittest',
    'pydoc_data',
    'test',
    'lib2to3',
    'tkinter',
    'distutils',
]

EXCLUDES = (EXCLUDE_WEB + EXCLUDE_QML + EXCLUDE_OTHER + EXCLUDE_STDLIB
            + ['PIL.ImageQt', 'PIL.ImageShow', 'numpy.distutils',
               'numpy.f2py', 'numpy.testing'])

# 動態匯入的模組：PyInstaller 靜態分析抓不到，必須手動指定，
# 否則執行時才會爆 ModuleNotFoundError。
#   secrets  -> numpy.random.bit_generator 會用到
#   hmac/_hashlib -> secrets 的相依
HIDDEN = [
    'secrets',
    'hmac',
    '_hashlib',
    'hashlib',
    'argparse',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=HIDDEN,
    # 排除模組（PyInstaller 6 改為純 list）
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='HalftoneStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # GUI 程式，不顯示主控台視窗
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='docs/halftone.ico',
    version='docs/version_info.txt',
)
