from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.nodes import send_email
from app.nodes.send_email import SendEmailNotConfiguredError


def test_send_email_stub_raises():
    with pytest.raises(SendEmailNotConfiguredError, match="not yet configured"):
        asyncio.run(
            send_email.run(
                {
                    "smtp_credential": "x",
                    "to": ["a@b.com"],
                    "subject": "hi",
                    "body": "hello",
                },
                input_items=[],
                context={},
                workflow_id="wf1",
            )
        )
