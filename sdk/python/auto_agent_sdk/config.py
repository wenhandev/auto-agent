from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class CliConfig:
    base_url: str
    api_key: str


def _default_config_path() -> Path:
    return Path.home() / ".config" / "auto-agent" / "config"


def _resolve_config_path() -> Path | None:
    explicit = os.environ.get("AUTO_AGENT_CONFIG", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    default = _default_config_path()
    return default if default.is_file() else None


def _parse_config_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in {"base_url", "AUTO_AGENT_BASE_URL"}:
            values["base_url"] = value
        elif key in {"api_key", "AUTO_AGENT_API_KEY"}:
            values["api_key"] = value
    return values


def _assert_safe_config_permissions(path: Path) -> None:
    if sys.platform == "win32":
        return
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(
            f"Config file {path} must be readable only by the owner (mode 0600). "
            "Run: chmod 600 "
            + str(path)
        )


def load_config(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    config_path: Path | None = None,
) -> CliConfig:
    file_values: dict[str, str] = {}
    resolved_path = config_path
    if resolved_path is None and base_url is None and api_key is None:
        resolved_path = _resolve_config_path()
    if resolved_path is not None:
        path = resolved_path.expanduser()
        if not path.is_file():
            raise ConfigError(f"Config file not found: {path}")
        _assert_safe_config_permissions(path)
        file_values = _parse_config_file(path)

    resolved_base = (
        base_url
        or os.environ.get("AUTO_AGENT_BASE_URL", "").strip()
        or file_values.get("base_url", "")
    )
    resolved_key = (
        api_key
        or os.environ.get("AUTO_AGENT_API_KEY", "").strip()
        or file_values.get("api_key", "")
    )

    missing: list[str] = []
    if not resolved_base:
        missing.append("AUTO_AGENT_BASE_URL")
    if not resolved_key:
        missing.append("AUTO_AGENT_API_KEY")
    if missing:
        raise ConfigError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Set environment variables or a config file."
        )
    return CliConfig(base_url=resolved_base, api_key=resolved_key)
