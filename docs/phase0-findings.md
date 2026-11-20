# Phase 0 Verification Findings (T1–T14)

Record real-hardware test results from `scripts/phase0_spike.py` before locking provider defaults.

## Hardware & Environment
- **OS / Version:** _(fill in)_
- **RAM:** _(fill in)_
- **Python / PySide6 / PySide6-WebEngine versions:** _(fill in)_
- **Installed Companion browsers detected:** _(Chrome / Edge / Brave)_

## Test Results

| # | Test | Pass Condition | Status | Notes / Measurements |
|---|---|---|---|---|
| T1 | Streaming reply finishes while Space is hidden (`Hidden-Active`) | Completes cleanly, background CPU low | ☐ | |
| T2 | Atomic `QWebEngineProfileBuilder` + email login survives quit & `kill -9` | Both isolated accounts remain signed in | ☐ | |
| T3 | Google sign-in in embedded pane triggers `BlockDetector` | Card shows working Email + Companion buttons | ☐ | |
| T4 | Cloudflare check on `chatgpt.com` (default UA + Client Hints) | Passes without verification loop | ☐ | |
| T5 | On-disk cookie storage format & owner-only folder permissions | `0700` / user ACL confirmed | ☐ | |
| T6 | `SendService` paste preserves original user clipboard | Prompt lands; clipboard restored | ☐ | |
| T7 | `AutoFitZoom` at 500 / 600 / 800 px pane widths | Desktop UI intact at >= 0.67 zoom | ☐ | |
| T8 | Hardware FIDO2 key flow via `WebAuthnDialog` | PIN + touch succeed natively | ☐ | |
| T9 | Vetted MV3 password manager via `QWebEngineExtensionManager` | Unlock popup + autofill work per profile | ☐ | |
| T10 | Ubuntu 24.04 Flatpak + `.deb` with AppArmor profile | Launches with full Chromium sandbox | ☐ | |
| T11 | Recursive `psutil` RAM test on 8 GB laptop (2 & 4 panes + discard) | Usable; discard frees renderer RAM | ☐ | |
| T12 | Platform passkeys (Touch ID / Windows Hello) in Qt WebEngine | Works natively or clean Companion offer | ☐ | |
| T13 | Companion Mode (`--app` + `--user-data-dir`) for 2 Gemini accounts | Isolated, signed in, tiled on Win/Mac | ☐ | |
| T14 | UX Polish Audit (no dark white flash, 60 FPS splitter, focus, monitor clamp) | All four pass smoothly | ☐ | |

## Provider Go / No-Go Decision Matrix

| Provider | Decision (`Embedded` / `Email-Only` / `Companion`) | Measured `target_css_width` | Notes |
|---|---|---|---|
| Claude | | 950 | |
| ChatGPT | | 950 | |
| Gemini | Companion (default) | 950 | |
| Perplexity | | 950 | |
| Custom URL | Embedded | 950 | |
