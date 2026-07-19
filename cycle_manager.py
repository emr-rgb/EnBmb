# ============================================================
#  EnB Multibox Manager — cycle_manager.py
#  Handles window cycling — swaps secondary windows to main
#  monitor and back, tracks swap state.
# ============================================================

import sys
import time
import threading
from constants import ENB_WINDOW_TITLE, WIN32_NC_H, WIN32_NC_W
from window_manager import (
    activate_window,
    move_resize_window,
    release_modifiers,
    wait_modifiers_released,
)


class CycleManager:
    """
    Manages the window swap cycle.

    When cycling:
    - The currently active secondary slot moves to the main monitor (full size)
    - Slot 1 (driver) moves to the vacated secondary spot
    - Pressing cycle again moves to the next secondary slot
    - Return-to-driver restores the original layout

    Tracks swap state so we always know where each window is.
    """

    def __init__(self, slot_manager, settings: dict):
        self.slots    = slot_manager
        self.settings = settings

        # Swap state
        self._swapped_slot  = None   # index of slot currently on main monitor
        self._driver_saved  = None   # saved geometry of slot 1 before swap
        self._swap_saved    = None   # saved geometry of swapped slot before swap

        # Driver assignment — set by Alt+G; independent of swap state
        self._driver_idx    = 0      # slot index that loops treat as the driver

        # Prevent double-fire from X11 key repeat
        self._cycle_lock      = threading.Lock()
        self._last_cycle_time = 0.0
        self._DEBOUNCE_S      = 0.35

    def reset(self):
        """Reset all swap and driver state — call on profile load."""
        self._swapped_slot = None
        self._driver_saved = None
        self._swap_saved   = None
        self._driver_idx   = 0

    def _main_monitor(self):
        return self.settings["layout"].get("main_monitor", 0)

    def _secondary_monitor(self):
        return self.settings["layout"].get("secondary_monitor", 1)

    def _get_monitor_geometry(self, monitors: list, index: int) -> dict:
        for m in monitors:
            if m["index"] == index:
                return m
        return monitors[0] if monitors else {"x": 0, "y": 0, "w": 1920, "h": 1080}

    def _acquire(self) -> bool:
        """Return True if we should proceed; False if debounce/lock blocks."""
        now = time.time()
        if now - self._last_cycle_time < self._DEBOUNCE_S:
            return False
        if not self._cycle_lock.acquire(blocking=False):
            return False
        self._last_cycle_time = time.time()
        return True

    def _release(self):
        self._cycle_lock.release()

    def cycle_next(self, monitors: list):
        """Cycle to the next secondary slot, or return to driver after last."""
        if not self._acquire():
            return
        try:
            assigned  = self.slots.assigned_slots()
            secondary = [s for s in assigned if s.index != 0]
            if not secondary:
                return

            if self._swapped_slot is None:
                target = secondary[0]
            else:
                current_indices = [s.index for s in secondary]
                try:
                    pos      = current_indices.index(self._swapped_slot)
                    next_pos = pos + 1
                    if next_pos >= len(current_indices):
                        # Wrapped past last secondary — return to driver
                        self._return_to_driver_impl(monitors)
                        return
                    target = secondary[next_pos]
                except ValueError:
                    target = secondary[0]

            self._swap_to_main(target, monitors)
        finally:
            self._release()

    def cycle_prev(self, monitors: list):
        """Cycle to the previous secondary slot."""
        if not self._acquire():
            return
        try:
            assigned  = self.slots.assigned_slots()
            secondary = [s for s in assigned if s.index != 0]
            if not secondary:
                return

            if self._swapped_slot is None:
                target = secondary[-1]
            else:
                current_indices = [s.index for s in secondary]
                try:
                    pos      = current_indices.index(self._swapped_slot)
                    prev_pos = pos - 1
                    if prev_pos < 0:
                        self._return_to_driver_impl(monitors)
                        return
                    target = secondary[prev_pos]
                except ValueError:
                    target = secondary[-1]

            self._swap_to_main(target, monitors)
        finally:
            self._release()

    def cycle_to_slot(self, slot_index: int, monitors: list):
        """Directly swap a specific slot to the main monitor."""
        if not self._acquire():
            return
        try:
            if slot_index == 0:
                self._return_to_driver_impl(monitors)
            else:
                slot = self.slots.slot(slot_index)
                if slot.is_assigned:
                    self._swap_to_main(slot, monitors)
        finally:
            self._release()

    def return_to_driver(self, monitors: list):
        """Public hotkey entry — restore slot 1, return swapped slot to secondary."""
        if not self._acquire():
            return
        try:
            self._return_to_driver_impl(monitors)
        finally:
            self._release()

    def _return_to_driver_impl(self, monitors: list):
        """Raw implementation — caller must hold _cycle_lock."""
        if self._swapped_slot is None:
            driver = self.slots.slot(0)
            if driver.is_assigned:
                wait_modifiers_released()
                release_modifiers()
                activate_window(driver.window_id)
            return

        driver  = self.slots.slot(0)
        swapped = self.slots.slot(self._swapped_slot)

        ops = []
        if self._driver_saved and driver.is_assigned:
            ops.append((driver, self._driver_saved))
        if self._swap_saved and swapped.is_assigned:
            ops.append((swapped, self._swap_saved))
        self._run_moves_parallel(ops)

        if driver.is_assigned:
            wait_modifiers_released()
            release_modifiers()
            activate_window(driver.window_id)

        self._swapped_slot = None
        self._driver_saved = None
        self._swap_saved   = None

    def _swap_to_main(self, target_slot, monitors: list):
        """
        Swap target_slot to main monitor (full size).
        Move slot 1 to target_slot's secondary position.

        All independent move/resize ops run in parallel — each window lives in
        its own Wine prefix so SetWindowPos calls do not contend.
        """
        driver = self.slots.slot(0)
        # monitors (from gui_main.self.monitors) already has the taskbar
        # reservation applied to its height.
        main_mon  = self._get_monitor_geometry(monitors, self._main_monitor())

        main_geo = {
            "x": main_mon["x"], "y": main_mon["y"],
            "w": main_mon["w"], "h": main_mon["h"],
        }

        ops = []

        # If already swapped to a different slot, restore it to its secondary
        if self._swapped_slot is not None and self._swapped_slot != target_slot.index:
            prev_swapped = self.slots.slot(self._swapped_slot)
            if self._swap_saved and prev_swapped.is_assigned:
                g = self._swap_saved
                prev_swapped.x, prev_swapped.y = g["x"], g["y"]
                prev_swapped.w, prev_swapped.h = g["w"], g["h"]
                ops.append((prev_swapped, g))

        # Save current INTENDED positions (slot.x/y/w/h) — stable, no X11 read timing issues
        self._driver_saved = {"x": driver.x,      "y": driver.y,      "w": driver.w,      "h": driver.h}
        self._swap_saved   = {"x": target_slot.x,  "y": target_slot.y,  "w": target_slot.w,  "h": target_slot.h}
        self._swapped_slot = target_slot.index

        # Only expand target to full-screen when driver IS full-screen (1+N dual-monitor
        # layouts). In equal-grid layouts the driver occupies a cell — swap geometries.
        if (driver.w == main_mon["w"] and driver.x == main_mon["x"]
                and driver.y == main_mon["y"]):
            target_geo = main_geo
        else:
            target_geo = self._driver_saved

        if driver.is_assigned:
            ops.append((driver, self._swap_saved))

        if target_slot.is_assigned:
            ops.append((target_slot, target_geo))

        self._run_moves_parallel(ops)

        if target_slot.is_assigned:
            time.sleep(0.1)
            wait_modifiers_released()
            release_modifiers()
            activate_window(target_slot.window_id)

    def _run_moves_parallel(self, ops):
        """Run a list of (slot, geometry-dict) move+resize ops concurrently."""
        if not ops:
            return
        threads = []
        for slot, g in ops:
            t = threading.Thread(
                target=self._move_one,
                args=(slot, g["x"], g["y"], g["w"], g["h"]),
                daemon=True,
            )
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        if sys.platform != "win32":
            # Phase 3: Openbox sometimes re-decorates windows during cross-monitor moves.
            # Re-apply borderless to any moved slot that gained a frame.
            from window_manager import get_frame_extents, set_window_borderless
            time.sleep(0.2)
            for slot, _ in ops:
                if not slot.is_assigned:
                    continue
                ext = get_frame_extents(slot.window_id)
                if ext[0] + ext[1] + ext[2] + ext[3] > 0:
                    set_window_borderless(slot.window_id, True)
                    time.sleep(0.3)

    def _move_one(self, slot, x: int, y: int, w: int, h: int):
        """Single-window move+resize. Designed to run inside a thread."""
        if sys.platform == "win32":
            move_resize_window(slot.window_id, x, y, w, h)
        else:
            import subprocess
            self._unmaximize_if_needed(slot.window_id)
            self._winresize_slot(slot, x, y, w, h)
            subprocess.run(["xdotool", "windowmove", str(slot.window_id), str(x), str(y)],
                           capture_output=True)

    def _wm_state_has_max_or_fullscreen(self, wid: int) -> bool:
        """True if the window currently carries maximized or fullscreen WM state.
        Used to skip the wmctrl unmaximize step (and its 50ms settle sleep)
        when the window isn't in those states — common case in normal cycles."""
        import subprocess
        try:
            r = subprocess.run(
                ["xprop", "-id", hex(wid), "_NET_WM_STATE"],
                capture_output=True, text=True, timeout=1,
            )
            out = r.stdout
            return ("_NET_WM_STATE_MAXIMIZED" in out) or ("_NET_WM_STATE_FULLSCREEN" in out)
        except Exception:
            return True  # on probe failure, fall through to the safe path

    def _unmaximize_if_needed(self, wid: int):
        """Strip maximized/fullscreen WM state so the window can be freely moved."""
        import subprocess
        if self._wm_state_has_max_or_fullscreen(wid):
            wid_hex = hex(wid)
            subprocess.run(["wmctrl", "-ir", wid_hex,
                            "-b", "remove,maximized_vert,maximized_horz"],
                           capture_output=True)
            subprocess.run(["wmctrl", "-ir", wid_hex,
                            "-b", "remove,fullscreen"],
                           capture_output=True)
            time.sleep(0.05)

    def _winresize_slot(self, slot, x: int, y: int, w: int, h: int):
        """
        Use winresize.exe (SetWindowPos) to resize a Wine window.
        xdotool windowsize fails on Wine windows; this is the workaround.
        Must run under the same Wine prefix as the target window.
        Win32 window title is always 'Earth & Beyond' regardless of character name.
        """
        import subprocess
        import os
        from window_manager import get_frame_extents

        # Apply the same WIN32_NC correction as _apply_layout_thread:
        # SetWindowPos(w,h) = target_size + Win32_NC - OB_frame_extents
        ext   = get_frame_extents(slot.window_id)
        ob_w  = ext[0] + ext[1]
        ob_h  = ext[2] + ext[3]
        rw    = w + WIN32_NC_W - ob_w
        rh    = h + WIN32_NC_H - ob_h

        base   = os.path.expanduser("~/.wine-enb")
        prefix = base if slot.index == 0 else f"{base}-{slot.index + 1}"
        winres = os.path.expanduser("~/bin/winresize.exe")
        if not os.path.exists(winres):
            return
        cmd = f'WINEPREFIX="{prefix}" wine "{winres}" "{ENB_WINDOW_TITLE}" {x} {y} {rw} {rh}'
        try:
            subprocess.run(["bash", "-c", cmd], capture_output=True, timeout=8)
        except Exception as e:
            print(f"[cycle] winresize failed for slot {slot.index + 1}: {e}")
