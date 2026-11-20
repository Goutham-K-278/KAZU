<p align="center">
  <img src="src/kazu/assets/kazu_logo.png" alt="Kazu" width="140" />
</p>

<h1 align="center">Kazu</h1>

<p align="center">
  <strong>All your AI chats. One calm window.</strong><br/>
  Run Claude, ChatGPT, Gemini, Perplexity and more, side by side, each in its own private session.
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

You've been using AI as a free user, you type a prompt, the token limit hits, so you switch to another account and start over. Same loop, over and over, never actually finishing the work.

**I built Kazu to fix that.**

Kazu is a desktop interface where you open multiple panes, one per account, one per AI, all in a single window. Split your task equally across each pane, work them all at once, and finish in a fraction of the time. No more tab-switching. No more losing context. No more worrying about token limits.

> **Your passwords are always safe.** You sign in directly on each AI's website, exactly as you would in a normal browser. Kazu never sees your credentials. Ever.

---

## Download

Go to [**Releases →**](https://github.com/Goutham-K-278/KAZU/releases/latest) and grab the installer for your system.

| Platform | Installer | How to install |
|---|---|---|
| **Windows 10 / 11** | `Kazu-Setup-*-Windows-x64.exe` | Double-click. No admin rights needed. Appears in Start Menu and Desktop. |
| **macOS 12+** | `Kazu-*-macOS.dmg` | Open the `.dmg`, drag Kazu into Applications. Done. |
| **Ubuntu / Debian** | `kazu_*_amd64.deb` | `sudo apt install ./kazu_*_amd64.deb`, then find Kazu in your Applications menu. |

---

## Why Kazu?

### 🪟 One window for all your AI tools
- See Claude, ChatGPT, Gemini side by side, no more alt-tabbing
- Compare answers instantly across panes
- 1–4 pane layouts with draggable splitters

### 🔐 Every AI stays logged in, always
- Each pane has its own completely private session
- Multiple accounts in multiple panes, all at once
- Nothing leaks between panes. Ever.

### 🗂 Spaces, like virtual desktops for your AI work
- Group panes into named Spaces: "Research", "Coding", "Writing"
- Switch Spaces in one click
- Activity dots on tabs light up when a background reply comes in

### 🧠 Smart memory, uses RAM only when needed
- Background Spaces freeze → hibernate → unload automatically
- Streams always finish before anything hibernates
- "Waking up..." preview when you switch back
- Pin any pane to keep it always live

### ✨ Gemini & Google accounts, it just works
- Kazu detects when Google blocks an embedded browser
- Opens Gemini in **Companion Mode**: your real Chrome/Edge/Brave, bar-free, auto-tiled
- Zero manual workarounds

### ⌨️ Keyboard-first
| Shortcut | What it does |
|---|---|
| `Ctrl+K` | Command palette, jump anywhere, open any site |
| `Ctrl+Shift+T` | Undo a closed pane (5-second window) |
| `Ctrl+Shift+B` | Draft Composer, write once, send to all panes |
| `Ctrl+W` | Focus mode, maximise one pane |
| Pass-Through Mode | Let site shortcuts reach the site, not Kazu |

### 🛡 Quiet details that matter
- Crash / offline / sign-out shown **per pane**, so one broken site doesn't touch the rest
- File downloads with progress toasts and auto-numbered filenames
- Window auto-recovers if you unplug a monitor
- Real RAM usage, not the number your OS guesses
- Light, dark, and system themes with no white flash on startup

---

## Feature Overview

<details>
<summary><strong>Show full feature list</strong></summary>

**Panes & Layouts**
- 1–4 panes per Space with draggable splitters
- Auto-fit zoom so sites keep their desktop layout even in narrow panes
- Snapshot preview with "Waking up..." animation on pane reload

**Accounts & Sessions**
- Colour-coded accounts with auto-naming, rename, recolour
- "Sign out & wipe data", removes the session folder completely
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

## Supported AI Services

Kazu works with any website. Ships with ready-made presets for:

**Claude · ChatGPT · Gemini · Perplexity · DeepSeek · Mistral · Grok · Copilot**

And any custom URL, including Notion, GitHub, Ollama running locally, and your company's internal tools.

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

**Run the test suite**

```bash
uv run pytest
```

**Publish a release (maintainers)**

Push a version tag and GitHub Actions will build and attach the Windows `.exe`, macOS `.dmg`, and Linux `.deb` installers automatically:

```bash
git tag v0.1.0
git push origin v0.1.0
```

---

## License

MIT © Goutham K, see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with PySide6 · Chromium · Python 3.11+
</p>
