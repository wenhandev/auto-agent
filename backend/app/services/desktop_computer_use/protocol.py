"""Desktop Computer Use backend protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable


class DesktopComputerUseUnavailableError(Exception):
    """Raised when desktop Computer Use is not available on this runtime."""


class DesktopAppAuthorizationError(Exception):
    """Raised when the target app is not authorized for Computer Use."""


class DesktopAppForbiddenError(Exception):
    """Raised when the target app is hard-denied."""


@dataclass
class DesktopAppInfo:
    app_id: str
    name: str
    bundle_id: str = ""
    pid: Optional[int] = None
    frontmost: bool = False

    def __post_init__(self) -> None:
        if not self.bundle_id:
            self.bundle_id = self.app_id


@dataclass
class DesktopElement:
    index: int
    role: str
    name: str
    value: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    ax_ref: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)


@dataclass
class DesktopAppState:
    app: DesktopAppInfo
    title: str
    screenshot_bytes: bytes
    screenshot_ref: str
    elements: list[DesktopElement] = field(default_factory=list)
    ax_snapshot: dict[str, Any] = field(default_factory=dict)

    def compact_payload(self) -> dict[str, Any]:
        return {
            "app_id": self.app.app_id,
            "bundle_id": self.app.bundle_id,
            "name": self.app.name,
            "title": self.title,
            "screenshot_ref": self.screenshot_ref,
            "elements": [
                {
                    "index": el.index,
                    "role": el.role,
                    "name": el.name,
                    **({"value": el.value} if el.value else {}),
                }
                for el in self.elements[:80]
            ],
        }


@runtime_checkable
class DesktopComputerUseBackend(Protocol):
    """Platform backend for native desktop Computer Use."""

    provider_id: str

    async def list_apps(self) -> list[DesktopAppInfo]: ...

    async def open_app(self, app: str) -> DesktopAppInfo: ...

    async def get_app_state(self, app: str) -> DesktopAppState: ...

    async def click(
        self,
        app: str,
        *,
        index: Optional[int] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
    ) -> dict[str, Any]: ...

    async def type_text(
        self,
        app: str,
        text: str,
        *,
        index: Optional[int] = None,
    ) -> dict[str, Any]: ...

    async def key(self, app: str, key: str) -> dict[str, Any]: ...

    async def scroll(
        self,
        app: str,
        direction: str,
        amount: int = 3,
    ) -> dict[str, Any]: ...
