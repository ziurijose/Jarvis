"""The listening HUD's look: a particle orb with the assistant's name and a status pill,
in the same visual language as the setup window (ui/setup.html).

OrbRenderer draws each frame as an RGBA image with numpy (no artwork files needed).
LayeredWindow shows those frames on Windows with true per-pixel transparency, so the
soft halo and glow blend over whatever is on screen.
"""
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

VOID = (15, 17, 19)
TEXT = (247, 247, 248)
LIME = (209, 254, 23)
POINTS = 900

# Orb behaviour per status: how lively it is, how fast it spins, how strongly it ripples.
MOODS = {
    'LISTENING': {'energy': 0.35, 'spin': 0.35, 'ripple': 0.0},
    'RECOGNIZING': {'energy': 0.75, 'spin': 1.1, 'ripple': 0.0},
    'ASKING CLAUDE': {'energy': 0.6, 'spin': 0.6, 'ripple': 0.8},
    'THINKING': {'energy': 0.6, 'spin': 0.8, 'ripple': 0.8},
    'SPEAKING': {'energy': 0.55, 'spin': 0.45, 'ripple': 0.5},
}
DEFAULT_MOOD = {'energy': 0.5, 'spin': 0.5, 'ripple': 0.3}


def _font(size_px: int, bold: bool = True):
    if sys.platform == 'win32':
        candidates = ['C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf']
    else:
        candidates = ['/System/Library/Fonts/Supplemental/Arial Bold.ttf' if bold else
                      '/System/Library/Fonts/Supplemental/Arial.ttf',
                      '/System/Library/Fonts/Helvetica.ttc']
    for path in candidates:
        try:
            return ImageFont.truetype(path, size_px)
        except OSError:
            continue
    return ImageFont.load_default(size_px)


def _ease(current: float, target: float, dt: float, speed: float = 5.0) -> float:
    """Frame-rate independent glide toward target (exponential smoothing)."""
    return current + (target - current) * (1 - math.exp(-dt * speed))


