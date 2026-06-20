"""Environment preflight checks before worker connects."""

from __future__ import annotations

import platform
import shutil
from typing import Any


def _check_playwright_installed() -> dict[str, Any]:
    try:
        import playwright  # noqa: F401

        return {"id": "playwright_installed", "status": "pass", "message": "playwright package available"}
    except ImportError:
        return {"id": "playwright_installed", "status": "fail", "message": "pip install playwright"}


def _check_chromium_binary() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
        if path:
            return {"id": "chromium_binary", "status": "pass", "message": path}
    except Exception as exc:
        return {
            "id": "chromium_binary",
            "status": "fail",
            "message": f"run playwright install chromium ({exc})",
        }
    return {"id": "chromium_binary", "status": "fail", "message": "chromium not installed"}


def _check_disk_space() -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(".")
        free_gb = usage.free / (1024**3)
        if free_gb < 1:
            return {"id": "disk_space", "status": "fail", "message": f"{free_gb:.1f} GB free"}
        if free_gb < 5:
            return {"id": "disk_space", "status": "warn", "message": f"{free_gb:.1f} GB free"}
        return {"id": "disk_space", "status": "pass", "message": f"{free_gb:.1f} GB free"}
    except Exception as exc:
        return {"id": "disk_space", "status": "warn", "message": str(exc)}


def _check_memory() -> dict[str, Any]:
    try:
        import psutil  # type: ignore[import-untyped]

        avail_gb = psutil.virtual_memory().available / (1024**3)
        if avail_gb < 0.5:
            return {"id": "memory", "status": "fail", "message": f"{avail_gb:.1f} GB available"}
        if avail_gb < 2:
            return {"id": "memory", "status": "warn", "message": f"{avail_gb:.1f} GB available"}
        return {"id": "memory", "status": "pass", "message": f"{avail_gb:.1f} GB available"}
    except ImportError:
        return {"id": "memory", "status": "warn", "message": "psutil not installed; skipped"}
    except Exception as exc:
        return {"id": "memory", "status": "warn", "message": str(exc)}


async def check_cloud_reachable(cloud_url: str) -> dict[str, Any]:
    import httpx

    base = cloud_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(f"{base}/api/health")
        if res.status_code < 500:
            return {"id": "cloud_reachable", "status": "pass", "message": base}
    except Exception as exc:
        return {"id": "cloud_reachable", "status": "fail", "message": str(exc)}
    return {"id": "cloud_reachable", "status": "fail", "message": f"HTTP {res.status_code}"}


def aggregate_environment(checks: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = [str(c.get("status") or "fail") for c in checks]
    if any(s == "fail" for s in statuses):
        env_status = "not_ready"
    elif any(s == "warn" for s in statuses):
        env_status = "degraded"
    else:
        env_status = "ready"
    return {
        "environment_status": env_status,
        "checks": checks,
        "capabilities": {
            "playwright": any(c.get("id") == "playwright_installed" and c.get("status") == "pass" for c in checks),
            "chromium": any(c.get("id") == "chromium_binary" and c.get("status") == "pass" for c in checks),
            "platform": platform.system(),
        },
    }


def run_local_checks() -> dict[str, Any]:
    checks = [
        _check_playwright_installed(),
        _check_chromium_binary(),
        _check_disk_space(),
        _check_memory(),
    ]
    return aggregate_environment(checks)


async def run_doctor(cloud_url: str | None = None) -> dict[str, Any]:
    checks = [
        _check_playwright_installed(),
        _check_chromium_binary(),
        _check_disk_space(),
        _check_memory(),
    ]
    if cloud_url:
        checks.append(await check_cloud_reachable(cloud_url))
    return aggregate_environment(checks)


__all__ = ["run_doctor", "run_local_checks", "aggregate_environment"]
