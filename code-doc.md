# Kazu — Code Documentation

> Living documentation. Updated every time code changes.
> Read this to understand how the entire project works without
> reading a single line of source code.

---

## Project Overview

**Kazu** is a calm desktop application that lets you place several AI chat websites — such as Claude, ChatGPT, Gemini, Perplexity, or any custom website — side by side in separate, private sessions grouped into switchable workspaces called **Spaces**. Your passwords never touch Kazu: each pane opens the real website in its own private folder on your computer, or opens your real Chrome/Edge/Brave browser in a clean bar-free window ("Companion Mode") when a site like Gemini requires Google Sign-In. To run Kazu, install Python 3.12 and `uv`, run `uv sync --extra dev`, and start the app with `uv run kazu` (or run `uv run python scripts/phase0_spike.py` first to test on your hardware).

---

## Architecture at a Glance

```
┌────────────────────────────────────────────────────────────────────┐
│  1. WINDOW & SCREENS (src/kazu/ui/)                                │
│     Top bar of Space tabs  •  Split panes  •  Command Palette      │
│     Draft Composer  •  Settings  •  Recovery cards  •  Toasts      │
│                                                                    │
│     Two ways to show a website inside a pane:                      │
│       ├── Embedded Browser (ui/engine_qt.py)  → Claude, ChatGPT    │
│       └── Real Browser Companion (ui/engine_companion.py) → Gemini │
└───────────────────────────────┬────────────────────────────────────┘
                                ↓
┌────────────────────────────────────────────────────────────────────┐
│  2. CONTROLLERS — THE COORDINATORS (src/kazu/controllers/)         │
│     Decide what happens when you click, type, switch Space,        │
│     close a pane, paste to all panes, or leave a Space idle.       │
└───────────────────────────────┬────────────────────────────────────┘
                                ↓
┌───────────────────────────────┴────────────────────────────────────┐
│  3. PURE RULES (src/kazu/domain/)    │  4. STORAGE & SAFETY        │
│     What an Account, Space,          │     (src/kazu/infra/)       │
│     Layout, and Preset look like.    │     SQLite database,        │
│     (Zero screen/window code here!)  │     private folders, RAM,   │
│                                      │     safe shutdown & locks.  │
└──────────────────────────────────────┴─────────────────────────────┘
```

### How Your Saved Data Looks in the Database (`app.db`)

```
┌──────────────────────────────────────────────────────────────────────┐
│ accounts                                                             │
├────────┬─────────────┬──────────────┬───────────┬───────┬────────────┤
│ id     │ label       │ provider_key │ engine    │ color │ keep_alive │
├────────┼─────────────┼──────────────┼───────────┼───────┼────────────┤
│ a1-... │ Work Claude │ claude       │ embedded  │ cobalt│ 0          │
│ b2-... │ Work Gemini │ gemini       │ companion │ teal  │ 1          │
└────────┴─────────────┴──────────────┴───────────┴───────┴────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│ spaces                                                               │
├────────┬─────────────┬─────────────┬─────────────────────────────────┤
│ id     │ name        │ order_index │ layout_json                     │
├────────┼─────────────┼─────────────┼─────────────────────────────────┤
│ s1-... │ Research    │ 0           │ {"v":1,"root":{"type":"split".. │
│ s2-... │ Coding      │ 1           │ {"v":1,"root":{"type":"pane"... │
└────────┴─────────────┴─────────────┴─────────────────────────────────┘
```

---

## File-by-File Documentation

### `pyproject.toml`
**Last updated**: 2026-11-20 13:05
**Purpose**: Lists the software Kazu needs to run and sets automatic quality rules.
**Connects to**: Used by `uv`, `pytest`, `pyright`, and `ruff` across the whole project.

**How it works**:
1. Declares the required packages (`PySide6-Essentials`, `PySide6-WebEngine`, `platformdirs`, `psutil`).
2. Sets a strict rule in `ruff` so **only** `src/kazu/ui/engine_qt.py` is allowed to touch the built-in browser engine — keeping the rest of the app free from lock-in.

