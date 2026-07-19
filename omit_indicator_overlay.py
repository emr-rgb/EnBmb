#!/usr/bin/env python3
"""Transparent text overlay for enbmb slot indicator — no background box."""
import sys
import os
import json
import signal
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo
import cairo

STATE_FILE = sys.argv[1] if len(sys.argv) > 1 else '/tmp/enbmb-indicator-state.json'
DRAG_FILE  = sys.argv[2] if len(sys.argv) > 2 else '/tmp/enbmb-indicator-drag.json'


def _rgba(hex_color, alpha=1.0):
    h = hex_color.lstrip('#')
    r = int(h[0:2], 16) / 255
    g = int(h[2:4], 16) / 255
    b = int(h[4:6], 16) / 255
    return r, g, b, alpha


class IndicatorOverlay(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.connect('draw', self._on_draw)
        self.connect('realize', lambda w: w.input_shape_combine_region(cairo.Region()))

        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect('button-press-event',  self._on_press)
        self.connect('motion-notify-event', self._on_motion)
        self.connect('button-release-event', self._on_release)

        self._state      = {}
        self._last_mtime = 0
        self._drag_mode  = False
        self._drag_active = False
        self._drag_ox    = 0
        self._drag_oy    = 0
        self._draw_x     = 20
        self._draw_y     = 280

        # Fixed full-virtual-desktop window — never resized or moved
        sw = screen.get_width()
        sh = screen.get_height()
        self.resize(sw, sh)
        self.move(0, 0)

        GLib.timeout_add(150, self._poll)

    def _set_drag_mode(self, enabled):
        if enabled == self._drag_mode:
            return
        self._drag_mode = enabled
        if enabled:
            self._update_drag_region()
            win = self.get_window()
            if win:
                win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), 'grab'))
        else:
            self._drag_active = False
            self.input_shape_combine_region(cairo.Region())
            win = self.get_window()
            if win:
                win.set_cursor(None)

    def _update_drag_region(self):
        state = self._state
        text = state.get('text', '')
        font_size = max(8, int(state.get('font_size', 48)))
        if not text:
            return
        tw, th = self._get_text_size(text, font_size)
        pad = 12
        rect = cairo.RectangleInt(
            max(0, self._draw_x - pad),
            max(0, self._draw_y - pad),
            tw + 2 * pad,
            th + 2 * pad,
        )
        self.input_shape_combine_region(cairo.Region(rect))

    def _on_press(self, widget, event):
        if event.button == 1 and self._drag_mode:
            self._drag_active = True
            self._drag_ox = event.x_root - self._draw_x
            self._drag_oy = event.y_root - self._draw_y

    def _on_motion(self, widget, event):
        if self._drag_active:
            self._draw_x = int(event.x_root - self._drag_ox)
            self._draw_y = int(event.y_root - self._drag_oy)
            self._update_drag_region()
            self.queue_draw()

    def _on_release(self, widget, event):
        if event.button == 1 and self._drag_active:
            self._drag_active = False
            try:
                with open(DRAG_FILE, 'w') as f:
                    json.dump({"x": self._draw_x, "y": self._draw_y}, f)
            except Exception:
                pass

    def _make_layout(self, cr, text, font_size):
        layout = PangoCairo.create_layout(cr)
        layout.set_text(text, -1)
        fd = Pango.FontDescription(f"Courier New, monospace Bold {font_size}")
        layout.set_font_description(fd)
        return layout

    def _on_draw(self, widget, cr):
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.paint()

        state = self._state
        text = state.get('text', '')
        if not text or not state.get('enabled', False):
            return False

        font_size = max(8, int(state.get('font_size', 48)))
        opacity = float(state.get('opacity', 1.0))

        cr.translate(self._draw_x, self._draw_y)
        layout = self._make_layout(cr, text, font_size)

        cr.set_operator(cairo.OPERATOR_OVER)

        cr.set_source_rgba(0, 0, 0, 0.75 * opacity)
        for ox, oy in [(-1, -1), (1, -1), (-1, 1), (1, 1),
                       (0, -1), (0, 1), (-1, 0), (1, 0)]:
            cr.save()
            cr.translate(ox, oy)
            PangoCairo.show_layout(cr, layout)
            cr.restore()

        r, g, b, a = _rgba(state.get('text_color', '#ffffff'), opacity)
        cr.set_source_rgba(r, g, b, a)
        cr.move_to(0, 0)
        PangoCairo.show_layout(cr, layout)

        return False

    def _get_text_size(self, text, font_size):
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1)
        cr = cairo.Context(surf)
        layout = self._make_layout(cr, text, font_size)
        w, h = layout.get_pixel_size()
        return max(w + 2, 4), max(h + 2, 4)

    def _poll(self):
        if not os.path.exists(STATE_FILE):
            GLib.idle_add(Gtk.main_quit)
            return False
        try:
            mtime = os.path.getmtime(STATE_FILE)
            if mtime != self._last_mtime:
                self._last_mtime = mtime
                with open(STATE_FILE) as f:
                    self._state = json.load(f)
                self._set_drag_mode(self._state.get('drag_mode', False))
                self._refresh()
        except Exception:
            pass
        return True

    def _refresh(self):
        state = self._state
        if not state.get('enabled', False):
            self.hide()
            return

        if not self._drag_mode:
            self._draw_x = int(state.get('x', 20))
            self._draw_y = int(state.get('y', 280))

        if not self.get_visible():
            self.show_all()
        self.queue_draw()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: GLib.idle_add(Gtk.main_quit))
    IndicatorOverlay()
    Gtk.main()
