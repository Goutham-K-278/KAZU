"""Bundled provider presets and remote preset verification helpers.

Zero Qt imports. Presets define default URLs, preferred engine (embedded vs.
companion), allowed in-pane domains, login path hints, and target CSS widths.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from kazu.domain.models import EngineKind

DEFAULT_TARGET_CSS_WIDTH: int = 950


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    """Metadata and behavior rules for an AI provider or custom web app."""

    key: str
    name: str
    url: str
    pane_type: EngineKind = EngineKind.EMBEDDED
    login_hints: tuple[str, ...] = ("/login",)
    google_login: bool = False
    allowed_domains: tuple[str, ...] = ()
    target_css_width: int = DEFAULT_TARGET_CSS_WIDTH
    quirks: tuple[str, ...] = ()
    disabled: bool = False
    badge_hint: str = ""


BUNDLED_PROVIDERS: dict[str, ProviderPreset] = {
    "claude": ProviderPreset(
        key="claude",
        name="Claude",
        url="https://claude.ai",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/login", "/signin"),
        google_login=True,
        allowed_domains=("claude.ai", "anthropic.com", "accounts.google.com"),
        target_css_width=950,
        quirks=(),
        badge_hint="Email or magic-link recommended",
    ),
    "chatgpt": ProviderPreset(
        key="chatgpt",
        name="ChatGPT",
        url="https://chatgpt.com",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/auth", "/login"),
        google_login=True,
        allowed_domains=(
            "chatgpt.com",
            "openai.com",
            "auth.openai.com",
            "auth0.openai.com",
            "accounts.google.com",
        ),
        target_css_width=950,
        quirks=("uses_ctrl_k",),
        badge_hint="Email login recommended",
    ),
    "gemini": ProviderPreset(
        key="gemini",
        name="Gemini",
        url="https://gemini.google.com",
        pane_type=EngineKind.COMPANION,
        login_hints=("accounts.google.com",),
        google_login=True,
        allowed_domains=("gemini.google.com", "google.com", "accounts.google.com"),
        target_css_width=950,
        quirks=("google_only",),
        badge_hint="Opens in Companion Mode",
    ),
    "perplexity": ProviderPreset(
        key="perplexity",
        name="Perplexity",
        url="https://www.perplexity.ai",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/login", "/signin"),
        google_login=True,
        allowed_domains=("perplexity.ai", "accounts.google.com"),
        target_css_width=950,
        quirks=(),
    ),
    "grok": ProviderPreset(
        key="grok",
        name="Grok",
        url="https://grok.com",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/sign-in", "/login"),
        google_login=True,
        allowed_domains=("grok.com", "x.ai", "x.com", "accounts.google.com"),
        target_css_width=950,
        quirks=(),
    ),
    "deepseek": ProviderPreset(
        key="deepseek",
        name="DeepSeek",
        url="https://chat.deepseek.com",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/sign_in", "/login"),
        google_login=True,
        allowed_domains=("deepseek.com", "accounts.google.com"),
        target_css_width=950,
        quirks=(),
    ),
    "mistral": ProviderPreset(
        key="mistral",
        name="Le Chat (Mistral)",
        url="https://chat.mistral.ai",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/login", "/auth"),
        google_login=True,
        allowed_domains=("mistral.ai", "accounts.google.com"),
        target_css_width=950,
        quirks=(),
    ),
    "copilot": ProviderPreset(
        key="copilot",
        name="Copilot",
        url="https://copilot.microsoft.com",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/login", "login.microsoftonline.com"),
        google_login=False,
        allowed_domains=("copilot.microsoft.com", "microsoft.com", "live.com"),
        target_css_width=950,
        quirks=(),
    ),
    "custom": ProviderPreset(
        key="custom",
        name="Custom URL",
        url="https://",
        pane_type=EngineKind.EMBEDDED,
        login_hints=("/login", "/signin", "/auth"),
        google_login=False,
        allowed_domains=(),
        target_css_width=950,
        quirks=(),
    ),
}


@dataclass(slots=True)
class ProviderPresetRegistry:
    """Runtime registry of bundled presets with optional signed remote overrides."""

    presets: dict[str, ProviderPreset] = field(
        default_factory=lambda: dict(BUNDLED_PROVIDERS)
    )

    def get(self, key: str) -> ProviderPreset:
        """Return the matching provider preset, falling back to 'custom'."""
        normalized = key.strip().lower()
        return self.presets.get(normalized, self.presets["custom"])

    def list_enabled(self) -> list[ProviderPreset]:
        """Return all non-disabled presets in display order."""
        return [preset for preset in self.presets.values() if not preset.disabled]

    def apply_verified_json(self, raw_json: str) -> int:
        """Merge a verified remote presets JSON payload into the registry.

        Returns the number of presets added or updated. Ignores malformed entries
        rather than crashing the application.
        """
        try:
            payload: Any = json.loads(raw_json)
        except json.JSONDecodeError:
            return 0

        if not isinstance(payload, dict):
            return 0

        entries = payload.get("providers")
        if not isinstance(entries, dict):
            return 0

        updated = 0
        for key, item in entries.items():
            if not isinstance(key, str) or not isinstance(item, dict):
                continue
            preset = _parse_preset_dict(key, item)
            if preset is not None:
                self.presets[preset.key] = preset
                updated += 1
        return updated


def _parse_preset_dict(key: str, data: dict[str, Any]) -> ProviderPreset | None:
    """Validate and build a ProviderPreset from untrusted JSON data."""
    name = data.get("name")
    url = data.get("url")
    if not isinstance(name, str) or not isinstance(url, str):
        return None
    if not (url.startswith("https://") or url.startswith("http://")):
        return None

    raw_engine = str(data.get("pane_type", EngineKind.EMBEDDED.value))
    try:
        pane_type = EngineKind(raw_engine)
    except ValueError:
        pane_type = EngineKind.EMBEDDED

    raw_width = data.get("target_css_width", DEFAULT_TARGET_CSS_WIDTH)
    is_numeric = isinstance(raw_width, (int, float))
    target_width = int(raw_width) if is_numeric else DEFAULT_TARGET_CSS_WIDTH
    target_width = max(500, min(1600, target_width))

    return ProviderPreset(
        key=key.strip().lower(),
        name=name.strip(),
        url=url.strip(),
        pane_type=pane_type,
        login_hints=tuple(str(h) for h in data.get("login_hints", ("/login",))),
        google_login=bool(data.get("google_login", False)),
        allowed_domains=tuple(str(d).lower() for d in data.get("allowed_domains", ())),
        target_css_width=target_width,
        quirks=tuple(str(q) for q in data.get("quirks", ())),
        disabled=bool(data.get("disabled", False)),
        badge_hint=str(data.get("badge_hint", "")),
    )
