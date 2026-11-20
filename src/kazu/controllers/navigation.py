"""Navigation policy, Google BlockDetector, signed-out hint, and safe DownloadService."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from kazu.domain.providers import ProviderPreset

GOOGLE_BLOCK_MARKERS: tuple[str, ...] = (
    "disallowed_useragent",
    "browser or app may not be secure",
    "couldn't sign you in",
)


class NavigationAction(StrEnum):
    """Decision for a navigation request inside an embedded pane."""

    ALLOW_IN_PANE = "allow_in_pane"
    OPEN_EXTERNAL = "open_external"
    BLOCK_UNSAFE = "block_unsafe"


class NavigationPolicy:
    """Decides whether a URL stays inside the pane or opens in the system browser."""

    def decide(
        self,
        url: str,
        preset: ProviderPreset,
        home_url: str,
        *,
        ctrl_clicked: bool = False,
    ) -> NavigationAction:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("https", "http"):
            return NavigationAction.BLOCK_UNSAFE
        if ctrl_clicked:
            return NavigationAction.OPEN_EXTERNAL

        host = (parsed.hostname or "").lower()
        if not host:
            return NavigationAction.BLOCK_UNSAFE

        allowed = set(preset.allowed_domains)
        home_host = (urlparse(home_url).hostname or "").lower()
        if home_host:
            allowed.add(home_host)

        for domain in allowed:
            if host == domain or host.endswith(f".{domain}"):
                return NavigationAction.ALLOW_IN_PANE
        return NavigationAction.OPEN_EXTERNAL


class BlockDetector:
    """Detects Google embedded-webview sign-in blocks (Problem A1)."""

    def is_google_blocked(self, url: str, page_title: str = "") -> bool:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        lowered_url = url.lower()
        lowered_title = page_title.lower()

        if "disallowed_useragent" in lowered_url:
            return True
        if host == "accounts.google.com" or host.endswith(".google.com"):
            return any(marker in lowered_title for marker in GOOGLE_BLOCK_MARKERS)
        return False

    def is_signed_out_url(self, url: str, preset: ProviderPreset) -> bool:
        """Non-invasive amber-dot hint based purely on URL path patterns (no scraping)."""
        lowered = url.lower()
        return any(hint.lower() in lowered for hint in preset.login_hints)


class DownloadService:
    """Auto-numbers download destinations so files never silently overwrite (Bug #10)."""

    def resolve_unique_path(self, target_dir: Path, filename: str) -> Path:
        """Return a collision-free path inside `target_dir`, blocking traversal."""
        safe_name = Path(filename).name.strip() or "download"
        target_dir.mkdir(parents=True, exist_ok=True)
        base_resolved = target_dir.resolve()

        candidate = (base_resolved / safe_name).resolve()
        if not candidate.is_relative_to(base_resolved):
            raise ValueError("Invalid download filename")

        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while True:
            numbered = (base_resolved / f"{stem} ({counter}){suffix}").resolve()
            if not numbered.exists():
                return numbered
            counter += 1
