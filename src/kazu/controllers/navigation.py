"""Navigation policy, Google BlockDetector, signed-out hint, and safe DownloadService."""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from kazu.domain.providers import ProviderPreset

GOOGLE_BLOCK_MARKERS: tuple[str, ...] = (
    "disallowed_useragent",
    "browser or app may not be secure",
    "couldn't sign you in",
    "error 400",
    "bad request",
    "malformed",
)

# OAuth / SSO identity-provider and auth-broker domains that must stay in-pane
# so session/PKCE cookies remain bound to this profile across the callback.
OAUTH_PASSTHROUGH_DOMAINS: tuple[str, ...] = (
    "accounts.google.com",
    "oauth2.googleapis.com",
    "accounts.youtube.com",
    "myaccount.google.com",
    "login.microsoftonline.com",
    "login.live.com",
    "appleid.apple.com",
    "auth0.com",
    "okta.com",
    "supabase.co",
    "firebaseapp.com",
    "clerk.accounts.dev",
    "clerk.com",
    "amazoncognito.com",
    "workos.com",
    "stytch.com",
    "kinde.com",
    "descope.com",
)

# Dual-purpose hosts: only treat as OAuth when the path starts with one of
# these prefixes (e.g. github.com/login/oauth but NOT github.com/openai).
OAUTH_PATH_PREFIXES: dict[str, tuple[str, ...]] = {
    "github.com": ("/login/oauth", "/login/device", "/sessions"),
    "gitlab.com": ("/oauth",),
}

# Common two-part public suffixes so sibling subdomains match properly.
_TWO_PART_TLDS: frozenset[str] = frozenset(
    {
        "co.uk",
        "org.uk",
        "ac.uk",
        "com.au",
        "net.au",
        "co.in",
        "co.jp",
        "com.br",
        "com.sg",
        "co.nz",
        "co.za",
    }
)


def extract_registrable_domain(host: str) -> str:
    """Return the registrable base domain for `host` (e.g. `app.pomaroo.ai` -> `pomaroo.ai`).

    Leaves `localhost`, single-label hosts, and IP addresses unchanged.
    """
    cleaned = host.strip().lower().rstrip(".")
    if not cleaned or cleaned == "localhost" or "." not in cleaned:
        return cleaned
    try:
        ipaddress.ip_address(cleaned)
        return cleaned
    except ValueError:
        pass

    parts = cleaned.split(".")
    if len(parts) <= 2:
        return cleaned
    last_two = ".".join(parts[-2:])
    if last_two in _TWO_PART_TLDS and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def is_oauth_url(url: str) -> bool:
    """Return True if `url` belongs to a known OAuth / SSO identity provider."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False

    for auth_domain in OAUTH_PASSTHROUGH_DOMAINS:
        if host == auth_domain or host.endswith(f".{auth_domain}"):
            return True

    path = parsed.path.lower()
    for dual_host, prefixes in OAUTH_PATH_PREFIXES.items():
        if (host == dual_host or host.endswith(f".{dual_host}")) and any(
            path.startswith(p) for p in prefixes
        ):
            return True
    return False


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
        is_user_link_click: bool = True,
    ) -> NavigationAction:
        if url.strip().lower() == "about:blank":
            return NavigationAction.ALLOW_IN_PANE

        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("https", "http"):
            return NavigationAction.BLOCK_UNSAFE
        if ctrl_clicked:
            return NavigationAction.OPEN_EXTERNAL

        host = (parsed.hostname or "").lower()
        if not host:
            return NavigationAction.BLOCK_UNSAFE

        # Server redirects, form submissions, and JS-driven OAuth handshakes
        # must stay in-pane so session/PKCE cookies are never split across browsers.
        if not is_user_link_click:
            return NavigationAction.ALLOW_IN_PANE

        # OAuth / SSO round-trips stay in-pane even on explicit link clicks.
        if is_oauth_url(url):
            return NavigationAction.ALLOW_IN_PANE

        allowed = set(preset.allowed_domains)
        home_host = (urlparse(home_url).hostname or "").lower()
        if home_host:
            allowed.add(home_host)
            # Also allow sibling subdomains of custom URLs (e.g. app.site.com <-> auth.site.com).
            allowed.add(extract_registrable_domain(home_host))

        for domain in allowed:
            if host == domain or host.endswith(f".{domain}"):
                return NavigationAction.ALLOW_IN_PANE
        return NavigationAction.OPEN_EXTERNAL


class BlockDetector:
    """Detects Google embedded-webview sign-in blocks and 400 errors (Problem A1)."""

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