---

### `src/kazu/domain/models.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Defines the plain building blocks of Kazu: an `Account`, a `Space`, and `AppSettings`.
**Connects to**: Imported by `domain/layout.py`, `domain/providers.py`, `infra/db.py`, `controllers/*`, and `ui/*`. Never imports any window or browser code.

**How it works**:
```
New Account created
    ↓
Cleans up blank spaces in its name
    ↓
Checks its dot color against 8 color-blind-safe colors
    ├── Valid color → keeps it
    └── Unknown color → falls back to Cobalt blue
    ↓
Keeps zoom level safely between 50% and 200%
```

---

### `src/kazu/domain/providers.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Holds the built-in list of AI websites (Claude, ChatGPT, Gemini, Perplexity, Grok, DeepSeek, Mistral, Copilot, Custom URL) and safely merges signed updates.
**Connects to**: Uses `domain/models.py`; used by `controllers/accounts.py`, `controllers/navigation.py`, and `ui/account_picker.py`.

**How it works**:
```
App asks for rules for a provider (for example, "gemini")
    ↓
Looks up "gemini" in the preset table
    ├── Found → returns its URL, allowed domains, zoom width, and Companion preference
    └── Not found → returns safe "custom" defaults
```
When a verified remote update file arrives, it goes through each entry one by one, checks that the address starts with `http://` or `https://`, and skips anything malformed so bad data can never crash the app.

---

### `src/kazu/domain/layout.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Manages how panes are split horizontally or vertically inside a Space and converts that layout to/from text for saving.
**Connects to**: Uses `domain/models.py`; used by `controllers/spaces.py` and `ui/space_stack.py`.

**How it works**:
```
Saved layout text loaded from database
    ↓
Reads the text and rebuilds the tree of splits and panes
    ├── Valid layout → returns the exact splits and pane sizes
    └── Corrupted or unreadable text → falls back to one clean empty pane (never crashes)
```
Also provides clean actions: `split_pane` (splits one rectangle into two), `close_pane` (removes one pane and tidies up leftover dividers), `swap_panes` (swaps two accounts), and `recommended_max_panes` (suggests 2, 3, or 4 panes based on screen width).

---

### `src/kazu/infra/paths.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Chooses the right private folders on Windows, macOS, and Linux and locks them so only the current user can read them.
**Connects to**: Used by `app.py`, `controllers/accounts.py`, `ui/engine_qt.py`, and `ui/engine_companion.py`.

**How it works**:
```
App asks for an account's private storage folder
    ↓
Checks the account ID contains only safe letters, numbers, dashes, or underscores
    ├── Unsafe characters (like "..") → stops immediately with an error
    └── Safe ID → builds the folder path inside Kazu's data directory
         ↓
    Double-checks the final path stays inside Kazu's folder
         ↓
    Creates the folder with owner-only permissions (0700)
```

---

### `src/kazu/infra/logging_setup.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Writes diagnostic logs to a rotating file while automatically erasing any web addresses so your browsing stays private.
**Connects to**: Configured at startup in `app.py`.

**How it works**:
```
A module writes a log message
    ↓
PrivacyRedactingFilter scans the text for "http://" or "https://"
    ├── Found → replaces the web address with "[redacted-url]"
    └── Not found → leaves the message alone
    ↓
Writes to kazu.log (automatically rotates at 2 MB, keeping 3 backups)
```

---

### `src/kazu/infra/db.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Saves and loads all Accounts, Spaces, and Settings in a local SQLite database with safe versioned upgrades.
**Connects to**: Uses `domain/models.py`; used by `controllers/accounts.py`, `controllers/spaces.py`, and `app.py`.

**How it works**:
```
Database opens app.db
    ↓
Checks PRAGMA user_version (the database's version number)
    ├── Older than latest → runs each missing upgrade step inside a safe transaction
    └── Already current → ready immediately
```
Every query uses bound parameters (`?`) rather than gluing text together, preventing SQL injection. On exit, `checkpoint()` flushes pending changes cleanly to disk.

