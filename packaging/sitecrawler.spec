# PyInstaller spec for the standalone, windowed sitecrawler.exe.
# Build with: uv run pyinstaller packaging/sitecrawler.spec  (output: dist/sitecrawler.exe)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = (
    # Audit rules are discovered with pkgutil, so nothing imports them by name.
    collect_submodules("sitecrawler")
    # uvicorn picks its loop, protocol and lifespan implementations at runtime.
    + collect_submodules("uvicorn")
    # The renderer imports Playwright inside functions, only when a crawl renders.
    + collect_submodules("playwright")
)

a = Analysis(
    ["sitecrawler_app.py"],
    pathex=[],
    binaries=[],
    # Templates, vendored JS/CSS and the bundled schema.org vocabulary, plus
    # Playwright's driver (node.exe and its package), which it finds beside
    # its own modules. Rendering uses the installed Edge (ADR-0015).
    datas=collect_data_files("sitecrawler") + collect_data_files("playwright"),
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff", "mkdocs", "tkinter"],
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
