"""Build script for the Infrabases TikTok & Douyin Downloader.

Builds the React frontend with Vite into apps/web/static, which is
served directly by the FastAPI app (apps/web/app.py).

Usage:
    python scripts/build.py            # Build frontend (default)
    python scripts/build.py --frontend # Same as default
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "apps" / "web" / "static"


def run(cmd: list[str], cwd: Path = ROOT, **kwargs):
    """Run a command and exit on failure."""
    print(f"\n{'='*60}")
    print(f"  Running: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=str(cwd), **kwargs)
    if result.returncode != 0:
        print(f"\n❌ Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def build_frontend():
    """Build React frontend with Vite into apps/web/static."""
    print("\n🎨 Building frontend (Vite)...")
    run(["npm", "run", "build"])
    index = STATIC / "index.html"
    if index.exists():
        print(f"\n✅ Frontend built: {STATIC}")
    else:
        print("\n❌ Frontend build failed — index.html not found")
        sys.exit(1)


def main():
    args = set(sys.argv[1:])

    if not args or "--frontend" in args:
        build_frontend()

    print("\n" + "=" * 60)
    print("  🎉 Build complete! Run the web app with:")
    print("     python -m uvicorn apps.web.app:app --host 127.0.0.1 --port 8080")
    print("=" * 60)


if __name__ == "__main__":
    main()
