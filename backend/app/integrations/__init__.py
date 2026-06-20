"""Integration descriptor registry and typed credential framework."""

from app.integrations.registry import get_registry, load_integrations

__all__ = ["get_registry", "load_integrations"]
