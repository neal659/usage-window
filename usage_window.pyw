"""
Usage Window - a small Windows desktop app that shows your Claude usage.

Network access: this app makes exactly ONE kind of request, a GET to
https://api.anthropic.com/api/oauth/usage (see fetch_usage()). Nothing else
is contacted. The OAuth token is read from %USERPROFILE%\\.claude\\.credentials.json
and is only sent in the Authorization header to that host. It is never printed,
logged, or shown on screen.

Only the 5-hour ("Current") and 7-day ("Weekly") windows are read. Account
details and other usage buckets are ignored.

Run with:  pythonw usage_window.pyw   (or double-click the file)
Requires only Python 3 with tkinter (included in the standard Windows installer).
"""

import datetime as dt
import json
import math
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

if getattr(sys, "frozen", False):                    # running as a packaged .exe
    APP_DIR = os.path.dirname(sys.executable)        # settings are saved next to the .exe
    RESOURCE_DIR = sys._MEIPASS                      # the icons are bundled inside the .exe
else:
    APP_DIR = RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(APP_DIR, "usage_settings.json")  # local settings
ICON_PNG = os.path.join(RESOURCE_DIR, "icon.png")              # shown top-left
ICON_ICO = os.path.join(RESOURCE_DIR, "icon.ico")              # taskbar / title bar
CREDENTIALS_FILE = os.path.join(
    os.environ.get("USERPROFILE", os.path.expanduser("~")), ".claude", ".credentials.json"
)
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"        # the only host we contact
REFRESH_SECONDS = 60
SETTINGS_VERSION = 3
WINDOW_W, WINDOW_H = 270, 363  # full-size window: 14 px margins at the sides and bottom
SCREEN_MARGIN = 12
COMPACT_W, COMPACT_H = 150, 112   # the Compact mode: only the Current card, much smaller
FONT = "Bahnschrift"   # a clean, modern Windows font (falls back to a default if missing)
CARD_RADIUS = 16
BAR_THICKNESS = 12
DEFAULT_PRESET = "light"
CARDS_TOP = 109              # y of the first card, below the creature area

# The colour modes. Each one sets every colour.
PRESETS = {
    "light": {
        "bg": "#F2F2F5", "card": "#FFFFFF", "text": "#111216",
        "pill_bg": "#111216", "pill_text": "#FFFFFF", "track": "#E4E4EA",
        "bar_current": "#FF7A1A", "bar_weekly": "#22B455", "border": "#F2F2F5",
    },
    "dark": {
        "bg": "#0E0F13", "card": "#1C1E25", "text": "#F4F5F7",
        "pill_bg": "#F4F5F7", "pill_text": "#0E0F13", "track": "#3A3D48",
        "bar_current": "#FF8A2B", "bar_weekly": "#3DDC84", "border": "#0E0F13",
    },
    "hell": {
        "bg": "#140708", "card": "#211013", "text": "#F3E4E6",
        "pill_bg": "#E24A5B", "pill_text": "#140708", "track": "#3B1A1F",
        "bar_current": "#FF4D5E", "bar_weekly": "#FFB86B", "border": "#140708",
    },
    "underwater": {
        "bg": "#060D16", "card": "#0E1A28", "text": "#DCEBF7",
        "pill_bg": "#5AA9E6", "pill_text": "#060D16", "track": "#1B2E42",
        "bar_current": "#4FC3F7", "bar_weekly": "#9B8CFF", "border": "#060D16",
    },
    "jungle": {
        "bg": "#07110B", "card": "#0F1D14", "text": "#E2F2E6",
        "pill_bg": "#7BD389", "pill_text": "#07110B", "track": "#1B3024",
        "bar_current": "#B8E05C", "bar_weekly": "#2EC4B6", "border": "#07110B",
    },
    "fire": {
        "bg": "#120B07", "card": "#1F150F", "text": "#F5E8DD",
        "pill_bg": "#F08A4B", "pill_text": "#120B07", "track": "#372519",
        "bar_current": "#FFB347", "bar_weekly": "#D9534F", "border": "#120B07",
    },
    "moon": {
        "bg": "#1A1028", "card": "#251A3A", "text": "#F2EAFF",
        "pill_bg": "#C9A7FF", "pill_text": "#1A1028", "track": "#3A2C55",
        "bar_current": "#FF8FAB", "bar_weekly": "#7CE38B", "border": "#1A1028",
    },
}

# Pixel-art fallback icon (12x12), used only if icon.png is missing.
PIXEL_ICON = [
    "............",
    ".KKKKKKKKKK.",
    ".K........K.",
    ".K.OOOOOO.K.",
    ".K........K.",
    ".K.GGGGGG.K.",
    ".K........K.",
    ".K.OOOO...K.",
    ".K........K.",
    ".KKKKKKKKKK.",
    "............",
    "............",
]
PIXEL_COLORS = {"K": "#1C1E25", "O": "#FF7A1A", "G": "#22B455", ".": "#000000"}

# Animated creature in the header: the same figure as icon.png, drawn on a 15 x 10
# grid. 'O' = body colour, 'E' = eye colour, '.' = empty. Rows 0-6 are the body
# (it bobs up and down by one pixel), rows 8-9 are the legs.
CREATURE_PX = 4                  # on-screen size of one creature pixel (grid is 60 x 40 px)
CREATURE_X, CREATURE_Y = 14, 50  # top-left of the creature when it is standing still
ANIM_MS = 125                    # about 8 frames per second
BODY_ROW = "..OOOOOOOOOOO.."
ARMS_ROW = "OOOOOOOOOOOOOOO"
EMPTY_ROW = "..............."
EYES_OPEN = ("..OOEOOOOOEOO..", "..OOEOOOOOEOO..")   # eyes in body rows 1-2
EYES_WIDE = ("..OEEOOOOOEEO..", "..OEEOOOOOEEO..")   # hover: wider eyes
EYES_SHUT = ("..OOOOOOOOOOO..", "..OEEOOOOOEEO..")   # blink: eyes become a closed line
LEGS_A = "...O..O.O..O..."
LEGS_B = "..O..O...O..O.."
JUMP_PX = (22, 26, 10, 0)        # height of the jump in screen pixels, one value per frame (0.5 s, higher and quicker)
WALK_PX = 3                      # walking speed in pixels per frame
WALK_HALF = 12                   # frames to walk out (and the same to walk back): 36 px each way
CREATURE_STEP = 4                   # pixels the creature moves per arrow-key press
RETURN_HOME_SECONDS = 5             # after this long without input, the creature slides back home
# One obstacle per mode, as (x start, x end, height above the floor). The moon uses MOON_ROCK.
SCENE_OBSTACLES = {
    "jungle": (146, 176, 14),       # mossy stump
    "underwater": (144, 176, 14),   # coral head
    "fire": (142, 178, 9),          # lava rock
    "hell": (140, 180, 8),          # magma vent
}
MOON_ROCK = (142, 178, 6)      # moon mode: a crater rim sticking out of the floor (x start, x end, height)
HIT_LEFT, HIT_RIGHT = 12, 48   # the legs are the only part that reaches the floor: their span (px from his left edge)
WALK_MIN_X, WALK_MAX_X = -60, 270  # fully off the left edge and fully off the right edge (window is 270 wide)
DASH_STEPS = (30, 24, 14)        # pixels moved on each dash frame (68 px in about 0.4 s)
DASH_LIFT = (18, 28, 0)          # height of a diagonal dash on each frame; back on the floor at the end
DOUBLE_TAP_MAX = 0.3             # two presses of the same arrow this close (seconds) make a dash
DOUBLE_TAP_MIN = 0.08            # closer than this is key auto-repeat, not a second tap
FX_TICKS = 4                     # dust and motion lines last 4 frames (about 0.5 s)
DASH_LEGS = ".O..O....O..O.."    # stretched legs for the dash pose


class UsageError(Exception):
    """An error with a message that is safe to show on screen (never contains the token)."""

    def __init__(self, message, retry_after=None):
        super().__init__(message)
        self.retry_after = retry_after      # seconds to wait before the next request, if known


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def mix_colors(c1, c2, t):
    """Blend hex colour c1 toward c2 by fraction t (0..1)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def readable_text(hex_color):
    """Black or white text, whichever is easier to read on hex_color."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#FFFFFF"


