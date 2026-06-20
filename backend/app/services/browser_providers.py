"""Browser provider abstraction: local Playwright default, remote CDP adapter."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


logger = logging.getLogger(__name__)

BROWSER_CAPABILITIES = frozenset({
    "persistent_context",
    "remote_cdp",
    "recording",
    "live_view",
    "proxy",
    "captcha",
    "computer_use",
})

LOCAL_PLAYWRIGHT_CAPABILITIES = frozenset({
    "persistent_context",
    "recording",
    "live_view",
    "proxy",
    "captcha",
    "computer_use",
})

REMOTE_CDP_CAPABILITIES = frozenset({
    "remote_cdp",
    "recording",
    "live_view",
    "computer_use",
})

_SECRET_KEYS = frozenset({
    "token",
    "password",
    "secret",
    "api_key",
    "apikey",
    "access_key",
    "auth",
    "authorization",
    "credentials",
})


class UnsupportedBrowserCapabilityError(Exception):
    """Raised when a provider does not support a requested runtime feature."""


@dataclass(frozen=True)
class BrowserProviderConfig:
    provider_id: str = "local_playwright"
    config: dict[str, Any] | None = None


@dataclass
class BrowserConnection:
    context: BrowserContext
    page: Page
    provider_id: str
    metadata: dict[str, Any]
    profile_id: Optional[str] = None


class BrowserProvider(Protocol):
    provider_id: str
    capabilities: frozenset[str]

    async def create_connection(
        self,
        session_id: str,
        *,
        profile_id: Optional[str] = None,
    ) -> BrowserConnection: ...


def default_provider_config() -> BrowserProviderConfig:
    return BrowserProviderConfig(provider_id="local_playwright", config={})


def sanitize_provider_metadata(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not raw:
        return {}
    safe: dict[str, Any] = {}
    for key, value in raw.items():
        lower = key.lower()
        if lower in _SECRET_KEYS or lower.endswith("_token") or lower.endswith("_secret"):
            safe[f"has_{lower}"] = bool(value)
            continue
        if isinstance(value, dict):
            nested = sanitize_provider_metadata(value)
            if nested:
                safe[key] = nested
            continue
        safe[key] = value
    return safe


def require_capability(provider: BrowserProvider, capability: str) -> None:
    if capability not in provider.capabilities:
        raise UnsupportedBrowserCapabilityError(
            f"provider {provider.provider_id!r} does not support capability {capability!r}"
        )


_playwright: Any = None
_browser: Optional[Browser] = None


async def _ensure_local_browser() -> Browser:
    from app.services import browser_pool

    return await browser_pool._ensure_browser()


async def _connect_over_cdp(endpoint_url: str) -> Browser:
    global _playwright
    if _playwright is None:
        _playwright = await async_playwright().start()
    return await _playwright.chromium.connect_over_cdp(endpoint_url)


@dataclass
class LocalPlaywrightBrowserProvider:
    provider_id: str = "local_playwright"
    capabilities: frozenset[str] = LOCAL_PLAYWRIGHT_CAPABILITIES

    async def create_connection(
        self,
        session_id: str,
        *,
        profile_id: Optional[str] = None,
    ) -> BrowserConnection:
        from app.services.antibot import apply_stealth_if_enabled
        from app.services.browser_capture import attach_download_listener, prepare_har_context_option
        from app.services.browser_context import resolve_context_options

        browser = await _ensure_local_browser()
        context_kwargs = resolve_context_options(session_id, profile_id)
        context_kwargs.update(prepare_har_context_option(session_id))
        context = await browser.new_context(**context_kwargs)
        await apply_stealth_if_enabled(context)
        page = await context.new_page()
        attach_download_listener(session_id, page)
        return BrowserConnection(
            context=context,
            page=page,
            provider_id=self.provider_id,
            metadata={"mode": "local"},
            profile_id=profile_id,
        )


@dataclass
class RemoteCdpBrowserProvider:
    endpoint_url: str
    token: Optional[str] = None
    provider_id: str = "remote_cdp"
    capabilities: frozenset[str] = REMOTE_CDP_CAPABILITIES

    async def create_connection(
        self,
        session_id: str,
        *,
        profile_id: Optional[str] = None,
    ) -> BrowserConnection:
        if profile_id:
            raise UnsupportedBrowserCapabilityError(
                "remote CDP provider does not support persistent_context profiles"
            )
        endpoint = self.endpoint_url.strip()
        if self.token:
            sep = "&" if "?" in endpoint else "?"
            endpoint = f"{endpoint}{sep}token={self.token}"
        browser = await _connect_over_cdp(endpoint)
        contexts = getattr(browser, "contexts", None) or []
        if contexts:
            context = contexts[0]
            pages = getattr(context, "pages", None) or []
            page = pages[0] if pages else await context.new_page()
        else:
            context = await browser.new_context()
            page = await context.new_page()
        from app.services.browser_capture import attach_download_listener

        attach_download_listener(session_id, page)
        metadata = sanitize_provider_metadata({
            "endpoint_url": self.endpoint_url,
            "token": self.token,
        })
        return BrowserConnection(
            context=context,
            page=page,
            provider_id=self.provider_id,
            metadata=metadata,
            profile_id=None,
        )


def get_provider(config: Optional[BrowserProviderConfig] = None) -> BrowserProvider:
    cfg = config or default_provider_config()
    provider_id = (cfg.provider_id or "local_playwright").strip().lower()
    raw = dict(cfg.config or {})
    if provider_id == "local_playwright":
        return LocalPlaywrightBrowserProvider()
    if provider_id == "remote_cdp":
        endpoint = str(raw.get("endpoint_url") or "").strip()
        if not endpoint:
            raise ValueError("remote CDP provider requires endpoint_url")
        token = raw.get("token")
        token_str = str(token).strip() if token else None
        return RemoteCdpBrowserProvider(endpoint_url=endpoint, token=token_str or None)
    raise ValueError(f"unknown browser provider {provider_id!r}")


async def create_browser_connection(
    session_id: str,
    *,
    profile_id: Optional[str] = None,
    config: Optional[BrowserProviderConfig] = None,
) -> BrowserConnection:
    provider = get_provider(config)
    return await provider.create_connection(session_id, profile_id=profile_id)


async def shutdown_providers() -> None:
    from app.services import browser_pool

    await browser_pool.shutdown()


__all__ = [
    "BROWSER_CAPABILITIES",
    "BrowserConnection",
    "BrowserProvider",
    "BrowserProviderConfig",
    "LocalPlaywrightBrowserProvider",
    "RemoteCdpBrowserProvider",
    "UnsupportedBrowserCapabilityError",
    "create_browser_connection",
    "default_provider_config",
    "get_provider",
    "require_capability",
    "sanitize_provider_metadata",
    "shutdown_providers",
]
