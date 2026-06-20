"""Tests for autonomous error normalization."""

from app.agents.autonomous_errors import (
    is_reason_code,
    is_technical_message,
    normalize_tool_error,
    user_failure_message,
)


def test_is_technical_message_detects_playwright() -> None:
    raw = "Locator.click: Timeout 30000ms exceeded.\nCall log:\n - waiting"
    assert is_technical_message(raw)


def test_normalize_tool_error_click_blocked() -> None:
    raw = (
        "Locator.click: Timeout 30000ms exceeded. "
        "subtree intercepts pointer events"
    )
    out = normalize_tool_error(raw, action="click_element")
    assert out["category"] == "click_blocked"
    assert "overlay" in out["error"].lower()
    assert "finish" in out["hint"].lower()


def test_user_failure_message_hides_technical_summary() -> None:
    msg = user_failure_message(
        objective="find price",
        summary="Locator.click: Timeout 30000ms exceeded",
        reason="error",
        items=[{"price": "RMB 17999"}],
    )
    assert "Locator" not in msg
    assert "RMB" in msg or "collected" in msg.lower()


def test_user_failure_message_uses_memory_last_error() -> None:
    msg = user_failure_message(
        objective="找到最贵的 iPhone",
        summary="",
        reason="error",
        memory_context={
            "last_tool_error": "Click failed: the target is covered by another element (overlay or sticky header).",
            "last_tool_error_category": "click_blocked",
        },
    )
    assert "遮挡" in msg or "cover" in msg.lower()


def test_user_failure_message_free_text_reason() -> None:
    msg = user_failure_message(
        objective="test",
        summary="",
        reason="no progress over 7 steps: repeated click_element",
    )
    assert "no progress" in msg.lower()


def test_is_reason_code() -> None:
    assert is_reason_code("no_progress")
    assert not is_reason_code("no progress over 7 steps")