def tint_titlebar(root, bg_hex, text_hex):
    """
    Colour the Windows title bar to match the app (Windows 11 only).
    On older Windows versions the call is ignored and the normal bar stays.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())

        def colorref(hex_color):
            r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
            return r | (g << 8) | (b << 16)

        def set_attr(attr, value):
            v = ctypes.c_int(value)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

        set_attr(20, 1 if readable_text(bg_hex) == "#FFFFFF" else 0)  # dark title-bar buttons
        set_attr(35, colorref(bg_hex))     # DWMWA_CAPTION_COLOR
        set_attr(36, colorref(text_hex))   # DWMWA_TEXT_COLOR
    except Exception:
        pass                               # never let styling break the app


def round_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    """Draw a rounded rectangle as a smooth polygon (works on any Canvas)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ----------------------------------------------------------------------------
# Settings file (local JSON, next to this script)
# ----------------------------------------------------------------------------

def load_settings():
    settings = {"preset": DEFAULT_PRESET, "colors": dict(PRESETS[DEFAULT_PRESET])}
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return settings                         # no file yet, or unreadable
    if not isinstance(saved, dict) or saved.get("version") != SETTINGS_VERSION:
        return settings                         # older layout: start from the default mode
    settings["compact"] = bool(saved.get("compact", False))
    name = saved.get("preset")
    name = {"crimson": "hell", "abyss": "underwater", "moss": "jungle",
            "ember": "fire", "grape": "moon"}.get(name, name)   # old mode names from earlier versions
    if name in PRESETS:
        settings["preset"] = name
        settings["colors"] = dict(PRESETS[name])
    return settings


def save_settings(settings):
    data = {"version": SETTINGS_VERSION, "preset": settings["preset"], "colors": settings["colors"],
            "compact": settings.get("compact", False)}
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass  # settings simply won't persist; the app keeps working


# ----------------------------------------------------------------------------
# Usage data
# ----------------------------------------------------------------------------

def read_access_token():
    """Read the OAuth access token from the Claude Code credentials file."""
    try:
        with open(CREDENTIALS_FILE, encoding="utf-8") as f:
            creds = json.load(f)
    except (OSError, ValueError):
        raise UsageError("No Claude login. Sign in to Claude Code.")
    oauth = creds.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        raise UsageError("No Claude login. Sign in to Claude Code.")
    expires_ms = oauth.get("expiresAt")
    if isinstance(expires_ms, (int, float)) and expires_ms / 1000 < time.time():
        raise UsageError("Login expired. Open Claude Code.")
    return token


def parse_window(block):
    """Turn one usage block ({"utilization", "resets_at"}) into a simple dict."""
    if not isinstance(block, dict):
        return None
    util = block.get("utilization")
    if not isinstance(util, (int, float)) or isinstance(util, bool):
        return None
    resets_at = None
    try:
        resets_at = dt.datetime.fromisoformat(block["resets_at"])
        if resets_at.tzinfo is None:
            resets_at = resets_at.replace(tzinfo=dt.timezone.utc)
    except (KeyError, TypeError, ValueError):
        pass
    return {"percent": float(util), "resets_at": resets_at}


