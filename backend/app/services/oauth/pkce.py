from __future__ import annotations

import base64
import hashlib
import secrets


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(48)


def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def generate_state_token() -> str:
    return secrets.token_urlsafe(32)
