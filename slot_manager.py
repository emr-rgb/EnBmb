# ============================================================
#  EnB Multibox Manager — slot_manager.py
#  Manages all client slots — assignment, cycling, state
# ============================================================

import threading
import time
from constants import ENB_WINDOW_TITLE, MAX_SLOTS
from window_manager import (
    find_enb_windows, window_exists, rename_window,
    activate_window, focus_window, send_key_to_window,
    send_keys_to_window, kill_window_process, slot_wine_prefix,
)


class Slot:
    """Represents one multibox slot (one EnB client position)."""

    def __init__(self, index: int):
        self.index     = index       # 0-based slot index
        self.role      = ""          # class abbreviation e.g. "PW"
        self.char_name = ""          # character name
        self.window_id = None        # X11 window id (int)
        self.pid       = None        # process PID
        self.monitor   = 1           # target monitor index
        self.x         = 0
        self.y         = 0
        self.w         = 960
        self.h         = 540
        self.stay_on_top  = False
        self.borderless   = True
        self.role_profile = ""       # name of the role profile for loop macros
        self.username     = ""       # login username for auto-login macro
        self.password     = ""       # login password for auto-login macro
        self.character    = ""       # name of character profile assigned to this slot

    # ── Character profile helpers ─────────────────────────────
    def apply_character(self, char: dict):
        """Populate slot fields from a character profile dict.
        Caller is responsible for persisting the slot afterwards.
        Empty fields on the character do NOT clear existing slot
        values, so a partially-filled character won't wipe credentials."""
        if not char:
            return
        name = char.get("name", "")
        self.character = name
        if name:
            self.char_name = name
        if char.get("account"):
            self.username = char["account"]
        if char.get("password"):
            self.password = char["password"]
        if char.get("char_class"):
            self.role = char["char_class"]
        if char.get("role_profile"):
            self.role_profile = char["role_profile"]
        if self.is_assigned and (self.char_name or self.role):
            title = self.char_name or self.role
            rename_window(self.window_id, title)

    @property
    def label(self) -> str:
        """Display label: role abbrev or slot number."""
        return self.role if self.role else f"Slot {self.index + 1}"

    @property
    def is_assigned(self) -> bool:
        return self.window_id is not None

    def check_alive(self) -> bool:
        """Return True if the assigned window still exists."""
        if not self.is_assigned:
            return False
        alive = window_exists(self.window_id)
        if not alive:
            # Client has died — clear assignment
            self.window_id = None
            self.pid       = None
        return alive

    def assign(self, window_id: int, pid: int = None):
        """Assign an X11 window to this slot."""
        self.window_id = window_id
        if pid:
            self.pid = pid
        # Rename window to char_name if set, otherwise role abbreviation
        title = self.char_name or self.role
        if title:
            rename_window(window_id, title)

    def unassign(self):
        """Remove window assignment from this slot."""
        self.window_id = None
        self.pid       = None

    def set_role(self, abbrev: str):
        """Set role — only rename window if no char_name is set."""
        self.role = abbrev
        if self.is_assigned:
            title = self.char_name or abbrev
            if title:
                rename_window(self.window_id, title)

    def set_char_name(self, name: str):
        """Set character name and rename the window."""
        self.char_name = name
        if self.is_assigned:
            title = name or self.role
            if title:
                rename_window(self.window_id, title)

    def focus(self) -> bool:
        """Bring this slot's window to focus."""
        if not self.is_assigned:
            return False
        return activate_window(self.window_id)

    def send_key(self, key: str) -> bool:
        """Send a key to this slot's window (inactive broadcast attempt)."""
        if not self.is_assigned:
            return False
        return send_key_to_window(self.window_id, key)

    def send_keys(self, keys: list, delay_ms: int = 50) -> bool:
        if not self.is_assigned:
            return False
        return send_keys_to_window(self.window_id, keys, delay_ms)

    def kill(self) -> bool:
        """Kill this slot's client process."""
        if self.pid:
            return kill_window_process(self.pid)
        return False

    def to_dict(self) -> dict:
        return {
            "role":         self.role,
            "role_profile": self.role_profile,
            "char_name":    self.char_name,
            "character":    self.character,
            "username":     self.username,
            "password":     self.password,
            "window_id":    self.window_id,
            "monitor":      self.monitor,
            "x":            self.x,
            "y":            self.y,
            "w":            self.w,
            "h":            self.h,
            "stay_on_top":  self.stay_on_top,
        }

    def from_dict(self, d: dict):
        self.role         = d.get("role", "")
        self.role_profile = d.get("role_profile", "")
        self.char_name    = d.get("char_name", "")
        self.character    = d.get("character", "")
        self.username     = d.get("username", "")
        self.password     = d.get("password", "")
        self.monitor      = d.get("monitor", 1)
        self.x            = d.get("x", 0)
        self.y            = d.get("y", 0)
        self.w            = d.get("w", 960)
        self.h            = d.get("h", 540)
        self.stay_on_top  = d.get("stay_on_top", False)
        # Don't restore window_id — windows must be re-detected on launch
        # Back-fill character from char_name if not explicitly saved yet
        if not self.character and self.char_name:
            from config_manager import load_character
            try:
                load_character(self.char_name)
                self.character = self.char_name
            except Exception:
                pass


