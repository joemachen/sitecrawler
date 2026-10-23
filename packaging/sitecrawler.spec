# PyInstaller spec for the standalone, windowed sitecrawler.exe.
# Build with: uv run pyinstaller packaging/sitecrawler.spec  (output: dist/sitecrawler.exe)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = (
    # Audit rules are discovered with pkgutil, so nothing imports them by name.
    collect_submodules("sitecrawler")
    # uvicorn picks its loop, protocol and lifespan implementations at runtime.
    + collect_submodules("uvicorn")
)

a = Analysis(
    ["sitecrawler_app.py"],
    pathex=[],
    binaries=[],
    # Templates, vendored JS/CSS and the bundled schema.org vocabulary.
    datas=collect_data_files("sitecrawler"),
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Rendering needs a Chromium download the exe cannot ship; the rest are dev tools.
    excludes=["playwright", "pytest", "mypy", "ruff", "mkdocs", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sitecrawler",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
