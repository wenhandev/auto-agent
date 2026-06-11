from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

from cryptography.fernet import Fernet


logger = logging.getLogger(__name__)

_ENV_VAR = "AUTO_AGENT_SECRET_KEY"
_KEY_FILE = Path(__file__).resolve().parents[2] / ".secret_key"
_KEY_README = _KEY_FILE.parent / ".secret_key.README"

_README_TEXT = (
    "auto-agent master key\n"
    "=====================\n"
    "The sibling file '.secret_key' contains the Fernet master key used to "
    "encrypt every credential and LLM API key stored in auto_agent.db.\n\n"
    "If you lose this file every encrypted blob in the database becomes "
    "unreadable. Back it up alongside any database dump.\n\n"
    "To override the on-disk key set the environment variable "
    "AUTO_AGENT_SECRET_KEY to a Fernet-compatible base64-encoded 32-byte "
    "value before starting the backend.\n"
)

_fernet: Fernet | None = None


def _write_readme() -> None:
    try:
        if not _KEY_README.exists():
            _KEY_README.write_text(_README_TEXT, encoding="utf-8")
    except OSError as exc:
        logger.warning("could not write %s: %s", _KEY_README, exc)


def _restrict_perms(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as exc:
        logger.warning(
            "could not chmod %s to 0600 (expected on Windows): %s", path, exc
        )


def load_or_create_key() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    env_value = os.environ.get(_ENV_VAR)
    if env_value:
        _fernet = Fernet(env_value.encode("utf-8"))
        return _fernet

    if _KEY_FILE.exists():
        key_bytes = _KEY_FILE.read_bytes().strip()
        _fernet = Fernet(key_bytes)
        _write_readme()
        return _fernet

    key_bytes = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_bytes(key_bytes)
    _restrict_perms(_KEY_FILE)
    _write_readme()
    logger.warning(
        "generated fresh Fernet master key at %s; back it up", _KEY_FILE
    )
    _fernet = Fernet(key_bytes)
    return _fernet


def encrypt(plaintext: bytes) -> bytes:
    return load_or_create_key().encrypt(plaintext)


def decrypt(ciphertext: bytes) -> bytes:
    return load_or_create_key().decrypt(ciphertext)


__all__ = ["load_or_create_key", "encrypt", "decrypt"]