---

### `src/kazu/infra/memory.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Measures the real memory used by Kazu — adding up the main Python app plus every background browser helper process.
**Connects to**: Used by `ui/settings_page.py`, `ui/main_window.py`, and `scripts/phase0_spike.py`.

**How it works**:
```
Settings or Diagnostics asks for current RAM usage
    ↓
Finds the main Kazu process
    ↓
Goes through every child browser process, one by one, adding its memory
    ↓
Returns the truthful combined total in megabytes
```

---

### `src/kazu/infra/snapshots.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Keeps a small, size-capped collection of screenshots of paused panes so returning to a Space shows your last chat instead of a blank screen.
**Connects to**: Used by `ui/main_window.py`.

**How it works**:
Acts like a small stack of sticky notes (at most 24 screenshots, each under 4 MB). When a new screenshot arrives and the stack is full, the oldest unused screenshot is automatically discarded.

---

### `src/kazu/infra/shutdown.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Orchestrates app shutdown in an exact order so login cookies are always saved to disk before Kazu exits.
**Connects to**: Wired in `app.py` and `ui/main_window.py`.

**How it works**:
```
User quits Kazu
    ↓
1. Hide windows and save window position
    ↓
2. Close and delete all web views and pages
    ↓
3. Let Qt finish clearing deleted pages
    ↓
4. Close all browser profiles (flushes cookies to disk)
    ↓
5. Checkpoint SQLite database and release single-instance lock
```

---

### `src/kazu/infra/geometry.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Prevents Kazu from opening invisibly off-screen after you unplug an external monitor.
**Connects to**: Called by `ui/main_window.py` when restoring window size and position.

**How it works**:
```
Saved window coordinates loaded
    ↓
Compares saved rectangle against every currently connected screen
    ├── At least 25% visible on a screen → keeps it on that screen, nudging edges inside
    └── Off-screen (monitor unplugged) → centers the window cleanly on the main screen
```

---

### `src/kazu/infra/single_instance.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Makes sure only one copy of Kazu opens your browser profiles at once.
**Connects to**: Used by `app.py`.

**How it works**:
```
User double-clicks Kazu
    ↓
Checks if a Kazu window is already listening on the local socket
    ├── Already running → sends "FOCUS" message to bring it to the front, then exits quietly
    └── Not running → starts listening and launches normally
```

---

### `src/kazu/infra/updater.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Checks whether the browser engine is more than 60 days old, verifies cryptographic signatures on remote preset files, and builds privacy-safe broken-site reports.
**Connects to**: Standalone helper used for update checks and preset verification.

**How it works**:
- `verify_ed25519_signature`: Checks a cryptographic signature; if anything is invalid or missing, returns `False` (never trusts unsigned updates).
- `build_broken_site_report`: Packs only your operating system name, engine version, and provider key — never your chats, emails, or URLs.

---

### `src/kazu/controllers/accounts.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Creates, renames, recolors, switches engines for, and completely wipes user accounts.
**Connects to**: Uses `domain/*`, `infra/db.py`, `infra/paths.py`; called by `ui/main_window.py`.

**How it works**:
```
User adds a new Claude account
    ↓
Picks the least-used color-blind-safe dot color
    ↓
Assigns a friendly name ("Claude", then "Claude 2", etc.)
    ↓
Saves to SQLite and creates its owner-only private folder on disk
```
When deleting an account, it clears all Spaces pointing to it, removes the database row, and deletes the storage, cache, and Companion folders from disk.

---

### `src/kazu/controllers/spaces.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Manages Spaces, splits, 5-second Undo-close recovery, duplicate-account detection, and atomic Sync Folder layout exports.
**Connects to**: Uses `domain/layout.py`, `infra/db.py`; called by `ui/main_window.py`.

