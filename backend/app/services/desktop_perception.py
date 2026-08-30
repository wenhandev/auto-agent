"""Build LLM-facing observations from DesktopAppState."""

from __future__ import annotations

import io
from typing import Any

from app.services.desktop_computer_use.protocol import DesktopAppState, DesktopElement
from app.services.perception import (
    ElementSignature,
    IndexedElement,
    Observation,
    make_element_ref,
)


def downsample_png_for_llm(data: bytes, *, max_side: int = 1280) -> bytes:
    """Shrink screenshots before sending to vision LLMs; keep original for artifacts."""
    if not data or max_side <= 0:
        return data
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        w, h = img.size
        scale = min(1.0, float(max_side) / float(max(w, h)))
        if scale >= 0.999:
            return data
        resized = img.resize(
            (max(1, int(w * scale)), max(1, int(h * scale))),
            Image.Resampling.LANCZOS,
        )
        buf = io.BytesIO()
        resized.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception:
        return data


def indexed_from_desktop_elements(elements: list[DesktopElement]) -> list[IndexedElement]:
    out: list[IndexedElement] = []
    for el in elements:
        sig = ElementSignature(role=el.role, name=el.name)
        out.append(
            IndexedElement(
                index=el.index,
                role=el.role,
                name=el.name,
                signature=sig,
                ref=make_element_ref(el.role, el.name, el.index),
                signature_metadata={
                    "role": el.role,
                    "name": el.name,
                    "index": el.index,
                    "value": el.value,
                    "ax_ref": el.ax_ref,
                },
            )
        )
    return out


def observation_from_desktop_state(state: DesktopAppState) -> Observation:
    """Map desktop state into the shared Observation shape (url slot = app id)."""
    return Observation(
        url=f"desktop://{state.app.bundle_id or state.app.app_id}",
        title=state.title,
        screenshot_bytes=state.screenshot_bytes,
        screenshot_ref=state.screenshot_ref,
        ax_snapshot=state.ax_snapshot,
        elements=indexed_from_desktop_elements(state.elements),
        page_text_summary=state.title,
    )


def compact_desktop_observation(state: DesktopAppState) -> dict[str, Any]:
    return observation_from_desktop_state(state).compact_payload()
