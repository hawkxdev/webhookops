"""Тесты проверки подписи."""

import hashlib
import hmac
import time

import pytest

from ingest.security import verify_signature

SECRET = 'test-secret'
OTHER_SECRET = 'other-secret'
NO_SECRET = ''
BODY = b'{"order": 1}'
TAMPERED_BODY = b'{"order": 2}'
TOLERANCE = 300
ARABIC_DIGITS = str.maketrans('0123456789', '٠١٢٣٤٥٦٧٨٩')


def _valid_signature(
    timestamp: str, raw_body: bytes = BODY, secret: str = SECRET
) -> str:
    """Подпись легитимного отправителя."""
    message = f'{timestamp}.'.encode() + raw_body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def test_valid_signature_returns_true() -> None:
    timestamp = str(int(time.time()))
    signature = _valid_signature(timestamp)
    assert verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


def test_huge_timestamp_does_not_raise() -> None:
    timestamp = '1' * 5000
    signature = _valid_signature(timestamp)
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


def test_expired_timestamp_returns_false() -> None:
    timestamp = str(int(time.time()) - TOLERANCE - 1)
    signature = _valid_signature(timestamp)
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


@pytest.mark.parametrize(
    'timestamp',
    ['abc', '12.5', ''],
    ids=['garbage', 'fractional', 'empty'],
)
def test_malformed_timestamp_returns_false(timestamp: str) -> None:
    signature = _valid_signature(timestamp)
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


def test_non_ascii_digits_timestamp_returns_false() -> None:
    timestamp = str(int(time.time())).translate(ARABIC_DIGITS)
    signature = _valid_signature(timestamp)
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


@pytest.mark.parametrize(
    'signature',
    ['', 'ab', 'abc', 'e' * 63 + 'é', 'zz' * 32],
    ids=['empty', 'too_short', 'odd_length', 'non_ascii', 'not_hex'],
)
def test_malformed_signature_returns_false(signature: str) -> None:
    timestamp = str(int(time.time()))
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


def test_empty_secret_returns_false() -> None:
    timestamp = str(int(time.time()))
    signature = _valid_signature(timestamp, secret=NO_SECRET)
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=NO_SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


def test_wrong_secret_returns_false() -> None:
    timestamp = str(int(time.time()))
    signature = _valid_signature(timestamp, secret=OTHER_SECRET)
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )


def test_tampered_body_returns_false() -> None:
    timestamp = str(int(time.time()))
    signature = _valid_signature(timestamp, raw_body=TAMPERED_BODY)
    assert not verify_signature(
        BODY,
        signature=signature,
        secret=SECRET,
        timestamp=timestamp,
        tolerance=TOLERANCE,
    )