**How it works**:
```
User presses Ctrl+W to close a pane
    ↓
Saves a copy of the Space's layout onto the Undo stack
    ↓
Removes the pane and saves the updated layout
    ↓
If user clicks Undo (or presses Ctrl+Shift+T) → restores the exact previous layout
```
`write_sync_folder` writes only Space names, layouts, and account labels (never login cookies) to a temporary file, backs up the old file as `.bak`, and swaps the new file into place atomically.

---

### `src/kazu/controllers/lifecycle.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Runs the 4-tier memory-saving state machine (`Live → Hidden-Active → Frozen → Discarded`) with an Activity Guard so long AI replies never freeze mid-stream.
**Connects to**: Used by `ui/main_window.py` and `ui/engine_qt.py`.

**How it works**:
```
User switches away from Space A to Space B
    ↓
Panes in Space A move from LIVE → HIDDEN_ACTIVE (timer starts)
    ↓
While hidden, does the page title or audio change?
    ├── Yes → Activity Guard resets the timer AND lights up a calm dot on Space A's tab
    └── No → after 10 min idle (and if not pinned "Keep Running") → FROZEN (~0% CPU)
              ↓
         After 30 min idle → DISCARDED (frees browser RAM; screenshot shown when you return)
```

---

### `src/kazu/controllers/navigation.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Decides which links stay in the pane vs. open in your system browser, spots Google sign-in blocks, shows signed-out hints, and prevents downloads from overwriting existing files.
**Connects to**: Used by `ui/engine_qt.py`.

**How it works**:
```
User clicks a link inside a pane
    ↓
Is it http/https?
    ├── No (e.g. file://) → blocked
    └── Yes → Was Ctrl held?
         ├── Yes → opens in system browser
         └── No → Is the domain on the provider's allowlist?
              ├── Yes → stays inside the pane
              └── No → opens in your default browser
```
For downloads, if `report.pdf` already exists, `DownloadService` automatically picks `report (1).pdf`, `report (2).pdf`, etc.

---

### `src/kazu/controllers/autofit.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Gently scales down narrow panes (`clamp(width / target_width, 0.67, 1.0)`) so AI websites stay in their spacious desktop layout instead of collapsing into cramped phone views.
**Connects to**: Used by `ui/pane_frame.py`.

**How it works**:
Divides the pane's pixel width by the site's comfortable desktop width (around 950 px). Keeps the result between 67% and 100%. If the pane gets narrower than 67%, flags a gentle suggestion to move a pane to a new Space.

---

### `src/kazu/controllers/send.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Pastes a prompt into multiple panes at once without scraping websites and without wiping out whatever you already had on your clipboard.
**Connects to**: Used by `ui/main_window.py` and `ui/draft_composer.py`.

**How it works**:
```
User sends a prompt to 2 selected panes
    ↓
1. Saves whatever text is currently on the system clipboard
    ↓
2. Copies the prompt onto the clipboard
    ↓
3. For each selected pane:
    ├── Focuses the pane → triggers native Paste
    └── Could not focus → marks that pane as needing a manual click
    ↓
4. Always restores the user's original clipboard text (even if an error happens)
```

---

### `src/kazu/controllers/shortcuts.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Holds keyboard shortcuts, lets users rebind them, supports Pass-Through Mode, and steps aside when a website uses the same shortcut (such as ChatGPT's `Ctrl+K`).
**Connects to**: Used by `ui/main_window.py`.

**How it works**:
When a shortcut is pressed, checks if Pass-Through Mode is turned on or if the active website claims that key combo. If either is true, Kazu lets the website handle the keystroke instead.

---

### `src/kazu/ui/theme/tokens.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Single source of truth for Light Mode and Dark Mode colors, account dot colors, and Qt stylesheet generation.
**Connects to**: Used by `ui/main_window.py` and `ui/pane_frame.py`.

**How it works**:
Stores exact Light (`#FAFAF9`) and Dark (`#0F0F10`) color palettes and plugs them into one shared stylesheet template so both themes stay visually consistent.

---

