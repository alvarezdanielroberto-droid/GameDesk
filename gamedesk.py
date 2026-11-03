"""
GameDesk v3 - Game covers on your Windows 11 desktop.

- Collapsed: shows the .exe icon (or your own small image) at half size.
- On hover: it expands with a short animation and shows the large image.
- Click                  -> launches the game
- Hold click and drag    -> moves the cover
- Right-click            -> images, executable, name, arrange, sizes...
- "+" button             -> add a game
"""
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
import ctypes
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageTk

try:
    import winreg
except ImportError:  # only so the script can be tested outside Windows
    winreg = None

APP = "GameDesk"
DATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP)
IMG_DIR = os.path.join(DATA, "images")
CFG = os.path.join(DATA, "config.json")
KEY = "#010101"  # transparent color (clicks pass through it)
ADD_SIZE = 72
DRAG_THRESHOLD = 6  # pixels of movement before it counts as a drag, not a click
STEPS = 7  # animation frames
FRAME_MS = 14  # ms between frames (total animation ~0.15 s)
IMG_TYPES = [("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.ico"), ("All files", "*.*")]
GAME_TYPES = [("Games / shortcuts", "*.exe *.lnk *.url *.bat"), ("All files", "*.*")]
LAYOUTS = {"top": "Top center", "center": "Screen center", "bottom": "Bottom center"}
SIZES = (("Small (220 px)", 220), ("Medium (340 px)", 340), ("Large (510 px)", 510))
RATIOS = (("40 %", 0.4), ("50 % (half)", 0.5), ("60 %", 0.6))

DEFAULT_CFG = {"tile_w": 340, "ratio": 0.5, "gap": 16, "layout": "bottom", "games": [], "add": None}


# ---------------------------------------------------------------- configuration
def load_cfg():
    try:
        with open(CFG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    for k, v in DEFAULT_CFG.items():
        cfg.setdefault(k, v if k != "games" else [])
    if cfg["tile_w"] < 200:  # sizes from earlier versions
        cfg["tile_w"] = 340
    return cfg


def save_cfg(cfg):
    os.makedirs(DATA, exist_ok=True)
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- images
def rounded_mask(size, radius):
    w, h = size
    s = 4
    m = Image.new("L", (w * s, h * s), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * s - 1, h * s - 1), radius * s, fill=255)
    return m.resize((w, h), Image.LANCZOS)


def rounded(img, radius):
    out = img.convert("RGBA")
    out.putalpha(rounded_mask(out.size, radius))
    return out


