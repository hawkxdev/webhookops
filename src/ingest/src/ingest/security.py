"""Проверка подписи HMAC."""

import hashlib
import hmac
import time

DIGEST = hashlib.sha256
DIGEST_BYTES = DIGEST().digest_size
MAX_TIMESTAMP_DIGITS = 20


def verify_signature(
    raw_body: bytes,
    *,
    signature: str,
    secret: str,
    timestamp: str,
    tolerance: int,
) -> bool:
    """Проверка подписи вебхука."""
    if not secret:
        return False
    if not (timestamp.isascii() and timestamp.isdigit()):
        return False
    if len(timestamp) > MAX_TIMESTAMP_DIGITS:
        return False
    if abs(time.time() - int(timestamp)) > tolerance:
        return False

    received = _decode_hex(signature, DIGEST_BYTES)
    if received is None:
        return False

    message = f'{timestamp}.'.encode() + raw_body
    expected = hmac.new(secret.encode(), message, DIGEST).digest()
    return hmac.compare_digest(expected, received)


def _decode_hex(value: str, size: int) -> bytes | None:
    """HEX в байты."""
    try:
        decoded = bytes.fromhex(value)
    except ValueError:
        return None
    return decoded if len(decoded) == size else None