### `src/kazu/ui/engine.py`, `ui/engine_qt.py`, & `ui/engine_companion.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: The hybrid browser engine layer: a shared contract (`engine.py`), the embedded Chromium pane (`engine_qt.py` — the **only** file allowed to import `QtWebEngine*`), and Companion Mode (`engine_companion.py`) for real Chrome/Edge/Brave windows.
**Connects to**: Uses `controllers/navigation.py`, `infra/paths.py`, `ui/oauth_popup.py`, `ui/webauthn_dialog.py`; used by `ui/main_window.py`.

**How it works**:
```
Pane needs to open an account
    ├── Engine is "embedded" (ui/engine_qt.py)
    │    ↓
    │   Builds private profile atomically (256 MB cache cap, persistent cookies)
    │    ↓
    │   Paints dark/light background BEFORE loading page (zero white flash)
    │    ↓
    │   Wires OAuth popups (520×680), WebAuthn security keys, and crash recovery
    │
    └── Engine is "companion" (ui/engine_companion.py)
         ↓
        Finds installed Chrome, Edge, or Brave on the computer
         ↓
        Launches it in bar-free App Mode with its own isolated --user-data-dir folder
```

---

### `src/kazu/ui/splitter_shield.py` & `ui/focus_guard.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: Two invisible polish helpers that make Kazu feel like a native desktop app.
**Connects to**: Used by `ui/space_stack.py` and `ui/main_window.py`.

**How it works**:
- `SplitterDragShield`: Raises an invisible glass layer over web views strictly while you drag a divider handle, preventing Chromium from stealing mouse events.
- `FocusGuard`: Automatically moves the blinking typing cursor back into the active chat pane right after you switch Spaces or close a popup with Escape.

---

### `src/kazu/ui/oauth_popup.py`, `ui/webauthn_dialog.py`, `ui/block_card.py`, `ui/toast.py`, `ui/find_bar.py`, `ui/draft_composer.py`, `ui/account_picker.py`, `ui/onboarding.py`, `ui/command_palette.py`, & `ui/settings_page.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: All interactive dialogs, cards, and overlays that make Kazu calm and predictable.
**Connects to**: Hosted inside `ui/pane_frame.py` and `ui/main_window.py`.

**How it works**:
- `oauth_popup.py`: Opens login popups centered at least 520×680 with a read-only lock icon showing the domain.
- `webauthn_dialog.py`: Shows native PIN, account-choice, and touch prompts for hardware security keys (like YubiKey).
- `block_card.py`: Displays calm one-click recovery cards if Google blocks embedded login, a tab crashes, or the internet drops.
- `toast.py`: Shows a 5-second floating banner with an **Undo** button when a pane is closed.
- `find_bar.py`: Opens a slim search bar (`Ctrl+F`) inside the active pane.
- `draft_composer.py`: Opens a bottom prompt box (`Ctrl+Shift+B`) to paste one prompt into selected panes safely.
- `account_picker.py`: Shows provider tiles, a Custom URL box, and asks *"Move it here, or open a second view?"* if you pick an already-open account.
- `onboarding.py`: Welcomes first-time users with the zero-password trust line and lets them choose Solo, Side-by-side, or Four-up.
- `command_palette.py`: Fuzzy-searches all actions and Spaces from `Ctrl+K`.
- `settings_page.py`: One scrollable page for General, Appearance, Performance (with truthful recursive RAM readout), Privacy, and About.

---

### `src/kazu/ui/top_bar.py`, `ui/pane_frame.py`, `ui/space_stack.py`, `ui/main_window.py`, `src/kazu/app.py`, & `src/kazu/__main__.py`
**Last updated**: 2026-11-20 13:05
**Purpose**: The main application shell that starts Kazu fast, draws the top bar and split panes, and shuts everything down cleanly.
**Connects to**: Connects all UI widgets, controllers, and infrastructure pieces together.