def fetch_usage():
    """
    THE ONLY NETWORK REQUEST IN THIS APP.
    GET https://api.anthropic.com/api/oauth/usage with the OAuth bearer token.
    """
    token = read_access_token()
    request = urllib.request.Request(USAGE_URL, headers={
        "Authorization": "Bearer " + token,
        "anthropic-beta": "oauth-2025-04-20",
        "Accept": "application/json",
        "User-Agent": "usage-window",
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:          # must come before URLError (it is a subclass)
        if e.code in (401, 403):
            raise UsageError("Login rejected. Sign in to Claude Code.")
        if e.code == 429:
            # Rate limited: wait as long as the server asks, at least 5 minutes by default.
            retry = e.headers.get("Retry-After") if e.headers else None
            wait = int(retry) if retry and retry.isdigit() else 300
            raise UsageError("Rate limited. Retrying in %d min." % max(1, wait // 60),
                             retry_after=max(wait, 300))
        raise UsageError("Server error (HTTP %d)." % e.code)
    except (urllib.error.URLError, OSError, ValueError):
        raise UsageError("Could not reach the server.")
    return {"current": parse_window(data.get("five_hour")),
            "weekly": parse_window(data.get("seven_day"))}


def format_remaining(seconds):
    """Format a duration like '1h 22m', '45m' or '2d 3h'."""
    if seconds <= 0:
        return "now"
    minutes = int(seconds // 60)
    days, minutes = divmod(minutes, 1440)
    hours, minutes = divmod(minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{max(minutes, 1)}m"


# ----------------------------------------------------------------------------
# The application window
# ----------------------------------------------------------------------------

class UsageApp:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        # Start in a random scenery each time the app opens. Not saved, so the next start picks again.
        self.settings["preset"] = random.choice(("hell", "underwater", "jungle", "fire", "moon"))
        self.settings["colors"] = dict(PRESETS[self.settings["preset"]])
        self.data = None            # last good result: {"current": ..., "weekly": ...}
        self.error = None           # last error message (shown in the status line)
        self.last_ok = None         # time.time() of the last good fetch
        self.fetching = False
        self.results = queue.Queue()
        self.hits = []              # clickable areas: (x1, y1, x2, y2, action)
        self._menu_open = False     # the three-dot dropdown is drawn on the canvas
        self.menu_hits = []         # clickable dropdown rows: (x1, y1, x2, y2, command)
        self._auto_id = None
        self.anim_frame = 0         # counts animation frames (blink, walk and bob timing)
        self.jump_step = None       # index into JUMP_PX while jumping, else None
        self.hovering = False       # mouse is over the creature
        self.drag = None            # set while the left button is held on the creature
        self.creature_x = CREATURE_X   # left edge of the creature (it walks sideways)
        self.creature_y = CREATURE_Y   # top edge of the creature (arrow keys can move it up and down)
        self.last_input = time.time()  # when the user last clicked, dragged or pressed an arrow key
        self.facing = 1             # 1 = facing right, -1 = facing left
        self.walk_left = 0          # frames left in the current walk trip (0 = not walking)
        self.steer_frames = 0       # frames left to show walking after an arrow-key press
        self.star_items = []        # moon mode: stars that can blink
        self.blinking = {}          # moon mode: stars currently dimmed, {canvas id: (frame to restore, colour)}
        self.shot = None            # moon mode: the shooting star in flight (or None)
        self.air_jumps = 0          # 1 after a double jump in the air (reset when he lands)
        self.embers = []            # flying embers in fire and hell mode
        self.fish = []              # swimming fish in underwater mode
        self.falling_leaves = []    # falling leaves in jungle mode
        self.next_shot = time.time() + 10   # the next shooting star, every 10 seconds
        self.walk_phase = 0.0       # leg-cycle position while steering (speeds up with the keys)
        self.steer_dir = 0          # -1 walking left, +1 walking right, 0 not walking
        self.steer_held = False     # True while a Left/Right key is held down
        self.steer_since = 0.0      # when the current key hold started (walking speeds up with time)
        self.steer_tail = 0         # ticks left to keep walking after the key is released
        self.steer_px = 3.0         # pixels moved per tick while walking
        self.crouching = False      # True while Down is held (he crouches and walks slower)
        self.walk_dir = 1           # direction of the outward part of the trip
        self.walk_x0 = CREATURE_X   # where the trip started, so the creature returns there
        self.next_walk = random.randint(80, 160)   # next walk: 10-20 s later
        self.keys_down = set()      # arrow keys currently held (auto-repeat does not count as a new press)
        self.last_press = {}        # time of the last new press of each Left/Right key
        self.up_time = -9.0         # time of the last new Up press (for diagonal dashes)
        self.dash_left = 0          # frames left in a dash (0 = not dashing)
        self.dash_dir = 1           # direction of the current dash
        self.dash_diag = False      # True for a diagonal (up-left or up-right) dash
        self.dash_lift = 0          # current height of a diagonal dash, in pixels
        self.fx = []                # dust and motion-line effects: dicts with position, speed and life

        root.title("")                      # no title text in the window's title bar
        root.attributes("-topmost", True)   # stay above other windows, never drop behind them
        root.minsize(100, 60)               # the Compact mode is much smaller

        self.icon = self.load_icon()
        self.set_window_icon()

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", self.on_leave)
        self.canvas.bind("<Button-3>", self.on_right_click)
        root.bind("<F5>", lambda e: self.refresh())
        root.bind("<Escape>", lambda e: self.close_menu())
        for key in ("<Left>", "<Right>", "<Up>", "<Down>"):   # only fires while this window has focus
            root.bind(key, self.on_arrow)
        root.bind("<KeyRelease>", self.on_key_release)

        self.apply_geometry()
        self.redraw()
        self.refresh()
        self.poll_results()
        self.tick()
        self.animate()

    # ---- icons -----------------------------------------------------------

    def load_icon(self):
        """Small icon for the top-left corner: ./icon.png, or the built-in pixel icon."""
        if os.path.exists(ICON_PNG):
            try:
                img = tk.PhotoImage(master=self.root, file=ICON_PNG)
                factor = max(1, -(-img.width() // 24))      # shrink to about 24 px
                return img.subsample(factor) if factor > 1 else img
            except tk.TclError:
                pass
        rows = [[PIXEL_COLORS[ch] for ch in line] for line in PIXEL_ICON]
        img = tk.PhotoImage(master=self.root, width=12, height=12)
        img.put(tuple(tuple(r) for r in rows))
        for y, line in enumerate(PIXEL_ICON):
            for x, ch in enumerate(line):
                if ch == ".":
                    img.transparency_set(x, y, True)
        return img.zoom(2)

    def set_window_icon(self):
        """Taskbar and title-bar icon. Uses icon.ico (multi-size) when present."""
        if os.path.exists(ICON_ICO):
            try:
                self.root.iconbitmap(ICON_ICO)
                return
            except tk.TclError:
                pass
        self.root.iconphoto(False, self.icon)

    # ---- helpers ---------------------------------------------------------

    def c(self, key):
        return self.settings["colors"][key]

    def save_and_redraw(self):
        save_settings(self.settings)
        self.apply_geometry()
        self.redraw()

    # ---- drawing ---------------------------------------------------------

    def toggle_compact(self):
        """Compact view is a separate on/off option: it uses the colours of the current mode."""
        self.settings["compact"] = not self.settings.get("compact", False)
        self.save_and_redraw()

    def is_compact(self):
        """True in the Compact mode, except while its menu is open (the menu needs the full window)."""
        return self.settings.get("compact", False) and not self._menu_open

    def apply_geometry(self):
        """Keep the top-right corner: full size normally, the small size in Compact mode."""
        w, h = (COMPACT_W, COMPACT_H) if self.is_compact() else (WINDOW_W, WINDOW_H)
        x = self.root.winfo_screenwidth() - w - SCREEN_MARGIN
        self.root.geometry(f"{w}x{h}+{x}+{SCREEN_MARGIN}")

    def draw_compact(self, w, h):
        """Compact mode: only the Current card, with a small three-dot button to open the menu."""
        c = self.canvas
        self.hits = [(w - 22, 36, w - 6, 64, "menu")]
        self.draw_card(6, 6, w - 6, h - 6, "current", "Current", self.c("bar_current"))
        for dy in (-5, 0, 5):
            c.create_oval(w - 14 - 1.5, 50 + dy - 1.5, w - 14 + 1.5, 50 + dy + 1.5,
                          fill=self.c("text"), outline="")

    def redraw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:                   # window not laid out yet
            return
        bg, text = self.c("bg"), self.c("text")
        self.root.configure(bg=bg)
        c.configure(bg=bg)
        tint_titlebar(self.root, bg, text)
        if self.is_compact():
            self.draw_compact(w, h)
            return
        self.draw_scene(w, CREATURE_Y + 10 * CREATURE_PX)   # background and obstacle of this mode
        pad = 14
        self.hits = []

        # Header: animated creature top-left, three dots top-right (no background, no title)
        floor_y = CREATURE_Y + 10 * CREATURE_PX      # the creature's feet rest on this floor line
        c.create_line(pad, floor_y, w - pad, floor_y, fill=mix_colors(text, bg, 0.6))
        self.draw_creature()
        dx1, dx2, dy1, dy2 = w - pad - 16, w - pad, 12, 36
        dcx, dcy = (dx1 + dx2) / 2, (dy1 + dy2) / 2
        for dy in (-5, 0, 5):
            c.create_oval(dcx - 1.5, dcy + dy - 1.5, dcx + 1.5, dcy + dy + 1.5,
                          fill=text, outline="")
        self.hits.append((dx1, dy1, dx2, dy2, "menu"))

        # Two cards: Current (5-hour) and Weekly (7-day)
        card_h, gap = 116, 8
        cards = [("current", "Current", "bar_current"), ("weekly", "Weekly", "bar_weekly")]
        for i, (key, label, bar_key) in enumerate(cards):
            y1 = CARDS_TOP + i * (card_h + gap)
            self.draw_card(pad, y1, w - pad, y1 + card_h, key, label, self.c(bar_key))

        # Bottom line: shows only error messages (empty when everything is fine)
        c.create_text(pad, h - 3, anchor="sw", text=self.status_text(),
                      font=("Consolas", 7), fill=mix_colors(text, bg, 0.5),
                      width=w - 2 * pad, tags=("status",))
        if self._menu_open:                    # the dropdown sits on top of everything
            self.draw_menu(w)

    def draw_card(self, x1, y1, x2, y2, key, label, bar_color):
        c = self.canvas
        border = self.c("border")
        data = (self.data or {}).get(key)

        # Card background
        round_rect(c, x1, y1, x2, y2, CARD_RADIUS, fill=self.c("card"), outline=border,
                   width=2 if border != self.c("card") else 0)

        # Label pill, top-right
        pill_font = tkfont.Font(root=self.root, family=FONT, size=7, weight="bold")
        px2 = x2 - 12
        px1 = px2 - pill_font.measure(label) - 18
        py1, py2 = y1 + 8, y1 + 26
        round_rect(c, px1, py1, px2, py2, 9, fill=self.c("pill_bg"), outline="")
        c.create_text((px1 + px2) / 2, (py1 + py2) / 2, text=label, font=pill_font,
                      fill=self.c("pill_text"))

        # Big percent, left
        pct_text = "%d%%" % round(data["percent"]) if data else "--%"
        c.create_text(x1 + 14, y1 + 44, anchor="w", text=pct_text,
                      font=(FONT, 20, "bold"), fill=self.c("text"))

        # Thick progress bar with fully rounded ends. The fill colour never changes.
        bar_x1, bar_x2 = x1 + 14, x2 - 14
        bar_y1 = y2 - 36
        bar_y2 = bar_y1 + BAR_THICKNESS
        round_rect(c, bar_x1, bar_y1, bar_x2, bar_y2, BAR_THICKNESS / 2,
                   fill=self.c("track"), outline="")
        if data and data["percent"] > 0:
            fraction = min(max(data["percent"] / 100.0, 0.0), 1.0)
            fill_w = max(BAR_THICKNESS, (bar_x2 - bar_x1) * fraction)
            round_rect(c, bar_x1, bar_y1, bar_x1 + fill_w, bar_y2, BAR_THICKNESS / 2,
                       fill=bar_color, outline="")

        # "Resets in ..." line, small and gray
        c.create_text(bar_x1, bar_y2 + 4, anchor="nw", text=self.reset_text(data),
                      font=(FONT, 7), fill=mix_colors(self.c("text"), self.c("card"), 0.5),
                      tags=("reset_" + key,))

    def reset_text(self, data):
        if not data or not data.get("resets_at"):
            return "Reset time unknown"
        resets = data["resets_at"]
        seconds = (resets - dt.datetime.now(dt.timezone.utc)).total_seconds()
        local = resets.astimezone()
        same_day = local.date() == dt.datetime.now().date()
        clock = local.strftime("%H:%M") if same_day else local.strftime("%a %H:%M")
        return f"Resets in {format_remaining(seconds)} · {clock}"

    def status_text(self):
        """Only errors are shown. No 'updated ... ago' text."""
        if self.error and not self.error.startswith("Rate limited"):   # rate limits are not shown
            return self.error
        return ""

    # ---- live text (once per second, no full redraw) ----------------------

    def tick(self):
        data = self.data or {}
        self.canvas.itemconfigure("reset_current", text=self.reset_text(data.get("current")))
        self.canvas.itemconfigure("reset_weekly", text=self.reset_text(data.get("weekly")))
        self.canvas.itemconfigure("status", text=self.status_text())
        self.root.after(1000, self.tick)

    # ---- data refresh ----------------------------------------------------

    def refresh(self):
        """Fetch usage in a background thread so the window never freezes."""
        self.schedule_auto_refresh()
        if self.fetching:
            return
        self.fetching = True
        threading.Thread(target=self._worker, daemon=True).start()

    def schedule_auto_refresh(self, delay=REFRESH_SECONDS):
        if self._auto_id is not None:
            self.root.after_cancel(self._auto_id)
        self._auto_id = self.root.after(int(delay * 1000), self.refresh)

    def _worker(self):
        # Each result is (kind, payload, seconds until the next automatic refresh)
        try:
            self.results.put(("ok", fetch_usage(), REFRESH_SECONDS))
        except UsageError as e:
            delay = e.retry_after or REFRESH_SECONDS
            self.results.put(("err", str(e), delay))
        except Exception:                       # never show or log internals
            self.results.put(("err", "Unexpected error.", REFRESH_SECONDS))

    def poll_results(self):
        try:
            while True:
                kind, payload, delay = self.results.get_nowait()
                self.fetching = False
                if kind == "ok":
                    self.data = payload
                    self.error = None
                    self.last_ok = time.time()
                else:
                    self.error = payload
                self.schedule_auto_refresh(delay)   # back off after errors such as rate limits
                self.redraw()
        except queue.Empty:
            pass
        self.root.after(200, self.poll_results)

    # ---- the creature: animation, hover, click and drag ------------------

    def eye_color(self):
        """Dark eyes: the background itself on dark modes, near-black on light ones."""
        bg = self.c("bg")
        return bg if readable_text(bg) == "#FFFFFF" else mix_colors(bg, "#000000", 0.8)

    def creature_frame(self):
        """Return (rows, lift) for the current frame: 10 grid rows and how high to jump."""
        f = self.anim_frame
        jumping = self.jump_step is not None
        dashing = self.dash_left > 0
        # Walking legs show on a random walk trip, and for a moment after each arrow-key press
        walking = not jumping and not dashing and (self.walk_left > 0 or self.steer_frames > 0)
        if f % 32 in (30, 31):                           # a blink about every 4 s
            eyes = EYES_SHUT
        elif self.hovering:
            eyes = EYES_WIDE
        else:
            eyes = EYES_OPEN
        if dashing:
            bob = 1                                      # body lifted and legs stretched: a leaning dash pose
            legs = (DASH_LEGS, DASH_LEGS)
        elif walking:
            # Steering uses walk_phase (it speeds up with the arrow keys); random trips use the frame count
            p = int(self.walk_phase) if self.steer_frames > 0 else f
            bob = p % 2                                  # bobs on every step
            legs = (LEGS_A, LEGS_B) if (p // 2) % 2 == 0 else (LEGS_B, LEGS_A)
        else:
            bob = (f // 4) % 2                           # slow idle bob
            legs = (LEGS_A, LEGS_A)
        if self.crouching:                               # shorter body while crouched
            body = [BODY_ROW, eyes[0], eyes[1], ARMS_ROW, BODY_ROW]
        else:
            body = [BODY_ROW, eyes[0], eyes[1], ARMS_ROW, ARMS_ROW, BODY_ROW, BODY_ROW]
        rows = [EMPTY_ROW] * 10
        top = 4 if self.crouching else (1 - bob)     # crouched: short body, no bobbing
        for i, row in enumerate(body):
            rows[top + i] = row
        if self.crouching:                               # squashed: legs tucked under the body
            rows[9] = legs[0]
            rows[8] = BODY_ROW
        else:
            rows[8], rows[9] = legs
        if self.facing < 0:                              # mirror the sprite to face left
            rows = [row[::-1] for row in rows]
        lift = JUMP_PX[self.jump_step] if jumping else 0   # jump height in pixels
        return rows, lift

    def draw_scene(self, w, floor_y):
        """Background texture and obstacle for the current mode."""
        draws = {"moon": self.draw_moon_texture, "jungle": self.draw_jungle,
                 "underwater": self.draw_underwater, "fire": self.draw_fire, "hell": self.draw_hell}
        draw = draws.get(self.settings["preset"])
        if draw is not None:
            draw(w, floor_y)

    def draw_leaf(self, x, y, length, angle, colour, tag="texture"):
        """A natural-looking leaf: a curved almond shape with a midrib, turned by angle (radians)."""
        c = self.canvas
        half = length * 0.28
        steps = 6
        top = [(i / steps * length, -half * math.sin(math.pi * i / steps)) for i in range(steps + 1)]
        bottom = [(i / steps * length, half * math.sin(math.pi * i / steps)) for i in range(steps + 1)]
        cos, sin = math.cos(angle), math.sin(angle)

        def place(px, py):
            return x + px * cos - py * sin, y + px * sin + py * cos

        outline = [v for p in top + bottom[::-1] for v in place(*p)]
        c.create_polygon(outline, fill=colour, outline="", smooth=True, tags=tag)
        vein = mix_colors(colour, "#000000", 0.25)
        c.create_line([v for p in ((0, 0), (length * 0.9, 0)) for v in place(*p)],
                      fill=vein, width=1, tags=tag)

    def draw_jungle(self, w, floor_y):
        """Jungle: a deep green forest with trunks, hanging vines, light shafts, ferns, spores and a mossy stump."""
        c = self.canvas
        rng = random.Random(11)
        # Forest: deep green at the top, lighter towards the ground
        bands = ("#0E1812", "#131F18", "#18291F", "#1F3328")   # greyer forest
        band_h = floor_y / len(bands)
        for i, colour in enumerate(bands):
            c.create_rectangle(0, i * band_h, w, (i + 1) * band_h + 1, fill=colour, outline="", tags="texture")
        # Soft light shafts coming down through the canopy
        shaft = mix_colors("#4A7A4A", "#163222", 0.6)
        for sx in (w * 0.2, w * 0.55, w * 0.85):
            c.create_polygon(sx - 10, 0, sx + 10, 0, sx + 30, floor_y, sx - 6, floor_y,
                             fill=shaft, outline="", tags="texture")
        # Two big trunks at the sides, with a mossy edge
        for tx in (w * 0.08, w * 0.9):
            c.create_polygon(tx - 8, 0, tx + 8, 0, tx + 11, floor_y, tx - 11, floor_y,
                             fill="#0A140C", outline="", tags="texture")
            c.create_line(tx - 8, 0, tx - 11, floor_y, fill="#2E5A2E", width=2, tags="texture")
        # Hanging vines
        for _ in range(7):
            vx, vl = rng.uniform(0, w), rng.uniform(40, 110)
            c.create_line(vx, 0, vx + rng.uniform(-6, 6), vl * 0.5, vx + rng.uniform(-4, 4), vl,
                          fill="#2F6B35", width=1, smooth=True, tags="texture")
        # Ferns on the ground: a few fronds from each base
        fern = "#3A5E42"
        for fx in range(6, int(w), 22):
            fh = rng.uniform(8, 16)
            for ang in (-0.9, -0.3, 0.3, 0.9):
                c.create_line(fx, floor_y, fx + math.sin(ang) * fh, floor_y - math.cos(ang) * fh,
                              fill=fern, width=2, tags="texture")
        leaf = mix_colors("#5ED36A", self.c("bg"), 0.2)      # brighter leaves
        for _ in range(6):
            x, y = rng.uniform(0, w), rng.uniform(0, floor_y - 20)
            self.draw_leaf(x, y, rng.uniform(8, 13), rng.uniform(0, 6.28), leaf)
        spore = mix_colors(self.c("text"), self.c("bg"), 0.7)
        for _ in range(30):
            x, y = rng.uniform(0, w), rng.uniform(0, floor_y - 10)
            r = rng.choice((0.7, 1.0))
            c.create_oval(x - r, y - r, x + r, y + r, fill=spore, outline="", tags="texture")
        grass = mix_colors("#3FA34D", "#6A7068", 0.55)      # greyer, less saturated grass
        for x in range(4, w, 9):
            h = rng.uniform(3, 6)
            c.create_line(x, floor_y, x - 2, floor_y - h, fill=grass, width=1, tags="texture")
            c.create_line(x, floor_y, x + 2, floor_y - h, fill=grass, width=1, tags="texture")
        # A mossy tree stump: rounded trunk, bark grooves, moss on top and small roots
        x1, x2, h = SCENE_OBSTACLES["jungle"]
        wood = mix_colors("#6B4423", self.c("bg"), 0.3)
        bark = mix_colors("#3A2514", self.c("bg"), 0.3)
        moss = "#4CAF50"
        c.create_polygon(x1 + 2, floor_y, x1, floor_y - h / 2, x1 + 2, floor_y - h, x2 - 2, floor_y - h,
                         x2, floor_y - h / 2, x2 - 2, floor_y, fill=wood, outline=bark, width=1,
                         smooth=True, tags="texture")
        for dx in range(6, int(x2 - x1) - 4, 6):               # bark grooves
            c.create_line(x1 + dx, floor_y - h + 3, x1 + dx + 1, floor_y - 2, fill=bark, width=1, tags="texture")
        c.create_line(x1 + 3, floor_y - h + 1, x2 - 3, floor_y - h + 1, fill=moss, width=3, tags="texture")
        for dx in range(4, int(x2 - x1) - 3, 6):               # moss bumps on top
            c.create_oval(x1 + dx, floor_y - h - 1, x1 + dx + 3, floor_y - h + 2,
                          fill="#66BB6A", outline="", tags="texture")
        # Roots: the base flares out on both sides, so the stump is wider at the bottom
        c.create_polygon(x1 - 3, floor_y, x1 + 3, floor_y - 6, x1 + 5, floor_y,
                         fill=wood, outline=bark, width=1, tags="texture")
        c.create_polygon(x2 + 3, floor_y, x2 - 3, floor_y - 6, x2 - 5, floor_y,
                         fill=wood, outline=bark, width=1, tags="texture")

    def draw_underwater(self, w, floor_y):
        """Underwater: rising bubbles, sand on the floor, and a coral head."""
        c = self.canvas
        rng = random.Random(12)
        bubble = mix_colors("#BEEBFF", self.c("bg"), 0.5)
        for _ in range(40):
            x, y = rng.uniform(0, w), rng.uniform(0, floor_y - 8)
            r = rng.choice((1.0, 1.5, 2.0))
            c.create_oval(x - r, y - r, x + r, y + r, outline=bubble, width=1, tags="texture")
        sand = mix_colors("#D9C27A", self.c("bg"), 0.5)
        for x in range(3, w, 7):
            c.create_oval(x, floor_y + 2, x + 1.5, floor_y + 3.5, fill=sand, outline="", tags="texture")
        x1, _, h = SCENE_OBSTACLES["underwater"]
        coral = ("#FF6F91", "#FF9E40", "#B47CFF")         # three colours
        for i, (dx, top) in enumerate(((4, h + 6), (11, h + 14), (18, h + 3), (25, h + 11), (31, h + 4))):
            c.create_line(x1 + dx, floor_y, x1 + dx, floor_y - top, fill=coral[i % 3], width=4, tags="texture")

    def draw_fire(self, w, floor_y):
        """Fire: a dusk sky in warm bands, a volcano with smoke, a lava river along the floor, and a lava rock."""
        c = self.canvas
        rng = random.Random(13)
        # Sky: warm bands, darkest at the top and orange near the horizon
        bands = ("#1A0C05", "#2E1408", "#4A2008", "#6A3010")
        band_h = floor_y / len(bands)
        for i, colour in enumerate(bands):
            c.create_rectangle(0, i * band_h, w, (i + 1) * band_h + 1, fill=colour, outline="", tags="texture")
        # A volcano on the horizon, with smoke puffs rising from its peak
        peak_x = w * 0.66
        c.create_polygon(0, floor_y, w * 0.42, floor_y - 16, peak_x - 14, floor_y - 40, peak_x + 14, floor_y - 40,
                         w * 0.9, floor_y - 18, w, floor_y, fill="#2A1208", outline="", tags="texture")
        smoke = mix_colors("#7A6A60", "#2A1208", 0.4)
        for i in range(3):
            sx = peak_x + rng.uniform(-6, 6)
            sy = floor_y - 46 - i * 8
            rx = 5 + i * 2
            c.create_oval(sx - rx, sy - rx * 0.5, sx + rx, sy + rx * 0.5, outline=smoke, width=1, tags="texture")
        # Lava river along the floor, wavy, with a glowing rim above the ground
        pts = []
        x = 0.0
        while x <= w:
            pts += [x, floor_y + 3 + rng.uniform(-1, 1)]
            x += rng.uniform(18, 30)
        pts += [w, floor_y + 3]
        c.create_rectangle(0, floor_y - 1, w, floor_y + 1, fill="#FF7A1A", outline="", tags="texture")
        c.create_line(pts, fill="#B33A10", width=3, smooth=True, tags="texture")
        # Dark ground below the lava
        c.create_rectangle(0, floor_y + 5, w, floor_y + 8, fill="#2A1208", outline="", tags="texture")
        # The obstacle: a lava rock with glowing cracks
        x1, x2, h = SCENE_OBSTACLES["fire"]
        c.create_polygon(x1, floor_y, x1 + 4, floor_y - h, x2 - 6, floor_y - h, x2, floor_y,
                         fill="#3A2420", outline="", tags="texture")
        c.create_line(x1 + 4, floor_y - h, x2 - 6, floor_y - h, fill="#FF7A1A", width=2, tags="texture")
        for dx in (10, 20):                                    # glowing cracks in the rock
            c.create_line(x1 + dx, floor_y - 1, x1 + dx + 3, floor_y - h * 0.5, x1 + dx - 1, floor_y - h + 1,
                          fill="#FF7A1A", width=1, tags="texture")

    def draw_hell(self, w, floor_y):
        """Hell: dark red sky in bands, a jagged mountain ridge, a lava glow along the floor, smoke and cracks."""
        c = self.canvas
        rng = random.Random(14)
        # Sky: dark red bands, darkest at the top
        bands = ("#1E0606", "#2A0A08", "#360E0A", "#421210")
        band_h = floor_y / len(bands)
        for i, colour in enumerate(bands):
            c.create_rectangle(0, i * band_h, w, (i + 1) * band_h + 1, fill=colour, outline="", tags="texture")
        # Jagged mountain ridge along the horizon
        points = [0, floor_y]
        x = 0.0
        while x < w + 20:
            x += rng.uniform(10, 22)
            points += [x, floor_y - rng.uniform(8, 26)]
        points += [w, floor_y]
        c.create_polygon(points, fill="#120404", outline="", tags="texture")
        # Lava glow along the floor line
        c.create_rectangle(0, floor_y - 1, w, floor_y + 2, fill="#B33A10", outline="", tags="texture")
        c.create_rectangle(0, floor_y + 2, w, floor_y + 4, fill="#6E1A08", outline="", tags="texture")
        # Smoke wisps above the ridge
        smoke = mix_colors("#8A6A7A", "#2A0A08", 0.5)
        for _ in range(7):
            x, y = rng.uniform(0, w), rng.uniform(10, floor_y - 30)
            rx = rng.uniform(8, 16)
            c.create_oval(x - rx, y - rx * 0.4, x + rx, y + rx * 0.4, outline=smoke, width=1, tags="texture")
        # Glowing cracks in the ground below the floor line
        crack = "#E0301E"
        for _ in range(5):
            x = rng.uniform(0, w)
            c.create_line(x, floor_y + 3, x + 4, floor_y + 6, x - 2, floor_y + 8, x + 3, floor_y + 11,
                          fill=crack, width=1, tags="texture")
        # The obstacle: a dark stone pillar with glowing red cracks
        x1, x2, h = SCENE_OBSTACLES["hell"]
        c.create_polygon(x1 + 2, floor_y, x1 + 4, floor_y - h, x2 - 4, floor_y - h, x2 - 2, floor_y,
                         fill="#2A1414", outline="#5A2A2A", width=2, tags="texture")
        for dx in (7, 13, 19):
            c.create_line(x1 + dx, floor_y - h + 1, x1 + dx + 2, floor_y - h / 2, x1 + dx - 1, floor_y - 1,
                          fill="#FF3B1F", width=1, tags="texture")

    def draw_moon_texture(self, w, floor_y):
        """Moon mode: stars in the background and craters along the floor. Fixed seed, so it never changes."""
        c = self.canvas
        rng = random.Random(7)
        star = mix_colors(self.c("text"), self.c("bg"), 0.65)
        self.star_items = []                 # (canvas id, colour) so stars can blink
        self.blinking = {}
        cols, rows = 12, 5                  # stars on a jittered grid, so they spread evenly over the sky
        for i in range(cols * rows):
            row, col = divmod(i, cols)
            x = (col + 0.5 + rng.uniform(-0.35, 0.35)) * w / cols
            y = (row + 0.5 + rng.uniform(-0.35, 0.35)) * (floor_y - 10) / rows
            r = rng.choice((0.7, 0.9, 1.1))
            item = c.create_oval(x - r, y - r, x + r, y + r, fill=star, outline="", tags="texture")
            self.star_items.append((item, star))
        # Craters: different sizes, and a shallow or deep rim
        rim = mix_colors(self.c("text"), self.c("bg"), 0.8)
        shadow = mix_colors(self.c("bg"), "#000000", 0.35)
        x = 8.0
        while x < w:
            rx = rng.uniform(3, 10)
            depth = rng.choice((1, 2, 3))
            cx, cy = x + rng.uniform(0, 14), floor_y + rng.uniform(3, 10)
            c.create_oval(cx - rx, cy - rx * 0.4, cx + rx, cy + rx * 0.4, fill=shadow, outline="", tags="texture")
            c.create_oval(cx - rx, cy - rx * 0.4, cx + rx, cy + rx * 0.4, outline=rim, width=depth, tags="texture")
            x += rng.uniform(24, 46)
        # A small crater rim sticking up out of the floor (the creature cannot walk through it)
        rock_x1, rock_x2, rock_h = MOON_ROCK
        rim_col = mix_colors(self.c("text"), self.c("bg"), 0.6)     # dimmer than the stars
        # Outer rim: a slightly curved top with sloped sides
        c.create_line(rock_x1, floor_y, rock_x1 + 7, floor_y - rock_h, rock_x2 - 7, floor_y - rock_h,
                      rock_x2, floor_y, fill=rim_col, width=3, tags="texture")
        # Inner dip of the crater, symmetric around the middle
        c.create_line(rock_x1 + 9, floor_y - rock_h + 2, rock_x1 + 13, floor_y - 2,
                      rock_x2 - 13, floor_y - 2, rock_x2 - 9, floor_y - rock_h + 2,
                      fill=rim_col, width=2, tags="texture")

    def draw_creature(self):
        """Redraw only the creature's own canvas items for the current frame."""
        if self.is_compact():                 # the Compact mode has no creature
            self.canvas.delete("creature")
            return
        c = self.canvas
        c.delete("creature")
        rows, lift = self.creature_frame()
        colors = {"O": self.c("bar_current"), "E": self.eye_color()}   # body follows the palette
        x0 = self.creature_x
        # Jump and diagonal dash both lift him; never draw higher than the top of the window
        # Stand on the rock top when his legs are over it (a jump can land him there)
        height = max(lift + self.dash_lift, self.rock_ground(x0))
        y0 = max(0, self.creature_y - height)
        # Keep the click/hover area on the creature's current position
        self.hits = [h for h in self.hits if h[4] != "creature"]
        self.hits.append((x0, 0, x0 + 15 * CREATURE_PX, CREATURE_Y + 10 * CREATURE_PX, "creature"))
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch in colors:
                    px, py = x0 + x * CREATURE_PX, y0 + y * CREATURE_PX
                    inset = CREATURE_PX // 4 if (ch == "E" and self.crouching) else 0   # crouched eyes are smaller
                    c.create_rectangle(px + inset, py + inset, px + CREATURE_PX - inset, py + CREATURE_PX - inset,
                                       fill=colors[ch], outline="", tags="creature")

    def step_home(self):
        """After RETURN_HOME_SECONDS without input, slide the creature back to its usual spot."""
        if time.time() - self.last_input < RETURN_HOME_SECONDS:
            return
        if self.walk_left > 0:
            return
        if self.jump_step is not None:
            # In the air on the way home: cover ground quickly so the jump carries him past the rock
            self.creature_x = self._toward(self.creature_x, CREATURE_X, 14)
            return
        target = self._toward(self.creature_x, CREATURE_X)
        if self.resolve_x(self.creature_x, target) != target:
            self.jump_step = 0              # the rock is in the way: jump over it
            return
        if target != self.creature_x:
            # Walking home looks like normal walking: face the way he goes, and move the legs
            self.facing = 1 if target > self.creature_x else -1
            self.steer_frames = 8
        self.creature_x = target
        self.creature_y = self._toward(self.creature_y, CREATURE_Y)

    @staticmethod
    def _toward(value, target, max_step=CREATURE_STEP):
        """Move value one step (max_step at most) toward target."""
        if value == target:
            return value
        step = min(max_step, abs(target - value))
        return value + step if target > value else value - step

    def on_key_release(self, event):
        """Releasing Left or Right stops the creature at once."""
        self.keys_down.discard(event.keysym)
        if event.keysym == "Down":
            self.crouching = False
        if event.keysym in ("Left", "Right") and self.steer_held:
            self.steer_held = False
            self.steer_tail = 0             # stop at once when the key is released

    def step_steer(self):
        """Walk while Left/Right is held: faster the longer the key is held, then a short tail."""
        if self.steer_held:
            held = time.time() - self.steer_since
            self.steer_px = min(14.0, 6.0 + 6.0 * held)     # speeds up quickly while held
        elif self.steer_tail > 0:
            self.steer_tail -= 1
        else:
            return
        self.steer_frames = 8               # keep the walking legs on while moving
        self.facing = self.steer_dir
        self.walk_left = 0
        speed = self.steer_px * (0.5 if self.crouching else 1.0)    # crouched walking is slower
        self.creature_x = self.wrap_x(int(round(self.creature_x + self.steer_dir * speed)))
        self.walk_x0 = self.creature_x

    def step_scene(self):
        """Moving details: flying embers now and then (fire, hell) and a few swimming fish (underwater)."""
        c = self.canvas
        preset = self.settings["preset"]
        c.delete("scene_fx")
        w = max(c.winfo_width(), 1)
        floor_y = CREATURE_Y + 10 * CREATURE_PX
        if preset in ("fire", "hell"):
            if random.random() < 0.03 and len(self.embers) < 5:     # about one every 4 s, not many
                self.embers.append({"x": random.uniform(0, w), "y": floor_y - 4, "life": 14})
            for e in self.embers:
                e["x"] += random.uniform(-0.4, 0.4)
                e["y"] -= 1.6
                e["life"] -= 1
            self.embers = [e for e in self.embers if e["life"] > 0 and e["y"] > 0]
            colour = "#FFA040" if preset == "fire" else "#FF5A2A"
            for e in self.embers:
                c.create_oval(e["x"] - 1.2, e["y"] - 1.2, e["x"] + 1.2, e["y"] + 1.2,
                              fill=colour, outline="", tags="scene_fx")
        else:
            self.embers = []
        if preset == "jungle":
            if random.random() < 0.08 and len(self.falling_leaves) < 8:     # about one every 1.5 s
                self.falling_leaves.append({"x": random.uniform(0, w), "y": -8.0,
                                            "phase": random.uniform(0, 6.28), "angle": random.uniform(0, 6.28)})
            for lf in self.falling_leaves:
                lf["y"] += 0.7
                lf["phase"] += 0.15
                lf["angle"] += 0.08
            self.falling_leaves = [lf for lf in self.falling_leaves if lf["y"] < floor_y]
            leaf = mix_colors("#5ED36A", self.c("bg"), 0.2)
            for lf in self.falling_leaves:
                sway = math.sin(lf["phase"]) * 6                 # leaves drift from side to side
                self.draw_leaf(lf["x"] + sway, lf["y"], 9, lf["angle"], leaf, tag="scene_fx")
        else:
            self.falling_leaves = []
        if preset == "underwater":
            if not self.fish:
                self.fish = [{"x": 40.0, "y": 30.0, "dir": 1, "col": "#FFB347"},
                             {"x": 150.0, "y": 48.0, "dir": -1, "col": "#7FD8FF"},
                             {"x": 215.0, "y": 22.0, "dir": 1, "col": "#FF6F91"}]
            for f in self.fish:
                f["x"] += f["dir"] * 0.5
                if f["x"] < -20:
                    f["x"] = w + 20
                elif f["x"] > w + 20:
                    f["x"] = -20
                x, y, d = f["x"], f["y"], f["dir"]
                c.create_oval(x - 5, y - 2.5, x + 5, y + 2.5, fill=f["col"], outline="", tags="scene_fx")
                c.create_polygon(x - 5 * d, y, x - 9 * d, y - 3, x - 9 * d, y + 3,
                                 fill=f["col"], outline="", tags="scene_fx")
        else:
            self.fish = []

    def step_moon(self):
        """Moon mode: stars blink now and then, and a shooting star crosses the sky every 10 seconds."""
        if self.settings["preset"] != "moon":
            return
        c = self.canvas
        # Every 30 frames (about 4 s) dim three random stars for about half a second
        if self.anim_frame % 30 == 0 and self.star_items:
            for item, colour in random.sample(self.star_items, min(3, len(self.star_items))):
                c.itemconfigure(item, fill=self.c("bg"))
                self.blinking[item] = (self.anim_frame + 4, colour)
        for item, (until, colour) in list(self.blinking.items()):
            if self.anim_frame >= until:
                c.itemconfigure(item, fill=colour)
                del self.blinking[item]
        # The shooting star: a short bright streak that moves down and to the left
        now = time.time()
        if self.shot is None and now >= self.next_shot:
            w = c.winfo_width()
            self.shot = {"x": random.uniform(w * 0.5, w), "y": random.uniform(10, 40), "t": 0}
            self.next_shot = now + 10
        c.delete("shooting")
        if self.shot is not None:
            s = self.shot
            hx, hy = s["x"] - 10 * s["t"], s["y"] + 6 * s["t"]
            c.create_line(hx + 26, hy - 15, hx, hy, fill=self.c("text"), width=2, tags="shooting")
            s["t"] += 1
            if s["t"] > 12:
                self.shot = None

    def wrap_x(self, x):
        """Walking fully off one side brings him back in on the other side."""
        span = WALK_MAX_X - WALK_MIN_X
        if x > WALK_MAX_X:
            x -= span
        elif x < WALK_MIN_X:
            x += span
        return x

    def obstacle(self):
        """The obstacle of the current mode as (x start, x end, height), or None."""
        if self.settings["preset"] == "moon":
            return MOON_ROCK
        return SCENE_OBSTACLES.get(self.settings["preset"])

    def rock_ground(self, x):
        """Height of the obstacle top under his legs when he stands at x (0 when there is none there)."""
        ob = self.obstacle()
        if ob is None:
            return 0
        rock_x1, rock_x2, rock_h = ob
        if x + HIT_RIGHT <= rock_x1 or x + HIT_LEFT >= rock_x2:
            return 0
        return rock_h

    def resolve_x(self, old_x, new_x):
        """
        Moon mode: the rock is solid from the side. He can stand on top of it, or jump onto it
        and over it, but he cannot walk into its side.
        """
        ob = self.obstacle()
        if ob is None or new_x == old_x:
            return new_x
        rock_x1, rock_x2, rock_h = ob
        lift = (JUMP_PX[self.jump_step] if self.jump_step is not None else 0) + self.dash_lift
        if max(lift, self.rock_ground(old_x)) >= rock_h:
            return new_x                     # high enough in the air, or already standing on the rock
        if new_x + HIT_RIGHT <= rock_x1 or new_x + HIT_LEFT >= rock_x2:
            return new_x                     # not touching the rock
        # stop at the side he came from
        return rock_x1 - HIT_RIGHT if new_x > old_x else rock_x2 - HIT_LEFT

    def steer_speed(self):
        """Leg-cycle speed multiplier: faster the longer the key is held (1x to 3x)."""
        if not self.steer_held:
            return 1.0
        return min(3.5, 1.0 + 2.0 * (time.time() - self.steer_since))

    def on_arrow(self, event):
        """Arrow keys move the creature while this window has keyboard focus."""
        now = time.time()
        self.last_input = now
        key = event.keysym
        new_press = key not in self.keys_down     # False for auto-repeat while the key is held
        self.keys_down.add(key)
        if key == "Down":              # holding Down crouches
            self.crouching = True
            return
        if key == "Up":                # Up makes him jump (no up/down walking)
            if new_press:
                self.up_time = now
            if self.jump_step is None:             # on the ground: a normal jump
                self.jump_step = 0
                self.air_jumps = 0
            elif new_press and self.air_jumps < 1:  # in the air: one double jump
                self.jump_step = 0
                self.air_jumps = 1
                self.spawn_dust(self.creature_x + 30)   # double-jump puff at his feet
            return
        dx = {"Left": -1, "Right": 1}.get(key, 0)
        if dx == 0:
            return
        if new_press:
            prev = self.last_press.get(key)
            if prev is not None and DOUBLE_TAP_MIN <= now - prev <= DOUBLE_TAP_MAX:
                # Double-tap: dash. Diagonal if Up is held or was pressed just before.
                diagonal = "Up" in self.keys_down or now - self.up_time <= DOUBLE_TAP_MAX
                self.start_dash(dx, diagonal)
                self.last_press[key] = None       # a third tap starts over, it does not dash again
                return
            self.last_press[key] = now
        # Holding a key starts a walk; repeated key events from holding do not restart it
        if not self.steer_held or self.steer_dir != dx:
            self.steer_held = True
            self.steer_dir = dx
            self.steer_since = time.time()
            self.steer_px = 6.0
        self.steer_tail = 0
        self.walk_left = 0                  # the key takes over from any random walk in progress
        self.steer_frames = 8               # legs keep moving while the walk lasts

    def step_walk(self):
        """Start a walk trip now and then, and move the creature one step along it."""
        if self.walk_left == 0 and self.anim_frame >= self.next_walk:
            # Walk out and back on the same spot. Pick a side where there is room.
            span = WALK_HALF * WALK_PX
            options = [d for d in (1, -1)
                       if WALK_MIN_X <= self.creature_x + d * span <= WALK_MAX_X]
            self.walk_dir = random.choice(options)
            self.walk_x0 = self.creature_x
            self.walk_left = 2 * WALK_HALF
            self.next_walk = self.anim_frame + random.randint(80, 160)
        if self.walk_left > 0:
            outbound = self.walk_left > WALK_HALF
            move = self.walk_dir if outbound else -self.walk_dir
            self.facing = move
            self.creature_x += move * WALK_PX
            self.walk_left -= 1
            if self.walk_left == 0:
                self.creature_x = self.walk_x0      # back exactly where the trip started

    # ---- dash and effects -------------------------------------------------

    def start_dash(self, dx, diagonal):
        """Start a short, fast dash to the left (dx = -1) or right (dx = 1)."""
        self.dash_left = len(DASH_STEPS)
        self.dash_dir = dx
        self.dash_diag = diagonal
        if diagonal:
            self.jump_step = None           # the diagonal arc replaces the plain jump
        self.facing = dx
        self.steer_held = False             # the dash replaces walking
        self.steer_tail = 0
        self.steer_frames = 0
        self.walk_left = 0
        self.spawn_dash_fx(dx)

    def step_dash(self):
        """Move the creature one frame along the dash; land (with dust) at the end."""
        i = len(DASH_STEPS) - self.dash_left
        x = self.creature_x + self.dash_dir * DASH_STEPS[i]
        self.creature_x = self.wrap_x(x)     # walks off one side and back in on the other
        self.dash_lift = DASH_LIFT[i] if self.dash_diag else 0
        self.dash_left -= 1
        if self.dash_left == 0:
            self.dash_lift = 0
            self.spawn_dust(self.creature_x + 30)

    def spawn_dash_fx(self, dx):
        """Dust puffs and motion lines behind the creature at the start of a dash."""
        floor = self.creature_y + 10 * CREATURE_PX
        back = self.creature_x + 30 - dx * 30            # the side he is leaving
        for _ in range(10):
            self.fx.append({"kind": "dot", "x": back + random.uniform(-6, 6),
                            "y": floor - random.uniform(0, 14),
                            "vx": -dx * random.uniform(0.5, 2.5), "vy": random.uniform(-1.5, 0.2),
                            "life": FX_TICKS, "color": random.choice(("bar_current", "text")),
                            "dx": dx})
        for k in range(3):
            self.fx.append({"kind": "line", "x": back, "y": self.creature_y + 12 + 10 * k,
                            "vx": -dx * 2.5, "vy": 0.0, "life": FX_TICKS, "color": "text", "dx": dx})

    def spawn_dust(self, cx):
        """A small puff of dust on the floor, for a landing."""
        floor = self.creature_y + 10 * CREATURE_PX
        for _ in range(6):
            self.fx.append({"kind": "dot", "x": cx + random.uniform(-20, 20), "y": floor - 2,
                            "vx": random.uniform(-1.5, 1.5), "vy": random.uniform(-2.0, -0.5),
                            "life": FX_TICKS, "color": "text", "dx": 1})

    def step_fx(self):
        """Move the effects; drop each one once it has faded (about 0.5 s)."""
        for p in self.fx:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += 0.25                  # dust settles back down
            p["life"] -= 1
        self.fx = [p for p in self.fx if p["life"] > 0]

    def draw_fx(self):
        """Draw the effects on their own canvas tag; they fade toward the background."""
        c = self.canvas
        c.delete("fx")
        bg = self.c("bg")
        for p in self.fx:
            t = p["life"] / FX_TICKS                       # 1 = fresh, near 0 = almost gone
            if p["kind"] == "line":
                col = mix_colors(self.c("text"), bg, 0.5 * t)
                c.create_line(p["x"], p["y"], p["x"] - p["dx"] * 14, p["y"],
                              fill=col, width=2, tags="fx")
            else:
                col = mix_colors(self.c(p["color"]), bg, t)
                c.create_rectangle(p["x"], p["y"], p["x"] + 3, p["y"] + 3,
                                   fill=col, outline="", tags="fx")

    def animate(self):
        """Runs about 8 times a second: draw the creature, then step to the next frame."""
        if self.is_compact():                 # Compact mode: no animation, just keep the timer going
            self.root.after(ANIM_MS, self.animate)
            return
        before = self.creature_x
        self.step_home()
        if self.dash_left > 0:
            self.step_dash()
        else:
            self.step_steer()
        self.creature_x = self.resolve_x(before, self.creature_x)
        if self.steer_frames > 0:
            self.steer_frames -= 1
            self.walk_phase += self.steer_speed()   # legs cycle faster the more often you steer
        self.step_fx()
        self.step_moon()
        self.step_scene()
        self.draw_creature()
        self.draw_fx()
        self.anim_frame += 1
        if self.jump_step is not None:
            self.jump_step += 1
            if self.jump_step >= len(JUMP_PX):
                self.jump_step = None
                self.air_jumps = 0
                self.spawn_dust(self.creature_x + 30)   # landing puff
        elif self.dash_left == 0:
            before = self.creature_x
            self.step_walk()
            self.creature_x = self.resolve_x(before, self.creature_x)
        self.root.after(ANIM_MS, self.animate)

    def set_hover(self, over):
        if over != self.hovering:
            self.hovering = over
            self.canvas.configure(cursor="hand2" if over else "")
            self.draw_creature()

    def on_motion(self, event):
        self.set_hover(self.hit_action(event.x, event.y) == "creature")

    def on_leave(self, event):
        self.set_hover(False)

    def on_press(self, event):
        self.last_input = time.time()
        if self._menu_open:                     # while the menu is open, presses go to the menu
            self.on_click(event)
            return
        if self.hit_action(event.x, event.y) == "creature":
            # Remember where the press started so the window can follow the mouse.
            self.drag = {"x": event.x_root, "y": event.y_root,
                         "wx": self.root.winfo_x(), "wy": self.root.winfo_y(), "moved": False}
        else:
            self.on_click(event)

    def on_drag(self, event):
        self.last_input = time.time()
        d = self.drag
        if d is None:
            return
        dx, dy = event.x_root - d["x"], event.y_root - d["y"]
        if abs(dx) > 3 or abs(dy) > 3:      # small wobbles still count as a click
            d["moved"] = True
        if d["moved"]:
            self.root.geometry("+%d+%d" % (d["wx"] + dx, d["wy"] + dy))

    def on_release(self, event):
        d, self.drag = self.drag, None
        if d is not None and not d["moved"]:
            self.on_click(event)            # press and release without moving = a click

    def on_click(self, event):
        if self._menu_open:                 # a click while the menu is open picks a row or closes it
            command = None
            for x1, y1, x2, y2, cmd in self.menu_hits:
                if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                    command = cmd
            self.close_menu()
            if command is not None:
                command()
            return
        action = self.hit_action(event.x, event.y)
        if action == "refresh":
            self.refresh()
        elif action == "menu":
            self.open_menu(event.x_root, event.y_root)
        elif action == "creature":
            self.creature_click()

    def on_right_click(self, event):
        if self._menu_open:
            self.close_menu()
            return
        if self.hit_action(event.x, event.y) == "creature":
            self.open_menu(event.x_root, event.y_root)

    def hit_action(self, x, y):
        for x1, y1, x2, y2, action in self.hits:
            if action == "creature":                # the creature moves, so use its live position
                x1, x2 = self.creature_x, self.creature_x + 15 * CREATURE_PX
            if x1 <= x <= x2 and y1 <= y <= y2:
                return action
        return None

    def creature_click(self):
        """A click on the creature: a short jump, then fetch the usage now."""
        if self.jump_step is None:
            self.jump_step = 0
        self.refresh()

    def open_menu(self, x, y):
        """The three-dot dropdown, drawn inside the window. Clicking again closes it."""
        if self._menu_open:
            self.close_menu()
        else:
            self._menu_open = True
            self.apply_geometry()
            self.redraw()

    def menu_entries(self):
        """Dropdown rows as (label, checked, command). None is a separator."""
        current = self.settings["preset"]
        rows = [(name.capitalize(), name == current, lambda n=name: self.set_preset(n))
                for name in PRESETS]
        rows += [
            None,
            ("Compact", self.settings.get("compact", False), self.toggle_compact),
            None,
            ("Exit", False, self.root.destroy),
        ]
        return rows

    def draw_menu(self, w):
        """Draw the dropdown over the top-right part of the window."""
        c = self.canvas
        colors = self.settings["colors"]
        row_h, sep_h = 20, 9
        x2, x1 = w - 12, w - 12 - 172
        y = 44
        entries = self.menu_entries()
        total = 10 + sum(sep_h if e is None else row_h for e in entries)
        round_rect(c, x1, y, x2, y + total, 14, fill=colors["card"], outline=colors["track"], width=1)
        y += 5
        self.menu_hits = []
        for e in entries:
            if e is None:
                c.create_line(x1 + 10, y + sep_h / 2, x2 - 10, y + sep_h / 2, fill=colors["track"])
                y += sep_h
                continue
            label, checked, command = e
            if label == "Compact":                           # an on/off switch
                c.create_text(x1 + 12, y + row_h / 2, anchor="w", text=label,
                              font=(FONT, 9), fill=colors["text"])
                sx1, sx2 = x2 - 44, x2 - 14                 # a 30 x 16 px switch
                track_col = colors["bar_current"] if checked else colors["track"]
                c.create_oval(sx1, y + 2, sx1 + 16, y + row_h - 2, fill=track_col, outline="")     # round ends
                c.create_oval(sx2 - 16, y + 2, sx2, y + row_h - 2, fill=track_col, outline="")
                c.create_rectangle(sx1 + 8, y + 2, sx2 - 8, y + row_h - 2, fill=track_col, outline="")
                kx = sx2 - 8 if checked else sx1 + 8       # knob sits inside the track, with space around it
                c.create_oval(kx - 6, y + row_h / 2 - 6, kx + 6, y + row_h / 2 + 6,
                              fill="#FFFFFF", outline="")
            else:
                preset = PRESETS.get(label.lower())          # each mode row shows a colour of its own
                fg = colors["text"]
                if preset is not None:
                    if label.lower() == "light":
                        chip = "#9A9CA6"                     # the light mode is shown as grey
                    elif label.lower() == "dark":
                        chip = "#3A3D44"                     # the dark mode is shown as dark grey
                    elif label.lower() == "moon":
                        chip = "#2E1F4F"                     # the moon mode is a darker purple
                    else:
                        chip = mix_colors(preset["bg"], preset["bar_current"], 0.65)   # vibrant, from the mode's bar colour
                    round_rect(c, x1 + 6, y + 2, x2 - 6, y + row_h - 2, 8, fill=chip, outline="")   # rounded chip
                    fg = readable_text(chip)
                c.create_text(x1 + 12, y + row_h / 2, anchor="w",
                              text=("✓  " if checked else "    ") + label,
                              font=(FONT, 9), fill=fg)
            self.menu_hits.append((x1, y, x2, y + row_h, command))
            y += row_h

    def close_menu(self):
        if self._menu_open:
            self._menu_open = False
            self.apply_geometry()
            self.redraw()

    def set_preset(self, name):
        self.settings["preset"] = name
        self.settings["colors"] = dict(PRESETS[name])
        self.save_and_redraw()


def main():
    if os.name == "nt":
        # Give this app its own taskbar identity. Without it, Windows groups the
        # window with pythonw.exe and shows Python's icon instead of ours.
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("UsageWindow.ClaudeUsage")
        except Exception:
            pass
    root = tk.Tk()
    UsageApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
