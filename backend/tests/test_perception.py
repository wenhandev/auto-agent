"""Perception layer tests — deterministic element map from fixture snapshots."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.perception import (
    control_tree,
    elements_from_ax_snapshot,
    perceive,
    resolve_element,
    Observation,
    ElementSignature,
    IndexedElement,
)


FIXTURE_AX: dict[str, Any] = {
    "role": "WebArea",
    "name": "Shop",
    "children": [
        {
            "role": "navigation",
            "name": "Main",
            "children": [
                {"role": "link", "name": "Home"},
                {"role": "link", "name": "Products"},
            ],
        },
        {"role": "button", "name": "Add to cart"},
        {"role": "textbox", "name": "Email", "focusable": True},
        {
            "role": "group",
            "name": "Static copy",
            "children": [{"role": "text", "name": "Welcome to our store"}],
        },
    ],
}


def test_element_map_numbering_is_deterministic() -> None:
    first = elements_from_ax_snapshot(FIXTURE_AX)
    second = elements_from_ax_snapshot(FIXTURE_AX)

    assert len(first) == 4
    assert [e.index for e in first] == [0, 1, 2, 3]
    assert [(e.role, e.name) for e in first] == [
        ("link", "Home"),
        ("link", "Products"),
        ("button", "Add to cart"),
        ("textbox", "Email"),
    ]
    assert [(e.role, e.name) for e in second] == [(e.role, e.name) for e in first]


def test_compact_payload_omits_static_noise() -> None:
    elements = elements_from_ax_snapshot(FIXTURE_AX)
    obs = Observation(
        url="https://shop.example",
        title="Shop",
        screenshot_bytes=b"png",
        screenshot_ref="/tmp/x.png",
        ax_snapshot=FIXTURE_AX,
        elements=elements,
        page_text_summary="Welcome to our store",
    )
    payload = obs.compact_payload()
    assert "Welcome" in payload["page_text_summary"]
    assert len(payload["elements"]) == 4
    assert payload["elements"][2]["role"] == "button"
    assert "children" not in payload
    assert "2. [button] Add to cart" in payload["tree"]


def test_control_tree_is_numbered_click_list() -> None:
    elements = elements_from_ax_snapshot(FIXTURE_AX)
    tree = control_tree(elements)
    assert tree.splitlines()[0] == "0. [link] Home"
    assert "2. [button] Add to cart" in tree


class _BlankPage:
    url = "about:blank"

    async def title(self) -> str:
        return ""

    async def screenshot(self, **_: Any) -> bytes:
        return b"blank"

    def locator(self, _selector: str) -> Any:
        page = self

        class _Loc:
            async def inner_text(self_inner) -> str:  # noqa: N805
                return ""

        return _Loc()

    @property
    def accessibility(self) -> Any:
        class _Ax:
            async def snapshot(self_inner) -> dict[str, Any]:  # noqa: N805
                return {"role": "WebArea", "name": "", "children": []}

        return _Ax()


@pytest.mark.asyncio
async def test_blank_page_returns_empty_interactive_list() -> None:
    page = _BlankPage()
    obs = await perceive(page)
    assert obs.url == "about:blank"
    assert obs.elements == []
    assert obs.screenshot_ref


class _ResolvePage:
    def __init__(self) -> None:
        self._calls = 0

    def get_by_role(self, role: str, name: str | None = None) -> Any:
        page = self

        class _Loc:
            async def count(self_inner) -> int:  # noqa: N805
                return 0

        return _Loc()

    def get_by_text(self, text: str, exact: bool = False) -> Any:
        return self.get_by_role("text", text)


@pytest.mark.asyncio
async def test_resolve_reperceives_once_on_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _ResolvePage()
    perceive_calls = 0

    async def fake_perceive(p, *, ref_hint: str = "") -> Observation:
        nonlocal perceive_calls
        perceive_calls += 1
        elements = [
            IndexedElement(
                index=0,
                role="button",
                name="Go",
                signature=ElementSignature(role="button", name="Go"),
            )
        ]
        return Observation(
            url="https://example.com",
            title="Ex",
            screenshot_bytes=b"x",
            screenshot_ref=f"ref-{perceive_calls}",
            ax_snapshot={},
            elements=elements,
        )

    monkeypatch.setattr("app.services.perception.perceive", fake_perceive)

    obs = Observation(
        url="https://example.com",
        title="Ex",
        screenshot_bytes=b"x",
        screenshot_ref="initial",
        ax_snapshot={},
        elements=[
            IndexedElement(
                index=0,
                role="button",
                name="Go",
                signature=ElementSignature(role="button", name="Go"),
            )
        ],
    )

    locator, new_obs = await resolve_element(page, obs, 0)
    assert locator is None
    assert perceive_calls == 1
    assert new_obs.screenshot_ref == "ref-1"