**How it works**:
```
User launches `kazu` (__main__.py → app.py)
    ↓
1. Turns on crisp HiDPI text scaling
    ↓
2. Checks SingleInstanceLock (if already open, focuses existing window and exits)
    ↓
3. Opens SQLite database, loads Settings, shows MainWindow immediately (< 1s)
    ↓
4. After the window paints, loads QtWebEngine lazily and staggers panes 150ms apart
    ↓
5. Every 15 seconds, evaluates background Spaces for Freeze/Discard transitions
    ↓
6. On quit, runs ShutdownCoordinator to flush every profile and database safely
```

---

### `scripts/phase0_spike.py` & `docs/phase0-findings.md`
**Last updated**: 2026-11-20 13:05
**Purpose**: Runnable Phase 0 hardware test harness and checklist for verifying tests T1–T14 on real machines.
**Connects to**: Uses `ui/engine_qt.py`, `ui/engine_companion.py`, `infra/memory.py`, and `infra/shutdown.py`.

**How it works**:
Opens two isolated embedded panes side by side in dark mode, displays live recursive RAM usage every 2 seconds, and provides a one-click button to launch a Gemini Companion window.

---

### `packaging/*` & `.github/workflows/ci.yml`
**Last updated**: 2026-11-20 13:05
**Purpose**: Ready-to-use installer configurations (Windows Inno Setup, macOS Hardened Runtime entitlements, Ubuntu 24.04 AppArmor sandbox profile) and 3-OS GitHub Actions CI pipeline.
**Connects to**: Used during automated testing and release builds.

---

### `tests/*`
**Last updated**: 2026-11-20 13:05
**Purpose**: Automated test suite verifying architecture rules, domain/layout operations, SQLite migrations, controllers, lifecycle state transitions, navigation policy, clipboard safety, and security guards.
**Connects to**: Tests all modules in `src/kazu/`.

---

## Change Log

| When | File | What Changed |
|------|------|--------------|
| 2026-11-20 13:05 | All project files | Initial complete implementation of Kazu v4 architecture: zero-Qt domain layer, SQLite migrations, owner-only paths, hybrid `PaneEngine` (`engine_qt.py` + `engine_companion.py`), 4-tier activity-aware lifecycle, all 10 silent everyday bugs designed out, Phase 0 spike, packaging/CI scaffolds, automated test suite, and `code-doc.md`. |

---

## Updates — 2026-11-20 18:30 (Space Deletion UX, App Logo Icons, & Native Installers)

### `src/kazu/ui/top_bar.py` & `src/kazu/ui/main_window.py` (Space Delete `×` + Confirmation)
**Last updated**: 2026-11-20 18:30
**Purpose**: Adds a `×` button on the right side of every Space tab (when 2 or more Spaces exist) and asks for confirmation before deleting a Space, with a *"Do not show this again"* option.
**Connects to**: Uses `AppSettings.confirm_delete_space` (`domain/models.py`, `infra/db.py`), `SpaceStack.remove_space()` (`ui/space_stack.py`), and `SettingsDialog` (`ui/settings_page.py`).

**How it works**:
```
User clicks the "×" button on the right side of a Space tab
    ↓
Is this the only Space left?
    ├── Yes → shows calm toast: "You need at least one Space."
    └── No → checks `settings.confirm_delete_space`
         ├── True → shows confirmation dialog:
         │      "Are you sure you want to delete '<Space>'?"
         │      [ ] Do not show this again
         │      [Yes, delete]   [No, don't delete]
         │      ├── Clicked "No, don't delete" → cancels immediately
         │      └── Clicked "Yes, delete" → if checkbox ticked, saves preference = False
         └── False → proceeds directly
              ↓
         Closes and frees all panes in that Space (accounts & logins stay safe)
              ↓
         Deletes the Space from SQLite and switches cleanly to a remaining Space
```
Users can turn the confirmation dialog back on anytime under **Settings → General → Ask for confirmation before deleting a Space**.

---

