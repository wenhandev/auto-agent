# PyInstaller spec for auto-agent-worker (onedir bundle; Windows, macOS, Linux).
#
# Build on each target OS (PyInstaller cannot cross-compile):
#   Windows:  .\worker\build-exe.ps1
#   macOS:    ./worker/build-macos.sh
#   Linux:    ./worker/build-linux.sh
# Or manually:
#   cd backend && pip install -e ".[worker-build]"
#   pyinstaller ../worker/auto-agent-worker.spec --noconfirm --clean

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

repo_root = Path(SPECPATH).resolve().parent
backend = repo_root / "backend"
entry = repo_root / "worker" / "entry.py"

hiddenimports = collect_submodules("app.worker")
hiddenimports += collect_submodules("app.services")
hiddenimports += collect_submodules("app.nodes")
hiddenimports += collect_submodules("app.tools")
hiddenimports += collect_submodules("app.exec")
hiddenimports += [
    "app.worker.cli",
    "app.services.runtime_engine",
    "app.services.browser_pool",
    "app.services.browser_context",
    "app.services.browser_primitives",
    "app.services.browser_providers",
    "app.services.browser_profiles",
    "app.services.credential_service",
    "app.services.credential_interpolation",
    "app.services.variable_interpolation",
    "app.services.flow_conditions",
    "app.services.artifacts",
    "app.services.session_recording",
    "app.services.llm_runtime",
    "app.worker.llm_proxy",
    "app.worker.artifact_relay",
    "app.worker.run_inputs",
    "app.db.session",
    "app.db.models",
    "app.settings",
    "app.schemas",
    "sqlmodel",
    "sqlalchemy.dialects.sqlite",
    "websockets",
    "httpx",
    "pydantic",
    "pydantic_settings",
    "greenlet",
]

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []

for pkg in ("playwright", "greenlet"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    [str(entry)],
    pathex=[str(backend)],
    binaries=binaries,
    datas=datas,
    hiddenimports=list(dict.fromkeys(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "IPython",
        "pytest",
        "uvicorn",
        "fastapi",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="auto-agent-worker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="auto-agent-worker",
)
