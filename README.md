<p align="center">
  <img src="src/kazu/assets/kazu_logo.png" alt="Kazu" width="140" />
</p>

<h1 align="center">Kazu</h1>

<p align="center">
  <strong>All your AI chats. One calm window.</strong><br/>
  Run Claude, ChatGPT, Gemini, Perplexity and more — side by side, each in its own private session.
</p>

<p align="center">
  <a href="https://github.com/Goutham-K-278/KAZU/releases/latest"><img src="https://img.shields.io/github/v/release/Goutham-K-278/KAZU?style=flat-square&color=7c6fcd&label=Download" alt="Download"></a>
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue?style=flat-square&logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/macOS-12%2B-lightgrey?style=flat-square&logo=apple" alt="macOS">
  <img src="https://img.shields.io/badge/Linux-deb%20%2F%20Flatpak-orange?style=flat-square&logo=linux" alt="Linux">
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT License">
</p>

---

## What is Kazu?

You probably have five AI tabs open right now. You switch between them. You lose context. You re-type the same thing in three different chat windows.

**Kazu fixes that.**

It's a desktop app that tiles your AI chats — Claude, ChatGPT, Gemini, Perplexity, DeepSeek, or any website — side by side in one window. Each chat lives in its own private bubble, stays logged in, and never touches another. You stay in flow.

> **Your passwords are always safe.** You sign in directly on each AI's website, exactly as you would in a normal browser. Kazu never sees your credentials — ever.

---

## Download

Go to [**Releases →**](https://github.com/Goutham-K-278/KAZU/releases/latest) and grab the installer for your system.

| Platform | Installer | How to install |
|---|---|---|
| **Windows 10 / 11** | `Kazu-Setup-*-Windows-x64.exe` | Double-click. No admin rights needed. Kazu appears in your Start Menu and Desktop. |
| **macOS 12+** | `Kazu-*-macOS.dmg` | Open the `.dmg` and drag Kazu into your Applications folder. |
| **Ubuntu / Debian** | `kazu_*_amd64.deb` | `sudo apt install ./kazu_*_amd64.deb` — Kazu appears in your Applications menu. |

---

## Why Kazu?

### One window for all your AI tools
Stop alt-tabbing between six browser tabs. See Claude and ChatGPT side by side, compare their answers instantly, and copy the best one.

### Every AI stays logged in — always
Each pane has its own private session. Claude is logged into your work account, ChatGPT into your personal one, Gemini into your Google account — all at the same time, never interfering with each other.

### Spaces — like virtual desktops for your AI work
Group your panes into **Spaces**: a "Research" space with four panes, a "Coding" space with two, a "Writing" space with one. Switch between them in one click. Activity dots light up on the tab so you always know when a reply comes in — even in a background Space.

### Smart memory — Kazu only uses RAM when it needs to
Background Spaces quietly freeze, then hibernate, then fully unload from memory — but only after your current AI replies finish streaming. When you switch back, panes wake up with a smooth "Waking up…" preview. Pin any pane to keep it always live.

### Gemini and Google accounts — it just works
Google blocks embedded browsers. Kazu detects this and opens Gemini in **Companion Mode**: your real Chrome, Edge, or Brave browser in a clean, bar-free window that auto-tiles with everything else. No workarounds needed.

### Keyboard-first, focus-friendly
- **`Ctrl+K`** — Command palette: jump anywhere, open any site, change any setting
- **`Ctrl+Shift+T`** — Undo a closed pane (for 5 seconds, like a browser tab)
- **`Ctrl+Shift+B`** — Draft Composer: write once, send to all panes at once
- **Focus Mode** — maximise one pane to full window, one keystroke away
- **Pass-Through Mode** — stop Kazu from capturing shortcuts so the site's own hotkeys work

### Downloads, themes, crash recovery — the quiet details
Kazu handles file downloads with progress toasts and auto-numbered filenames. It recovers your window if you unplug a monitor. It shows real RAM usage, not just the number your OS sees. Crash, offline, and sign-out states are shown per-pane — one broken site doesn't affect the rest.

---

## Feature Overview

<details>
<summary><strong>Show full feature list</strong></summary>

**Panes & Layouts**
- 1–4 panes per Space with draggable splitters
- Auto-fit zoom so sites keep their desktop layout even in narrow panes
- Snapshot preview with "Waking up…" animation on pane reload

**Accounts & Sessions**
- Colour-coded accounts with auto-naming, rename, recolour
- "Sign out & wipe data" — removes the session folder completely
- Companion Mode for Gemini and any Google-only account
- Google-block detection with "Use email login" or "Switch to Companion" prompt
- OAuth popups at a proper size with domain lock
- Native FIDO2 / security-key dialog

**Spaces & Navigation**
- Multiple Spaces (virtual desktops) with instant switching
- Activity dots on Space tabs when a background reply updates
- One-click Space deletion with undo

**Memory & Lifecycle**
- 4-tier lifecycle: Live → Hidden-Active → Frozen → Discarded
- Streams finish before a Space hibernates
- "Keep Running" pin per pane

**Productivity**
- Command palette (`Ctrl/Cmd+K`) with rebindable shortcuts
- Clipboard-safe Send Selection, Paste to All, and Draft Composer
- Focus mode to maximise one pane
- Undo for accidentally closed pane (`Ctrl+Shift+T`)

**Reliability**
- Crash, offline, and signed-out recovery cards (per pane, not global)
- File downloads with progress toasts and auto-numbered filenames
- Window recovery after an unplugged monitor
- Truthful RAM diagnostics (recursive process tree)

**Customisation & Sync**
- Light, dark, and system themes with no white flash on startup
- Signed remote provider presets with a "Report a broken site" button
- Layout export/import and sync via your own Dropbox/Drive folder (never your sessions)
- Custom URLs for any web app: Notion, GitHub, Ollama, and more

**Updates & Packaging**
- Delta auto-updates with signed installers
- Flatpak and `.deb` packaging for Linux

**Coming in v1.x**
- Space templates, detachable windows, system tray with global hotkey
- MV3 password-manager browser extension

</details>

---

## Install from Source

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
# 1. Clone
git clone https://github.com/Goutham-K-278/KAZU.git
cd KAZU/kazu

# 2. Install dependencies
uv sync --extra dev

# 3. Register Kazu in your Start Menu / Applications menu
uv run python scripts/install_desktop_entry.py

# 4. Launch
uv run kazu
```

### Run the test suite

```bash
uv run pytest
```

### Publish a release (maintainers)

Push a version tag — GitHub Actions builds and attaches the Windows `.exe`, macOS `.dmg`, and Linux `.deb` installers automatically:

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## Supported AI Services

Kazu works with any website. It ships with ready-made presets for:

**Claude · ChatGPT · Gemini · Perplexity · DeepSeek · Mistral · Grok · Copilot**

And any custom URL — Notion, GitHub, Ollama running locally, your company's internal tools.

---

## License

MIT © Goutham K — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with PySide6 · Chromium · Python 3.11+
</p>
