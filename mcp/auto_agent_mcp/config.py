from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class McpConfig:
    base_url: str
    api_key: str


def load_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> McpConfig:
    resolved_base = (base_url or os.environ.get("AUTO_AGENT_BASE_URL", "")).strip()
    resolved_key = (api_key or os.environ.get("AUTO_AGENT_API_KEY", "")).strip()

    missing: list[str] = []
    if not resolved_base:
        missing.append("AUTO_AGENT_BASE_URL")
    if not resolved_key:
        missing.append("AUTO_AGENT_API_KEY")
    if missing:
        raise ConfigError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Set environment variables or pass values explicitly."
        )
    return McpConfig(base_url=resolved_base, api_key=resolved_key)
