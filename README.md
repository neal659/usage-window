# Usage Window

A small Windows desktop window that shows your Claude usage:
the 5-hour **Current** window and the 7-day **Weekly** window.

## Run it

Requires Python 3 (tkinter is included in the standard Windows installer). Nothing else to install.

- Double-click `usage_window.pyw`, or run `pythonw usage_window.pyw` from this folder.
- Or build a single `.exe` with PyInstaller (`--onefile --noconsole`); it ends up in `dist/UsageWindow.exe`.
- It also starts automatically when you sign in to Windows (shortcut in your Startup folder).
  Delete `Usage Window.lnk` from `shell:startup` to turn that off.

Files used by the app:
- `icon.png`: the small icon top-left (transparent background)
- `icon.ico`: the taskbar and title-bar icon (16, 32, 48 and 256 px)

## Data

- Reads the OAuth token from `%USERPROFILE%\.claude\.credentials.json`. The token is
  used only in the `Authorization` header and is never printed, logged or shown.
- Refreshes every 60 seconds. Press F5, or click the creature, to fetch now.
- Shows only the two usage windows. Fable usage and account details are not shown.
- If the server says to slow down (HTTP 429), it waits at least 5 minutes before trying again.

## The creature

The orange pixel creature at the top of the window is animated (about 8 frames per second):

- **Idle:** it bobs up and down, and every few seconds it blinks.
- **Walking:** for a few seconds every 12 seconds it walks in place.
- **Hover:** when the mouse is over it, its eyes widen.
- **Click:** a short jump, then the usage is fetched now.
- **Drag:** hold the left button on it and move the mouse to move the whole window. A click with no movement counts as a click.
- **Right-click:** opens the same dropdown menu as the three dots.

Its body colour follows the current bar colour, and its eyes follow the background.

### Keyboard (while the window has focus)

- **Left / Right:** walk while held. It walks off one side and comes back in on the other.
- **Double-tap Left or Right:** dash. Hold Up (or press it just before) for a diagonal dash.
- **Up:** jump. Press Up again in the air for a double jump: a bigger boost, with a puff of dust from its feet.
- **Down:** crouch while held.
- **F5:** fetch the usage now.

The scenic modes have an obstacle on the floor (a stump, coral, rock and so on). The creature cannot walk through it, but it can jump onto it or over it.

## Menu (three dots, top-right)

A dropdown menu drawn inside the window:

- **Modes:** light, dark, hell, underwater, jungle, fire, moon. The scenic modes have animated
  scenery (falling leaves, fish, embers, blinking stars and a shooting star).
- **Compact:** a small window with just the two percentages.
- **Exit**

At each start the window picks one of hell, underwater, jungle, fire or moon at random.

Settings are saved to `usage_settings.json` in this folder.

## Network requests

This app makes two kinds of network request:

| Method | URL | Purpose |
|---|---|---|
| GET | `https://api.anthropic.com/api/oauth/usage` | Read the 5-hour and 7-day utilisation and reset times |
| POST | `https://platform.claude.com/v1/oauth/token` | Renew the login when it is about to expire (sends only the refresh token; saves the new token back to `.credentials.json`, as Claude Code does) |

Headers sent: `Authorization: Bearer <token from .credentials.json>`, `anthropic-beta: oauth-2025-04-20`,
`Accept`, and `User-Agent: usage-window`.

Nothing else is contacted: no telemetry, no update checks, no other hosts.

## Files

- `usage_window.pyw`: the whole app (one file, commented)
- `usage_settings.json`: created automatically when you change a setting
- `icon.png`, `icon.ico`: icons as described above
