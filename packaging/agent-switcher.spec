# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.compat import is_win
from PyInstaller.utils.hooks import collect_data_files, copy_metadata


PROJECT_ROOT = Path(SPECPATH).parent
ENTRYPOINT = PROJECT_ROOT / "packaging" / "pyinstaller_entry.py"
QTAWESOME_RUNTIME_HOOK = PROJECT_ROOT / "packaging" / "pyi_rth_qtawesome_slim.py"


def _keep_runtime_file(entry):
    """Keep only the Qt runtime used by this widgets-only application."""
    destination = entry[0].replace("\\", "/").lower()

    unused_qt_libraries = (
        "libqt6eglfsdeviceintegration",
        "libqt6eglfsKmssupport".lower(),
        "libqt6network",
        "libqt6openglwidgets",
        "libqt6pdf",
        "libqt6qml",
        "libqt6quick",
        "libqt6virtualkeyboard",
        "pyside6/qtopengl.",
        "pyside6/qtopenglwidgets.",
        "pyside6/qtnetwork.",
        "pyside6/qtpdf.",
        "pyside6/qtqml.",
        "pyside6/qtquick.",
    )
    if any(name in destination for name in unused_qt_libraries):
        return False

    unused_plugin_folders = (
        "/plugins/egldeviceintegrations/",
        "/plugins/generic/",
        "/plugins/networkinformation/",
        "/plugins/platformthemes/",
        "/plugins/tls/",
    )
    if any(folder in destination for folder in unused_plugin_folders):
        return False

    if "/plugins/platforminputcontexts/" in destination:
        return "virtualkeyboard" not in destination

    if "/plugins/platforms/" in destination:
        supported = (
            "qminimal",
            "qoffscreen",
            "qwayland",
            "qwindows",
            "qxcb",
        )
        return any(name in Path(destination).name for name in supported)

    if "/plugins/imageformats/" in destination:
        supported = ("qico", "qsvg")
        return any(name in Path(destination).name for name in supported)

    return True


datas = collect_data_files("qdarktheme")
datas += collect_data_files("agent_switcher")
datas += copy_metadata("agent-switcher")

a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(QTAWESOME_RUNTIME_HOOK)],
    excludes=[
        "PySide6.QtBluetooth",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtLocation",
        "PySide6.QtMultimedia",
        "PySide6.QtNetwork",
        "PySide6.QtNetworkAuth",
        "PySide6.QtOpenGL",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf",
        "PySide6.QtPositioning",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtRemoteObjects",
        "PySide6.QtScxml",
        "PySide6.QtSensors",
        "PySide6.QtSerialBus",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "PySide6.QtWebChannel",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
    ],
    noarchive=False,
    optimize=2,
)

# QtAwesome ships a dozen complete icon families. Agent Switcher uses only the
# Font Awesome 5 solid family, so omit the other fonts and their charmaps.
qtawesome_font_files = {
    "fontawesome5-solid-webfont-5.15.4.ttf",
    "fontawesome5-solid-webfont-charmap-5.15.4.json",
}
a.datas = [
    entry
    for entry in a.datas
    if "/qtawesome/fonts/" not in f"/{entry[0].replace(chr(92), '/').lower()}"
    or Path(entry[0]).name in qtawesome_font_files
]

# The app does not install a QTranslator, so bundled Qt translations are dead
# weight; Agent Switcher's own English/Persian translations remain included.
a.datas = [
    entry
    for entry in a.datas
    if "/pyside6/qt/translations/" not in f"/{entry[0].replace(chr(92), '/').lower()}"
]

# Linux distributions already provide their core runtime libraries. Avoid
# embedding host copies that add size and can conflict with the user's system.
if not is_win:
    a.exclude_system_libraries(["libgcc_s*", "libstdc++*"])

a.binaries = [entry for entry in a.binaries if _keep_runtime_file(entry)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [("O", None, "OPTION"), ("O", None, "OPTION")],
    name="agent-switcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=not is_win,
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
