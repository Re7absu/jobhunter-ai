"""Symmetric encryption for data at rest (CV files, Gmail OAuth tokens)."""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet

from app.core.config import settings

log = logging.getLogger(__name__)


def _fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        if settings.APP_ENV == "production":
            raise RuntimeError("ENCRYPTION_KEY must be set in production")
        # Development fallback: deterministic key derived from SECRET_KEY.
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_bytes(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def encrypt_str(value: str) -> str:
    return encrypt_bytes(value.encode()).decode()


def decrypt_str(value: str) -> str:
    return decrypt_bytes(value.encode()).decode()