def get_font(size):
    for name in ("segoeuib.ttf", "segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def placeholder(text, w, h, font_div=8):
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):  # vertical gradient
        t = y / max(h - 1, 1)
        px.line([(0, y), (w, y)], fill=(int(40 + 30 * t), int(30 + 20 * t), int(80 + 60 * t)))
    font = get_font(max(14, w // font_div))
    lines, cur = [], ""
    for wd in text.split():
        test = (cur + " " + wd).strip()
        if px.textlength(test, font=font) <= w - 20:
            cur = test
        else:
            lines.append(cur)
            cur = wd
    lines.append(cur)
    lh = font.size + 4
    y0 = (h - lh * len(lines)) // 2
    for i, ln in enumerate(lines):
        tw = px.textlength(ln, font=font)
        px.text(((w - tw) / 2, y0 + i * lh), ln, fill=(255, 255, 255), font=font)
    return img


def cover(path, w, h):
    img = Image.open(path).convert("RGB")
    return ImageOps.fit(img, (w, h), Image.LANCZOS, centering=(0.5, 0.5))  # crop to 9:16


def build_big(path, name, w, h):
    """Large image (the one shown on hover)."""
    img = None
    if path and os.path.exists(path):
        try:
            img = cover(path, w, h)
        except Exception:
            img = None
    if img is None:
        img = placeholder(name, w, h)
    return rounded(img, max(10, int(w * 0.1)))


def build_small(small_path, icon_path, name, w, h):
    """Small image: your own if set; otherwise the exe icon over a blurred background."""
    img = None
    if small_path and os.path.exists(small_path):
        try:
            img = cover(small_path, w, h)
        except Exception:
            img = None
    if img is None and icon_path and os.path.exists(icon_path):
        try:
            icon = Image.open(icon_path).convert("RGBA")
            bg = ImageOps.fit(icon.convert("RGB"), (w, h), Image.BILINEAR)
            bg = bg.filter(ImageFilter.GaussianBlur(max(6, w // 6)))
            bg = ImageEnhance.Brightness(bg).enhance(0.5)
            side = int(w * 0.72)
            ic = ImageOps.contain(icon, (side, side), Image.LANCZOS)
            bg.paste(ic, ((w - ic.width) // 2, (h - ic.height) // 2), ic)
            img = bg
        except Exception:
            img = None
    if img is None:
        img = placeholder((name[:1] or "?").upper(), w, h, font_div=2)
    return rounded(img, max(8, int(w * 0.1)))


def smoothstep(t):
    return t * t * (3 - 2 * t)


def make_frame(small, big, k):
    """Intermediate frame: scales from small to large and cross-fades the two images."""
    e = smoothstep(k / STEPS)
    sw, _ = small.size
    bw, _ = big.size
    fw = round(sw + (bw - sw) * e)
    fh = round(fw * 16 / 9)
    a = max(0.0, min(1.0, (e - 0.15) / 0.6))
    s = small.resize((fw, fh), Image.BILINEAR)
    b = big.resize((fw, fh), Image.BILINEAR)
    return Image.blend(s, b, a)


def build_add_tile(size):
    radius = size // 3
    img = Image.new("RGBA", (size, size), (30, 30, 36, 190))
    d = ImageDraw.Draw(img)
    c, L = size // 2, size // 5
    d.line([(c - L, c), (c + L, c)], fill=(255, 255, 255, 230), width=5)
    d.line([(c, c - L), (c, c + L)], fill=(255, 255, 255, 230), width=5)
    mask = rounded_mask((size, size), radius)
    img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", (size, size), 0), mask))
    hov = img.copy()
    ImageDraw.Draw(hov).rounded_rectangle((1, 1, size - 2, size - 2), radius, outline=(255, 255, 255, 240), width=3)
    return img, hov


def extract_icon(exe):
    """Extract the largest icon from the .exe and save it as PNG. Returns the file name, or ''."""
    try:
        from icoextract import IconExtractor
    except Exception:
        return ""
    try:
        data = IconExtractor(exe).get_icon()
        im = Image.open(data)
        try:
            im.size = max(im.info["sizes"])  # largest available size
        except Exception:
            pass
        im = im.convert("RGBA")
        name = "icon_" + uuid.uuid4().hex + ".png"
        im.save(os.path.join(IMG_DIR, name))
        return name
    except Exception:
        return ""


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def modal(fn):
    """While a dialog is open the panel is not sent to the back (otherwise the dialog would sink behind other windows)."""

    def wrapper(self, *a, **k):
        self.busy = True
        try:
            return fn(self, *a, **k)
        finally:
            self.busy = False
            self._sink()

    return wrapper


class Tile:
    def __init__(self, idx, small, big):
        self.idx = idx
        self.small, self.big = small, big
        self.sw, self.sh = small.size
        self.k = 0  # current frame (0 = small, STEPS = large)
        self.target = 0
        self.job = None
        self.pos = (0, 0)  # top-left corner of the small box
        self.item = None
        self.frames = {}  # k -> (PhotoImage, width, height)


class GameDesk:
    def __init__(self):
        os.makedirs(IMG_DIR, exist_ok=True)
        self.cfg = load_cfg()
        self.busy = False
        self.press = None
        self.tiles = []
        self.items = {}
        self.photos = []

        self.root = tk.Tk()
        self.root.title(APP)
        self.sw, self.sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.overrideredirect(True)
        self.root.configure(bg=KEY)
        self.root.attributes("-transparentcolor", KEY)
        self.root.geometry(f"{self.sw}x{self.sh}+0+0")
        self.canvas = tk.Canvas(self.root, bg=KEY, highlightthickness=0, bd=0, width=self.sw, height=self.sh)
        self.canvas.pack(fill="both", expand=True)

        self.autostart_var = tk.BooleanVar(value=self.autostart_enabled())
        self.render()
        self.root.after(300, self._loop)
        self.root.mainloop()

    # ---------- sizes and positions ----------
    def big_size(self):
        w = int(self.cfg["tile_w"])
        return w, round(w * 16 / 9)

    def small_size(self):
        w = max(40, round(self.cfg["tile_w"] * float(self.cfg["ratio"])))
        return w, round(w * 16 / 9)

    def clamp(self, x, y, w, h):
        return (max(0, min(int(x), max(0, self.sw - w))), max(0, min(int(y), max(0, self.sh - h))))

    def work_area(self):
        """Usable screen area (without the taskbar)."""
        try:
            r = RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
            if r.right > r.left and r.bottom > r.top:
                return r.left, r.top, r.right, r.bottom
        except Exception:
            pass
        return 0, 0, self.sw, self.sh

    def compute_layout(self, mode, sw, sh):
        """Place the covers in aligned, centered rows (top / center / bottom)."""
        games = self.cfg["games"]
        if not games:
            return
        L, T, R, B = self.work_area()
        gap, m = int(self.cfg["gap"]), 16
        cols = max(1, (R - L - 2 * m + gap) // (sw + gap))
        rows = [games[i : i + cols] for i in range(0, len(games), cols)]
        total_h = len(rows) * sh + (len(rows) - 1) * gap
        if mode == "top":
            y0 = T + m
        elif mode == "bottom":
            y0 = B - m - total_h
        else:
            y0 = T + (B - T - total_h) // 2
        for r, row in enumerate(rows):
            row_w = len(row) * sw + (len(row) - 1) * gap
            x0 = L + (R - L - row_w) // 2
            for c, g in enumerate(row):
                g["x"], g["y"] = x0 + c * (sw + gap), y0 + r * (sh + gap)

    def default_positions(self, sw, sh):
        """Free mode: initial position for covers that do not have one yet."""
        gap, x0, y0 = int(self.cfg["gap"]), 160, 60
        cols = max(1, (self.sw - x0 - gap) // (sw + gap))
        for i, g in enumerate(self.cfg["games"]):
            if "x" not in g or "y" not in g:
                r, c = divmod(i, cols)
                g["x"], g["y"] = x0 + c * (sw + gap), y0 + r * (sh + gap)

    def anchor(self):
        """Direction in which the cover grows when it expands."""
        return {"top": "top", "bottom": "bottom"}.get(self.cfg["layout"], "center")

    # ---------- drawing ----------
    def img_path(self, name):
        return os.path.join(IMG_DIR, name) if name else None

    def render(self):
        for t in self.tiles:
            if t.job:
                self.root.after_cancel(t.job)
        self.canvas.delete("all")
        self.tiles, self.items, self.photos = [], {}, []
        W, H = self.big_size()
        sw, sh = self.small_size()
        layout = self.cfg["layout"]
        if layout in LAYOUTS:
            self.compute_layout(layout, sw, sh)
        else:
            self.default_positions(sw, sh)

        changed = False
        for idx, g in enumerate(self.cfg["games"]):
            if "icon" not in g:
                g["icon"] = extract_icon(g.get("exe", ""))
                changed = True
            big = build_big(self.img_path(g.get("image")), g["name"], W, H)
            small = build_small(self.img_path(g.get("small")), self.img_path(g.get("icon")), g["name"], sw, sh)
            tile = Tile(idx, small, big)
            x, y = self.clamp(g["x"], g["y"], sw, sh)
            g["x"], g["y"] = x, y
            tile.pos = (x, y)
            p0 = ImageTk.PhotoImage(small)
            tile.frames[0] = (p0, sw, sh)
            tile.item = self.canvas.create_image(x, y, image=p0, anchor="nw")
            self.items[tile.item] = {"kind": "game", "idx": idx, "tile": tile}
            self._bind(tile.item)
            self.tiles.append(tile)

        a = self.cfg["add"] or {"x": self.sw - ADD_SIZE - 40, "y": 40}
        ax, ay = self.clamp(a["x"], a["y"], ADD_SIZE, ADD_SIZE)
        self.cfg["add"] = {"x": ax, "y": ay}
        n, h = build_add_tile(ADD_SIZE)
        pn, ph = ImageTk.PhotoImage(n), ImageTk.PhotoImage(h)
        self.photos += [pn, ph]
        item = self.canvas.create_image(ax, ay, image=pn, anchor="nw")
        self.items[item] = {"kind": "add", "normal": pn, "hover": ph, "w": ADD_SIZE, "h": ADD_SIZE}
        self._bind(item)
        if changed:
            save_cfg(self.cfg)

    def _bind(self, item):
        c = self.canvas
        c.tag_bind(item, "<Enter>", lambda e, i=item: self.on_enter(i))
        c.tag_bind(item, "<Leave>", lambda e, i=item: self.on_leave(i))
        c.tag_bind(item, "<ButtonPress-1>", lambda e, i=item: self.on_press(e, i))
        c.tag_bind(item, "<B1-Motion>", lambda e, i=item: self.on_motion(e, i))
        c.tag_bind(item, "<ButtonRelease-1>", lambda e, i=item: self.on_release(e, i))
        c.tag_bind(item, "<Button-3>", lambda e, i=item: self.show_menu(e, i))

    # ---------- animation ----------
    def _frame(self, tile, k):
        f = tile.frames.get(k)
        if f:
            return f
        img = tile.big if k >= STEPS else make_frame(tile.small, tile.big, k)
        f = (ImageTk.PhotoImage(img), img.width, img.height)
        tile.frames[k] = f
        return f

    def _apply(self, tile):
        photo, fw, fh = self._frame(tile, tile.k)
        px, py = tile.pos
        x = px + (tile.sw - fw) / 2
        anchor = self.anchor()
        if anchor == "top":
            y = py
        elif anchor == "bottom":
            y = py + tile.sh - fh
        else:
            y = py + (tile.sh - fh) / 2
        x = max(0, min(x, self.sw - fw))
        y = max(0, min(y, self.sh - fh))
        self.canvas.itemconfig(tile.item, image=photo)
        self.canvas.coords(tile.item, x, y)

    def _kick(self, tile):
        if tile.job is None:
            tile.job = self.root.after(1, lambda: self._step(tile))

    def _step(self, tile):
        tile.job = None
        if tile.k < tile.target:
            tile.k += 1
        elif tile.k > tile.target:
            tile.k -= 1
        self._apply(tile)
        if tile.k != tile.target:
            tile.job = self.root.after(FRAME_MS, lambda: self._step(tile))

    def on_enter(self, item):
        info = self.items.get(item)
        if not info:
            return
        if info["kind"] == "add":
            self.canvas.itemconfig(item, image=info["hover"])
            return
        self.canvas.tag_raise(item)
        info["tile"].target = STEPS
        self._kick(info["tile"])

    def on_leave(self, item):
        info = self.items.get(item)
        if not info:
            return
        if info["kind"] == "add":
            self.canvas.itemconfig(item, image=info["normal"])
            return
        info["tile"].target = 0
        self._kick(info["tile"])

    # ---------- keep the panel at the back ----------
    def _sink(self):
        """Put the window below all others, as if it were part of the desktop."""
        try:
            u = ctypes.windll.user32
            u.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p] + [ctypes.c_int] * 5
            hwnd = u.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            # HWND_BOTTOM=1 | SWP_NOSIZE=1 | SWP_NOMOVE=2 | SWP_NOACTIVATE=0x10
            u.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    def _loop(self):
        if not self.busy:
            self._sink()
        self.root.after(1000, self._loop)

    # ---------- click and drag ----------
    def on_press(self, e, item):
        info = self.items[item]
        if info["kind"] == "game":
            ox, oy = info["tile"].pos
        else:
            ox, oy = self.canvas.coords(item)
        self.press = {"item": item, "sx": e.x_root, "sy": e.y_root, "ox": ox, "oy": oy, "moved": False}

    def on_motion(self, e, item):
        p = self.press
        if not p or p["item"] != item:
            return
        dx, dy = e.x_root - p["sx"], e.y_root - p["sy"]
        if not p["moved"]:
            if math.hypot(dx, dy) < DRAG_THRESHOLD:
                return
            p["moved"] = True
            self.canvas.tag_raise(item)
            self.canvas.config(cursor="fleur")
        info = self.items[item]
        if info["kind"] == "game":
            t = info["tile"]
            t.pos = self.clamp(p["ox"] + dx, p["oy"] + dy, t.sw, t.sh)
            self._apply(t)
        else:
            nx, ny = self.clamp(p["ox"] + dx, p["oy"] + dy, info["w"], info["h"])
            self.canvas.coords(item, nx, ny)

    def on_release(self, e, item):
        p, self.press = self.press, None
        self.canvas.config(cursor="")
        if not p or p["item"] != item:
            return
        info = self.items[item]
        if p["moved"]:
            if info["kind"] == "game":
                g = self.cfg["games"][info["idx"]]
                g["x"], g["y"] = info["tile"].pos
                self.cfg["layout"] = "free"  # moving by hand switches the layout to free
            else:
                x, y = self.canvas.coords(item)
                self.cfg["add"] = {"x": int(x), "y": int(y)}
            save_cfg(self.cfg)
        elif info["kind"] == "add":
            self.add_game()
        else:
            self.launch(self.cfg["games"][info["idx"]])
        # if the pointer is no longer over it on release, shrink back
        bbox = self.canvas.bbox(item)
        if info["kind"] == "game" and bbox and not (bbox[0] <= e.x <= bbox[2] and bbox[1] <= e.y <= bbox[3]):
            info["tile"].target = 0
            self._kick(info["tile"])
        self._sink()

    # ---------- menu ----------
    def show_menu(self, e, item):
        info = self.items[item]
        m = tk.Menu(self.root, tearoff=0)
        if info["kind"] == "game":
            idx = info["idx"]
            m.add_command(label="Change large image…", command=lambda: self.change_big(idx))
            m.add_command(label="Change small image…", command=lambda: self.change_small(idx))
            m.add_command(label="Use the exe icon as the small image", command=lambda: self.reset_small(idx))
            m.add_command(label="Change executable…", command=lambda: self.change_exe(idx))
            m.add_command(label="Rename…", command=lambda: self.rename(idx))
            m.add_command(label="Remove from desktop", command=lambda: self.remove(idx))
            m.add_separator()
        m.add_command(label="Add game…", command=self.add_game)
        org = tk.Menu(m, tearoff=0)
        for mode, label in LAYOUTS.items():
            org.add_command(label=label, command=lambda md=mode: self.set_layout(md))
        m.add_cascade(label="Arrange", menu=org)
        sizes = tk.Menu(m, tearoff=0)
        for label, val in SIZES:
            sizes.add_command(label=label, command=lambda v=val: self.set_size(v))
        m.add_cascade(label="Size when expanded", menu=sizes)
        ratios = tk.Menu(m, tearoff=0)
        for label, val in RATIOS:
            ratios.add_command(label=label, command=lambda v=val: self.set_ratio(v))
        m.add_cascade(label="Small size", menu=ratios)
        m.add_checkbutton(label="Start with Windows", variable=self.autostart_var, command=self.toggle_autostart)
        m.add_command(label="Move: hold click and drag", state="disabled")
        m.add_separator()
        m.add_command(label="Quit GameDesk", command=self.root.destroy)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # ---------- actions ----------
    def copy_image(self, src):
        ext = os.path.splitext(src)[1].lower() or ".png"
        name = uuid.uuid4().hex + ext
        shutil.copy(src, os.path.join(IMG_DIR, name))
        return name

    def _delete_img(self, name):
        if name:
            try:
                os.remove(os.path.join(IMG_DIR, name))
            except OSError:
                pass

    def launch(self, g):
        path = g.get("exe", "")
        if not os.path.exists(path):
            self._warn(path)
            return
        try:
            if path.lower().endswith(".exe"):
                subprocess.Popen([path], cwd=os.path.dirname(path))
            else:
                os.startfile(path)
        except OSError:
            try:  # in case it needs administrator rights
                os.startfile(path)
            except Exception as ex:
                self._error(ex)

    @modal
    def _warn(self, path):
        messagebox.showwarning(APP, f"File not found:\n{path}\n\nRight-click > Change executable.")

    @modal
    def _error(self, ex):
        messagebox.showerror(APP, f"Could not open the game:\n{ex}")

    @modal
    def add_game(self):
        exe = filedialog.askopenfilename(parent=self.root, title="Choose the game's executable", filetypes=GAME_TYPES)
        if not exe:
            return
        default = os.path.splitext(os.path.basename(exe))[0]
        name = simpledialog.askstring(APP, "Game name:", initialvalue=default, parent=self.root) or default
        img = filedialog.askopenfilename(
            parent=self.root,
            title="LARGE image (shown on hover). Cancel = generic",
            filetypes=IMG_TYPES,
        )
        self.cfg["games"].append(
            {
                "name": name,
                "exe": exe,
                "image": self.copy_image(img) if img else "",
                "small": "",  # empty = use the exe icon
                "icon": extract_icon(exe),
            }
        )
        save_cfg(self.cfg)
        self.render()

    @modal
    def change_big(self, idx):
        img = filedialog.askopenfilename(parent=self.root, title="New large image", filetypes=IMG_TYPES)
        if not img:
            return
        g = self.cfg["games"][idx]
        self._delete_img(g.get("image"))
        g["image"] = self.copy_image(img)
        save_cfg(self.cfg)
        self.render()

    @modal
    def change_small(self, idx):
        img = filedialog.askopenfilename(parent=self.root, title="New small image", filetypes=IMG_TYPES)
        if not img:
            return
        g = self.cfg["games"][idx]
        self._delete_img(g.get("small"))
        g["small"] = self.copy_image(img)
        save_cfg(self.cfg)
        self.render()

    def reset_small(self, idx):
        g = self.cfg["games"][idx]
        self._delete_img(g.get("small"))
        g["small"] = ""
        if not g.get("icon"):
            g["icon"] = extract_icon(g.get("exe", ""))
        save_cfg(self.cfg)
        self.render()

    @modal
    def change_exe(self, idx):
        exe = filedialog.askopenfilename(parent=self.root, title="New executable", filetypes=GAME_TYPES)
        if not exe:
            return
        g = self.cfg["games"][idx]
        g["exe"] = exe
        self._delete_img(g.get("icon"))
        g["icon"] = extract_icon(exe)  # the small icon updates with the new exe
        save_cfg(self.cfg)
        self.render()

    @modal
    def rename(self, idx):
        g = self.cfg["games"][idx]
        name = simpledialog.askstring(APP, "Name:", initialvalue=g["name"], parent=self.root)
        if name:
            g["name"] = name
            save_cfg(self.cfg)
            self.render()

    @modal
    def remove(self, idx):
        g = self.cfg["games"][idx]
        if messagebox.askyesno(APP, f"Remove '{g['name']}' from the desktop?\n(The game itself is not deleted)", parent=self.root):
            for k in ("image", "small", "icon"):
                self._delete_img(g.get(k))
            del self.cfg["games"][idx]
            save_cfg(self.cfg)
            self.render()

    def set_layout(self, mode):
        self.cfg["layout"] = mode
        save_cfg(self.cfg)
        self.render()

    def set_size(self, w):
        self.cfg["tile_w"] = w
        save_cfg(self.cfg)
        self.render()

    def set_ratio(self, r):
        self.cfg["ratio"] = r
        save_cfg(self.cfg)
        self.render()

    # ---------- start with Windows ----------
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def run_command(self):
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        pyw = sys.executable.replace("python.exe", "pythonw.exe")
        return f'"{pyw}" "{os.path.abspath(__file__)}"'

    def autostart_enabled(self):
        if not winreg:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as k:
                winreg.QueryValueEx(k, APP)
            return True
        except OSError:
            return False

    def toggle_autostart(self):
        if not winreg:
            return
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if self.autostart_var.get():
                winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, self.run_command())
            else:
                try:
                    winreg.DeleteValue(k, APP)
                except OSError:
                    pass


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    GameDesk()
