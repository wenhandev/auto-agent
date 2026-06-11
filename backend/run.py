"""Dev runner that keeps Playwright happy on Windows.

uvicorn's asyncio loop factory picks SelectorEventLoop whenever
`reload=True` (see Config.use_subprocess), and that loop cannot
spawn subprocesses on Windows -- which breaks Playwright's
chromium.launch().

Workaround: install the Proactor event loop policy ourselves and
tell uvicorn loop="none" so it doesn't override us.

Usage:
    python run.py
    AUTO_AGENT_PORT=8002 python run.py
"""
from __future__ import annotations

import asyncio
import os
import sys

import uvicorn

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

if __name__ == "__main__":
    port = int(os.environ.get("AUTO_AGENT_PORT", "8001"))
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=True,
        loop="none",
    )