### `src/kazu/assets/kazu_logo.png`, `packaging/icons/*`, `packaging/kazu.spec`, `packaging/linux/kazu.desktop`, `scripts/install_desktop_entry.py`, & `.github/workflows/release.yml`
**Last updated**: 2026-11-20 18:30
**Purpose**: Embeds the official Kazu logo across every operating system and builds native one-click installers (Windows `.exe`, macOS `.dmg`, Linux `.deb`) automatically on GitHub Releases so Kazu lives in the Start Menu / Applications folder like any regular app.
**Connects to**: `src/kazu/app.py` loads `kazu_logo.png` at runtime (and sets Windows' taskbar `AppUserModelID`); `packaging/kazu.spec` and `.github/workflows/release.yml` bundle the native installers.

**How it works**:
```
Maintainer pushes a GitHub tag (e.g. `git tag v0.1.0 && git push origin v0.1.0`)
    ↓
GitHub Actions runs `.github/workflows/release.yml` on Windows, macOS, and Ubuntu
    ├── Windows → builds `Kazu-Setup-x.y.z-Windows-x64.exe` (Start Menu + Desktop + Kazu `.ico`)
    ├── macOS   → builds `Kazu-x.y.z-macOS.dmg` (drag `Kazu.app` to Applications with `.icns`)
    └── Linux   → builds `kazu_x.y.z_amd64.deb` (Applications menu `.desktop` + icon + AppArmor)
    ↓
All three installers attach automatically to the GitHub Release page for one-click download
```
Developers who install from source can also run `uv run python scripts/install_desktop_entry.py` to register Kazu in their Start Menu / Applications launcher immediately.

| When | File | What Changed |
|------|------|--------------|
| 2026-11-20 18:30 | `top_bar.py`, `main_window.py`, `space_stack.py`, `models.py`, `db.py`, `settings_page.py`, `tokens.py` | Added right-side `×` delete button on Space tabs, `"Yes, delete"` / `"No, don't delete"` confirmation dialog with persisted `"Do not show this again"` checkbox, Settings toggle to re-enable confirmation, and clean pane disposal on Space deletion. |
| 2026-11-20 18:30 | `app.py`, `assets/kazu_logo.png`, `packaging/icons/*`, `packaging/kazu.spec`, `packaging/windows/kazu.iss`, `packaging/linux/kazu.desktop`, `scripts/install_desktop_entry.py`, `.github/workflows/release.yml`, `README.md` | Generated PNG/ICO/ICNS icons from `KAZU_LOGO.jpg`, wired runtime window & Windows taskbar icon, added automated 3-OS GitHub Release installers (Windows `.exe`, macOS `.dmg`, Linux `.deb`), and added Start Menu / Applications launcher helper script. |

---

## Updates — 2026-11-20 18:55 (Windowless Launch — Zero Terminal Window on Windows)

### `pyproject.toml`, `scripts/install_desktop_entry.py`, & `src/kazu/app.py`
**Last updated**: 2026-11-20 18:55
**Purpose**: Removes the black terminal/console window that appeared behind Kazu on Windows and silences noisy Chromium `Permissions-Policy` console warnings.
**Connects to**: Affects how Windows Start Menu shortcuts and `uv sync` launch `kazu`.

**How it works**:
```
User clicks Kazu in the Windows Start Menu (or runs `kazu`)
    ↓
1. `pyproject.toml` now registers `kazu` under `[project.gui-scripts]`
   (builds a native Windows GUI launcher with NO console window)
    ↓
2. `scripts/install_desktop_entry.py` points the Windows Start Menu shortcut
   to `pythonw.exe -m kazu` (guaranteed windowless)
    ↓
3. `app.py` sets `--log-level=3` and `QT_LOGGING_RULES` before Qt starts
   so Chromium's background warnings stay silent
```

| When | File | What Changed |
|------|------|--------------|
| 2026-11-20 18:55 | `pyproject.toml`, `scripts/install_desktop_entry.py`, `src/kazu/app.py` | Switched `kazu` to `[project.gui-scripts]`, updated Windows Start Menu shortcut to use windowless `pythonw.exe -m kazu`, and silenced noisy Chromium `stderr` logs. |
