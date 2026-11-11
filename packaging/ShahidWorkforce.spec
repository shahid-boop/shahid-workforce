# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Shahid Workforce Windows EXE.

Build (after `npm run build:static` has produced apps/dashboard/out):

    pyinstaller packaging/ShahidWorkforce.spec --distpath dist --workpath build

One-file double-clickable EXE that runs the API and serves the static
dashboard from the bundle; data/config live in %LOCALAPPDATA%\\ShahidWorkforce.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # repo root (spec lives in packaging/)

# --- hidden imports ---------------------------------------------------------
# litellm resolves providers/helpers dynamically; tiktoken loads its BPE
# tables through importlib entry points that PyInstaller cannot trace.
hiddenimports: list[str] = []
for package in ("litellm", "tiktoken"):
    hiddenimports += collect_submodules(package)
hiddenimports += ["tiktoken_ext", "tiktoken_ext.openai_public"]

hiddenimports += collect_submodules("services")
hiddenimports += collect_submodules("database")
hiddenimports += collect_submodules("agents")
hiddenimports += collect_submodules("tools")

# uvicorn's pluggable defaults are imported by name only.
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.asyncio",
    "anyio._backends._asyncio",
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
]

# --- data files -------------------------------------------------------------
datas = [
    (str(ROOT / "agents" / "prompts"), "agents/prompts"),
    (str(ROOT / "agents" / "configs"), "agents/configs"),
]
# Non-Python assets litellm expects inside its package (tweaks, UI, etc.).
datas += collect_data_files("litellm")

dashboard_out = ROOT / "apps" / "dashboard" / "out"
if (dashboard_out / "index.html").is_file():
    datas.append((str(dashboard_out), "dashboard"))
else:
    raise SystemExit(
        "apps/dashboard/out is missing - run `npm run build:static` first "
        "in apps/dashboard (stop `npm run dev` on Windows)."
    )

analysis = Analysis(
    [str(ROOT / "apps" / "desktop" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "mypy", "langsmith"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ShahidWorkforce",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # keep a console for first-run diagnostics
    disable_windowed_traceback=False,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="ShahidWorkforce",
)
