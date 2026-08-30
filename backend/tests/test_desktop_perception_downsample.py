"""desktop_perception helpers."""

from __future__ import annotations

import io

import pytest

from app.services.desktop_perception import downsample_png_for_llm


def test_downsample_png_for_llm_empty() -> None:
    assert downsample_png_for_llm(b"") == b""


def test_downsample_png_for_llm_passthrough_without_valid_image() -> None:
    blob = b"not-a-png"
    assert downsample_png_for_llm(blob) == blob


def test_downsample_png_for_llm_shrinks_large_image() -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    img = Image.new("RGB", (2400, 1600), color=(20, 40, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()
    out = downsample_png_for_llm(raw, max_side=800)
    assert len(out) < len(raw)
    w, h = Image.open(io.BytesIO(out)).size
    assert max(w, h) <= 800