class SlotManager:
    """
    Manages all slots, cycling state, and auto-detection.
    This is the core state object passed around the app.
    """

    def __init__(self):
        self.slots        = [Slot(i) for i in range(MAX_SLOTS)]
        self.active_index = 0          # currently focused slot (0-based)
        self._lock        = threading.Lock()
        self._callbacks   = []         # UI update callbacks

    # ── Slot access ───────────────────────────────────────────

    def slot(self, index: int) -> Slot:
        return self.slots[index]

    @property
    def active_slot(self) -> Slot:
        return self.slots[self.active_index]

    def assigned_slots(self) -> list[Slot]:
        """Return only slots that have a window assigned."""
        return [s for s in self.slots if s.is_assigned]

    def count_assigned(self) -> int:
        return len(self.assigned_slots())

    # ── Cycling ───────────────────────────────────────────────

    def cycle_next(self) -> Slot | None:
        """Focus the next assigned slot after the current one."""
        assigned = self.assigned_slots()
        if not assigned:
            return None
        try:
            current_pos = assigned.index(self.active_slot)
            next_slot   = assigned[(current_pos + 1) % len(assigned)]
        except ValueError:
            next_slot = assigned[0]
        self.active_index = next_slot.index
        next_slot.focus()
        self._notify()
        return next_slot

    def cycle_prev(self) -> Slot | None:
        """Focus the previous assigned slot."""
        assigned = self.assigned_slots()
        if not assigned:
            return None
        try:
            current_pos = assigned.index(self.active_slot)
            prev_slot   = assigned[(current_pos - 1) % len(assigned)]
        except ValueError:
            prev_slot = assigned[-1]
        self.active_index = prev_slot.index
        prev_slot.focus()
        self._notify()
        return prev_slot

    def focus_slot(self, index: int) -> bool:
        """Directly focus a specific slot by index."""
        if 0 <= index < MAX_SLOTS:
            slot = self.slots[index]
            if slot.is_assigned:
                self.active_index = index
                slot.focus()
                self._notify()
                return True
        return False

    # ── Auto-detection ────────────────────────────────────────

    def auto_detect(self, exclude_ids: set | None = None) -> int:
        """
        Scan for EnB windows and assign them to their correct slots.
        Phase 1: title-match ALL windows against configured char_name/role —
                 corrects mismatches even if the window was already assigned
                 to the wrong slot.
        Phase 2: fill remaining empty slots with unmatched windows in order.
        Returns number of windows newly assigned (not previously in any slot).

        exclude_ids: window ids to never assign to a slot (e.g. the
        untracked "Launch Independent Client" window). On Linux this is
        normally redundant with the wine-prefix check below, but on
        Windows there's no prefix to distinguish an independent client
        window from a managed one, so this is the only guard.
        """
        with self._lock:
            char_names = [s.char_name for s in self.slots if s.char_name]
            enb_windows = find_enb_windows(extra_names=char_names)
            if exclude_ids:
                enb_windows = [w for w in enb_windows if w["id"] not in exclude_ids]
            previously_assigned = {s.window_id for s in self.slots if s.is_assigned}

            # Phase 1: correct mismatches by title — only match window to a slot
            # if the window's wine prefix matches that slot's expected prefix.
            matched_win_ids = set()
            changes = 0
            for win in enb_windows:
                title = win["title"].strip()
                win_prefix = win.get("wine_prefix")  # None = unknown
                for slot in self.slots:
                    if (slot.char_name and title == slot.char_name) or \
                       (slot.role and title == slot.role):
                        expected = slot_wine_prefix(slot.index)
                        if win_prefix is not None and win_prefix != expected:
                            break  # wrong prefix — don't assign to this slot
                        if slot.window_id != win["id"]:
                            # Pull this window out of whatever slot currently holds it
                            for s in self.slots:
                                if s.window_id == win["id"]:
                                    s.window_id = None
                                    s.pid = None
                            slot.window_id = None
                            slot.pid = None
                            slot.assign(win["id"], win.get("pid"))
                            changes += 1
                        matched_win_ids.add(win["id"])
                        break

            # Phase 2: fill empty slots — only assign window to the slot whose
            # prefix matches. Skip windows whose prefix doesn't match any empty slot.
            new_count = 0
            for win in enb_windows:
                if win["id"] in matched_win_ids:
                    continue
                win_prefix = win.get("wine_prefix")  # None = unknown
                matched_slot = None
                for slot in self.slots:
                    if slot.is_assigned or slot.index >= MAX_SLOTS:
                        continue
                    expected = slot_wine_prefix(slot.index)
                    if win_prefix is None or win_prefix == expected:
                        matched_slot = slot
                        break
                if matched_slot:
                    matched_slot.assign(win["id"], win.get("pid"))
                    if matched_slot.w == 0 or matched_slot.h == 0:
                        matched_slot.x = win["x"]
                        matched_slot.y = win["y"]
                        matched_slot.w = win["w"]
                        matched_slot.h = win["h"]
                    if win["id"] not in previously_assigned:
                        new_count += 1
                    changes += 1
                    matched_win_ids.add(win["id"])

            self._notify()
            return new_count, changes

    def check_liveness(self):
        """Check all assigned slots for dead windows. Call periodically."""
        changed = False
        for slot in self.slots:
            if slot.is_assigned:
                if not slot.check_alive():
                    changed = True
        if changed:
            self._notify()

    def assign_window_to_slot(self, slot_index: int, window_id: int, pid: int = None):
        """Manually assign a specific window to a specific slot."""
        with self._lock:
            # Remove this window from any other slot first
            for s in self.slots:
                if s.window_id == window_id:
                    s.unassign()
            self.slots[slot_index].assign(window_id, pid)
            self._notify()

    def clear_slot(self, slot_index: int):
        """Clear a slot's window assignment without killing the process."""
        self.slots[slot_index].unassign()
        self._notify()

    def kill_slot(self, slot_index: int) -> bool:
        """Kill the client in a slot and clear it."""
        slot = self.slots[slot_index]
        ok   = slot.kill()
        slot.unassign()
        self._notify()
        return ok

    # ── Layout helpers ────────────────────────────────────────

    def apply_layout(self):
        """Apply stored x/y/w/h to each assigned slot's window sequentially.
        winresize handles size; xdotool windowmove --sync corrects position after."""
        from window_manager import winresize_wine_window, _run
        for slot in self.slots:
            if slot.is_assigned:
                wid_hex = hex(slot.window_id)
                _run(["wmctrl", "-ir", wid_hex, "-b", "remove,maximized_vert,maximized_horz"])
                _run(["wmctrl", "-ir", wid_hex, "-b", "remove,fullscreen"])
                time.sleep(0.05)
                winresize_wine_window(slot.index, ENB_WINDOW_TITLE,
                                      slot.x, slot.y, slot.w, slot.h)
                _run(["xdotool", "windowmove", "--sync",
                      str(slot.window_id), str(slot.x), str(slot.y)])
                time.sleep(0.15)

    # ── Serialization ─────────────────────────────────────────

    def to_list(self) -> list:
        return [s.to_dict() for s in self.slots]

    def from_list(self, data: list):
        for i, d in enumerate(data[:MAX_SLOTS]):
            self.slots[i].from_dict(d)
        self._notify()

    # ── Observer pattern for UI updates ──────────────────────

    def register_callback(self, fn):
        """Register a function to call when slot state changes."""
        self._callbacks.append(fn)

    def _notify(self):
        for fn in self._callbacks:
            try:
                fn()
            except Exception as e:
                print(f"[slots] Callback error: {e}")