class OrbRenderer:
    def __init__(self, size: int, title: str):
        self.size = size
        self.title = title.upper()
        i = np.arange(POINTS)
        y = 1 - (i / (POINTS - 1)) * 2           # Fibonacci sphere: even coverage
        r = np.sqrt(1 - y * y)
        theta = i * 2.399963
        self.base = np.stack([np.cos(theta) * r, y, np.sin(theta) * r], axis=1)
        rng = np.random.default_rng(7)
        self.seed = rng.uniform(0, 2 * math.pi, POINTS)
        self.lime = rng.uniform(0, 1, POINTS) < 0.12
        self.mood = dict(DEFAULT_MOOD)
        self.rotation = 0.0
        self.time = 0.0
        self.appear = 0.0          # 0 hidden .. 1 fully shown (drives fade + scale)
        self.appear_target = 0.0
        self.status = ''
        self.title_font = _font(max(16, min(26, int(300 / max(len(self.title), 1)))))
        self.status_font = _font(15)
        self.caption = ''
        self.caption_font = _font(16, bold=False)
        self.halo = self._make_halo()

    def _make_halo(self) -> Image.Image:
        """Dark radial backdrop: readable over any desktop, fading to fully transparent."""
        s = self.size
        yy, xx = np.mgrid[0:s, 0:s]
        d = np.hypot(xx - s / 2, yy - s * 0.52) / (s / 2)
        # Solid behind the orb and the name, then a smooth fade to nothing at the rim.
        t = np.clip((d - 0.68) / 0.32, 0, 1)
        alpha = (1 - t * t * (3 - 2 * t)) * 238
        halo = np.zeros((s, s, 4), np.uint8)
        halo[..., :3] = VOID
        halo[..., 3] = alpha.astype(np.uint8)
        return Image.fromarray(halo, 'RGBA')

    def set_status(self, status: str) -> None:
        self.status = status
        self.appear_target = 1.0

    def set_caption(self, text: str) -> None:
        """What was heard or is being said; shown in place of the name."""
        self.caption = ' '.join(text.split())

    def hide(self) -> None:
        self.appear_target = 0.0
        self.caption = ''

    @property
    def fully_hidden(self) -> bool:
        return self.appear_target == 0.0 and self.appear < 0.01

    def frame(self, dt: float) -> Image.Image:
        dt = min(dt, 0.1)
        self.time += dt
        goal = MOODS.get(self.status, DEFAULT_MOOD)
        for key in self.mood:
            self.mood[key] = _ease(self.mood[key], goal[key], dt, 3.0)
        self.appear = _ease(self.appear, self.appear_target, dt, 9.0)
        self.rotation += dt * (0.25 + self.mood['spin'])

        s = self.size
        image = self.halo.copy()
        points = self._draw_points(s)
        image.alpha_composite(points)
        self._draw_labels(image)

        if self.appear < 0.999:
            # Fade and grow in from 92%: the whole HUD eases on instead of popping.
            scale = 0.92 + 0.08 * self.appear
            if scale < 0.999:
                scaled = image.resize((round(s * scale),) * 2, Image.BILINEAR)
                image = Image.new('RGBA', (s, s), (0, 0, 0, 0))
                offset = (s - scaled.width) // 2
                image.alpha_composite(scaled, (offset, offset))
            alpha = np.asarray(image)[..., 3].astype(np.float32) * self.appear
            image.putalpha(Image.fromarray(alpha.astype(np.uint8)))
        return image

    def _draw_points(self, s: int) -> Image.Image:
        m, t = self.mood, self.time
        p = self.base
        cr, sr = math.cos(self.rotation), math.sin(self.rotation)
        x = p[:, 0] * cr - p[:, 2] * sr
        z = p[:, 0] * sr + p[:, 2] * cr
        tilt = 0.38
        y = p[:, 1] * math.cos(tilt) - z * math.sin(tilt)
        z = p[:, 1] * math.sin(tilt) + z * math.cos(tilt)
        wave = (np.sin(t * (1.2 + m['energy'] * 3) + p[:, 1] * 5 + self.seed) * (0.015 + m['energy'] * 0.05)
                + np.sin(t * 6 - (p[:, 1] + 1) * 6) * m['ripple'] * 0.06)
        radius = s * 0.24 * (1 + wave)
        cx, cy = s / 2, s * 0.42
        px = (cx + x * radius).astype(np.int32)
        py = (cy + y * radius).astype(np.int32)
        depth = (z + 1) / 2                      # 0 back .. 1 front

        layer = np.zeros((s, s, 4), np.float32)
        bright = self.lime & (depth > 0.62)
        colour = np.where(bright[:, None], np.array(LIME, np.float32), np.array(TEXT, np.float32))
        alpha = np.where(bright, 0.7 + depth * 0.3, 0.08 + depth * 0.62)
        size = np.where(depth > 0.55, 2, 1)
        for d in range(2):                       # front points are 2x2, back points 1x1
            for e in range(2):
                keep = (size > max(d, e)) & (px + d < s) & (py + e < s) & (px >= 0) & (py >= 0)
                xs, ys = px[keep] + d, py[keep] + e
                a = alpha[keep]
                layer[ys, xs, :3] = colour[keep]
                layer[ys, xs, 3] = np.maximum(layer[ys, xs, 3], a * 255)
        points = Image.fromarray(layer.astype(np.uint8), 'RGBA')

        # Glow: blur a small copy of the points and lay it underneath.
        small = points.resize((s // 4, s // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
        glow = small.resize((s, s), Image.BILINEAR)
        glow_arr = np.asarray(glow).astype(np.float32)
        glow_arr[..., :3] = LIME
        glow_arr[..., 3] = np.clip(glow_arr[..., 3] * (1.2 + m['energy']), 0, 255)
        out = Image.fromarray(glow_arr.astype(np.uint8), 'RGBA')
        out.alpha_composite(points)
        return out

    def _draw_labels(self, image: Image.Image) -> None:
        s = self.size
        draw = ImageDraw.Draw(image)
        if self.caption:
            lines = self._wrap(draw, self.caption, s - 60, 2)
            top = s * 0.76 - (len(lines) - 1) * 11
            for i, line in enumerate(lines):
                draw.text((s / 2, top + i * 22), line, font=self.caption_font, fill=TEXT + (235,), anchor='mm')
        else:
            draw.text((s / 2, s * 0.76), self.title, font=self.title_font, fill=TEXT + (255,), anchor='mm')
        # Status pill with a pulsing lime dot.
        label = {'ASKING CLAUDE': 'Asking Claude'}.get(self.status, self.status.capitalize())
        if not label:
            return
        text_w = draw.textlength(label, font=self.status_font)
        pill_w, pill_h = text_w + 46, 30
        x0, y0 = s / 2 - pill_w / 2, s * 0.84
        draw.rounded_rectangle((x0, y0, x0 + pill_w, y0 + pill_h), radius=15,
                               fill=(22, 25, 28, 235), outline=(38, 42, 47, 255))
        pulse = (math.sin(self.time * 4) + 1) / 2
        r = 3.5 + pulse * 1.2
        dot_x, dot_y = x0 + 17, y0 + pill_h / 2
        draw.ellipse((dot_x - r - 3, dot_y - r - 3, dot_x + r + 3, dot_y + r + 3),
                     fill=LIME + (int(40 + 50 * pulse),))
        draw.ellipse((dot_x - r, dot_y - r, dot_x + r, dot_y + r), fill=LIME + (255,))
        draw.text((x0 + 30, dot_y), label, font=self.status_font, fill=TEXT + (255,), anchor='lm')

    def _wrap(self, draw, text, width, max_lines):
        """Up to max_lines lines that fit width; a long caption keeps its end (the newest words)."""
        lines, line = [], ''
        for word in text.split():
            trial = (line + ' ' + word).strip()
            if draw.textlength(trial, font=self.caption_font) <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            lines[0] = '…' + lines[0]
        return lines


class LayeredWindow:
    """Shows RGBA frames in a Tk toplevel through Win32 UpdateLayeredWindow."""

    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020  # clicks pass through to the windows underneath
    WS_EX_TOOLWINDOW = 0x00000080   # no taskbar button
    WS_EX_TOPMOST = 0x00000008
    WS_EX_NOACTIVATE = 0x08000000   # never steals keyboard focus

    def __init__(self, root, size: int, x: int, y: int):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
        self.user32 = user32
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.GetDC.restype = wintypes.HDC
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT,
                                           ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE,
                                           wintypes.DWORD]
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG),
                        ('biHeight', wintypes.LONG), ('biPlanes', wintypes.WORD),
                        ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
                        ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
                        ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD),
                        ('biClrImportant', wintypes.DWORD)]

        class BLENDFUNCTION(ctypes.Structure):
            _fields_ = [('BlendOp', ctypes.c_ubyte), ('BlendFlags', ctypes.c_ubyte),
                        ('SourceConstantAlpha', ctypes.c_ubyte), ('AlphaFormat', ctypes.c_ubyte)]

        user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
            ctypes.POINTER(wintypes.SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
            wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]

        root.update_idletasks()
        self.hwnd = int(root.wm_frame(), 16)
        self.position = wintypes.POINT(x, y)
        self.extent = wintypes.SIZE(size, size)
        self.origin = wintypes.POINT(0, 0)
        self.blend = BLENDFUNCTION(0, 0, 255, 1)  # AC_SRC_OVER, per-pixel AC_SRC_ALPHA
        self.screen_dc = user32.GetDC(None)
        self.memory_dc = gdi32.CreateCompatibleDC(self.screen_dc)
        header = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), size, -size, 1, 32, 0,
                                  0, 0, 0, 0, 0)  # negative height = top-down rows
        self.bits = ctypes.c_void_p()
        bitmap = gdi32.CreateDIBSection(self.memory_dc, ctypes.byref(header), 0,
                                        ctypes.byref(self.bits), None, 0)
        gdi32.SelectObject(self.memory_dc, bitmap)
        self.apply_style()

    def apply_style(self) -> None:
        style = self.user32.GetWindowLongPtrW(self.hwnd, self.GWL_EXSTYLE)
        style |= (self.WS_EX_LAYERED | self.WS_EX_TRANSPARENT | self.WS_EX_TOOLWINDOW
                  | self.WS_EX_TOPMOST | self.WS_EX_NOACTIVATE)
        self.user32.SetWindowLongPtrW(self.hwnd, self.GWL_EXSTYLE, style)

    def present(self, frame: Image.Image) -> None:
        rgba = np.asarray(frame, dtype=np.uint16)
        alpha = rgba[..., 3:4]
        premultiplied = (rgba[..., :3] * alpha // 255).astype(np.uint8)  # Windows wants premultiplied BGRA
        bgra = np.concatenate([premultiplied[..., ::-1], alpha.astype(np.uint8)], axis=2)
        data = np.ascontiguousarray(bgra).tobytes()
        self.ctypes.memmove(self.bits, data, len(data))
        c = self.ctypes
        self.user32.UpdateLayeredWindow(self.hwnd, self.screen_dc, c.byref(self.position),
                                        c.byref(self.extent), self.memory_dc,
                                        c.byref(self.origin), 0, c.byref(self.blend), 2)
