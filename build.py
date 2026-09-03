"""Build script for Infrabases Desktop App.

Usage:
    python build.py              # Build both backend + frontend + electron
    python build.py --backend    # Build only Python backend (PyInstaller)
    python build.py --frontend   # Build only frontend (Vite)
    python build.py --electron   # Build only Electron installer
"""

import subprocess
import sys
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"


def run(cmd: list[str], cwd: Path = ROOT, **kwargs):
    """Run a command and exit on failure."""
    print(f"\n{'='*60}")
    print(f"  Running: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=str(cwd), **kwargs)
    if result.returncode != 0:
        print(f"\n❌ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def build_backend():
    """Build Python backend with PyInstaller."""
    print("\n🔧 Building Python backend (PyInstaller)...")
    # Clean previous build
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            shutil.rmtree(p)

    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "tiktok-backend",
        "--add-data", f"core{os.pathsep}core",
        "--add-data", f"desktop{os.pathsep}desktop",
        "--hidden-import", "uvicorn",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "desktop/ws_server.py",
    ])

    exe = DIST / "tiktok-backend.exe"
    if exe.exists():
        size_mb = exe.stat().st_size / (1024 * 1024)
        print(f"\n✅ Backend built: {exe} ({size_mb:.1f} MB)")
    else:
        print("\n❌ Backend build failed — exe not found")
        sys.exit(1)


def build_frontend():
    """Build React frontend with Vite."""
    print("\n🎨 Building frontend (Vite)...")
    run([sys.executable, "-m", "npm", "run", "build"])
    static = ROOT / "web" / "static" / "index.html"
    if static.exists():
        print(f"\n✅ Frontend built: {static.parent}")
    else:
        print("\n❌ Frontend build failed")
        sys.exit(1)


def build_electron():
    """Build Electron installer."""
    print("\n📦 Building Electron installer (electron-builder)...")

    # Copy backend exe to dist/ for electron-builder
    backend_exe = DIST / "tiktok-backend.exe"
    if not backend_exe.exists():
        print("⚠️  tiktok-backend.exe not found in dist/. Run --backend first.")
        sys.exit(1)

    run([sys.executable, "-m", "npm", "run", "dist:win"])

    # Find the installer
    for f in DIST.glob("*.exe"):
        if "tiktok-backend" not in f.name:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"\n✅ Installer built: {f} ({size_mb:.1f} MB)")
            return

    print("\n⚠️  Installer not found in dist/")


def main():
    args = set(sys.argv[1:])

    if not args or "--backend" in args:
        build_backend()
    if not args or "--frontend" in args:
        build_frontend()
    if not args or "--electron" in args:
        build_electron()

    print("\n" + "=" * 60)
    print("  🎉 Build complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
