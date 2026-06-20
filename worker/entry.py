"""PyInstaller entry point for auto-agent-worker."""

from app.worker.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
