"""Signed remote preset verification, engine-age checks, and privacy-safe reports."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import date

ENGINE_STALE_DAYS: int = 60


@dataclass(frozen=True, slots=True)
class BrokenSiteReport:
    """Privacy-safe diagnostic payload (strictly OS + engine + provider key)."""

    os_name: str
    os_release: str
    engine_version: str
    provider_key: str


def is_engine_stale(engine_release_date: date, today: date | None = None) -> bool:
    """Return True if the bundled Chromium/WebEngine is older than 60 days."""
    reference = today if today is not None else date.today()
    return (reference - engine_release_date).days > ENGINE_STALE_DAYS


def build_broken_site_report(provider_key: str, engine_version: str) -> BrokenSiteReport:
    """Create a minimal privacy-safe report payload with zero user data or URLs."""
    return BrokenSiteReport(
        os_name=platform.system(),
        os_release=platform.release(),
        engine_version=engine_version.strip() or "unknown",
        provider_key=provider_key.strip().lower() or "custom",
    )


def verify_ed25519_signature(
    payload_bytes: bytes,
    signature_bytes: bytes,
    public_key_bytes: bytes,
) -> bool:
    """Verify an Ed25519 signature for remote providers.json updates.

    Returns False if the signature is invalid or if the optional cryptography
    package is not installed (fail-closed).
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False

    try:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        public_key.verify(signature_bytes, payload_bytes)
        return True
    except (InvalidSignature, ValueError):
        return False
