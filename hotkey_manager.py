# ============================================================
#  EnB Multibox Manager — hotkey_manager.py
#  Global hotkey listener using pynput.
#  Captures keypresses system-wide even when game is focused.
# ============================================================

import threading
import time
from pynput import keyboard as pynput_keyboard
from pynput.keyboard import Key

# Modifier name (as used in hotkey strings) -> the set of pynput Key members
# that represent it. Used to wait for a held modifier to be released before
# firing a combo's action, so the game window doesn't see it as still down.
MODIFIER_KEYS = {
    "shift": {Key.shift, Key.shift_l, Key.shift_r},
    "ctrl":  {Key.ctrl, Key.ctrl_l, Key.ctrl_r},
    "alt":   {Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr},
    "super": {Key.cmd, Key.cmd_l, Key.cmd_r},
    "cmd":   {Key.cmd, Key.cmd_l, Key.cmd_r},
}


# ── Key string conversion ─────────────────────────────────────

def _parse_hotkey(hotkey_str: str):
    """
    Convert a hotkey string like 'ctrl+F1', 'grave', 'shift+Tab'
    into a pynput GlobalHotKeys compatible string like '<ctrl>+<f1>'.
    Returns None if the hotkey string is empty or invalid.
    """
    if not hotkey_str or hotkey_str.strip() == "":
        return None

    parts = hotkey_str.lower().split("+")
    result = []

    modifier_map = {
        "ctrl":  "<ctrl>",
        "alt":   "<alt>",
        "shift": "<shift>",
        "super": "<super>",
        "cmd":   "<cmd>",
    }

    key_map = {
        "grave":     "`",
        "tab":       "<tab>",
        "escape":    "<esc>",
        "return":    "<enter>",
        "enter":     "<enter>",
        "space":     "<space>",
        "backspace":  "<backspace>",
        "delete":    "<delete>",
        "f1":  "<f1>",  "f2":  "<f2>",  "f3":  "<f3>",  "f4":  "<f4>",
        "f5":  "<f5>",  "f6":  "<f6>",  "f7":  "<f7>",  "f8":  "<f8>",
        "f9":  "<f9>",  "f10": "<f10>", "f11": "<f11>", "f12": "<f12>",
    }

    for part in parts:
        part = part.strip()
        if part in modifier_map:
            result.append(modifier_map[part])
        elif part in key_map:
            result.append(key_map[part])
        elif len(part) == 1:
            result.append(part)
        else:
            # Unknown key — wrap in angle brackets
            result.append(f"<{part}>")

    if not result:
        return None
    return "+".join(result)


# ── Hotkey Manager ────────────────────────────────────────────

class HotkeyManager:
    """
    Manages global hotkey registration and dispatch using pynput.
    Runs in a background thread — hotkeys work even when game is focused.
    """

    def __init__(self):
        self._listener   = None
        self._key_listener = None
        self._thread     = None
        self._callbacks  = {}   # action_name → callable
        self._hotkeys    = {}   # action_name → hotkey_str
        self._running    = False
        self._lock       = threading.Lock()
        self._pressed    = set()   # currently-held pynput Key/KeyCode objects
        self._pending_seq = {}     # mod-signature → sequence number of latest combo

    def register(self, action: str, callback):
        """Register a callback for a named action."""
        self._callbacks[action] = callback

    def start(self, hotkey_settings: dict):
        """
        Start listening for hotkeys.
        hotkey_settings: dict of action_name → hotkey_string
        """
        self.stop()
        self._hotkeys = dict(hotkey_settings)
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the hotkey listener."""
        self._running = False
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        if self._key_listener:
            try:
                self._key_listener.stop()
            except Exception:
                pass
            self._key_listener = None
        self._pressed.clear()
        self._pending_seq.clear()

    def restart(self, hotkey_settings: dict):
        """Restart with new hotkey settings."""
        self.start(hotkey_settings)

    def _run(self):
        """Background thread — builds and runs the pynput listener."""
        self._running = True

        # Build the hotkeys dict for pynput GlobalHotKeys
        # Format: {'<ctrl>+f': callback, '`': callback, ...}

        # pynput fires ALL matching hotkeys for a keypress, including bare-key
        # handlers when a modifier+key combo fires (e.g. alt+grave also triggers
        # the bare grave handler). Track which base keys have modifier variants
        # so we can suppress the bare-key handler when the modifier combo fires.
        base_keys_with_modifiers = set()
        for hk_str in self._hotkeys.values():
            if hk_str and '+' in hk_str.lower():
                base_keys_with_modifiers.add(hk_str.lower().split('+')[-1].strip())

        _suppress = {}  # base_key → suppress-until timestamp

        # Track currently-held keys via a parallel listener, so combo handlers
        # can wait for their modifier(s) to be physically released before
        # firing — otherwise e.g. holding Shift while pressing F1 then F6
        # delivers a still-held Shift to the newly-activated game window
        # (seen as an unwanted camera zoom).
        def _on_press(key):
            self._pressed.add(key)

        def _on_release(key):
            self._pressed.discard(key)

        self._key_listener = pynput_keyboard.Listener(
            on_press=_on_press, on_release=_on_release
        )
        self._key_listener.start()

        def _wait_modifiers_released(mod_groups, timeout=2.0):
            """Block until none of the given modifier key-groups are held,
            or until timeout. Returns once clear (or on timeout)."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                if not any(self._pressed & grp for grp in mod_groups):
                    return
                time.sleep(0.02)

        pynput_map = {}

        for action, hk_str in self._hotkeys.items():
            callback = self._callbacks.get(action)
            if not callback or not hk_str:
                continue
            parsed = _parse_hotkey(hk_str)
            if not parsed:
                continue
            has_modifier = '+' in hk_str
            base_key = hk_str.lower().split('+')[-1].strip()
            is_conflicted_bare = not has_modifier and base_key in base_keys_with_modifiers
            mod_groups = [
                MODIFIER_KEYS[p.strip()]
                for p in hk_str.lower().split('+')[:-1]
                if p.strip() in MODIFIER_KEYS
            ]
            mod_sig = tuple(sorted(
                p.strip() for p in hk_str.lower().split('+')[:-1]
                if p.strip() in MODIFIER_KEYS
            ))

            def make_handler(cb, hm=has_modifier, bk=base_key, icb=is_conflicted_bare,
                              mods=mod_groups, sig=mod_sig):
                def handler():
                    if hm:
                        # Modifier combo fired — suppress bare-key variant.
                        # Window must exceed the bare-key delay below (30ms).
                        _suppress[bk] = time.time() + 0.1

                        # If the same modifier is still held when another combo
                        # fires (e.g. Shift+F1 then Shift+F6 without releasing
                        # Shift), only the LAST one should actually run — running
                        # both back-to-back briefly re-activates the first
                        # target's window, which is what causes the residual
                        # camera-zoom bleed. Mark this as the latest for its
                        # modifier signature; superseded ones are skipped.
                        with self._lock:
                            self._pending_seq[sig] = self._pending_seq.get(sig, 0) + 1
                            my_seq = self._pending_seq[sig]

                        def _run_after_release(cb=cb, mods=mods, sig=sig, my_seq=my_seq):
                            # Don't activate the target window while the
                            # combo's modifier(s) are still physically held —
                            # otherwise the held modifier bleeds into the
                            # newly-focused game window.
                            _wait_modifiers_released(mods)
                            if self._pending_seq.get(sig) != my_seq:
                                return  # superseded by a later combo press
                            try:
                                cb()
                            except Exception as e:
                                print(f"[hotkeys] Error in handler: {e}")

                        threading.Thread(target=_run_after_release, daemon=True).start()
                    elif icb:
                        # Bare key that has a modifier variant.
                        # Delay firing so the modifier combo handler (which may
                        # fire in any order) always gets a chance to set the
                        # suppress flag first. Both events arrive within <1ms;
                        # 30ms is well above that.
                        def _delayed(cb=cb, bk=bk):
                            time.sleep(0.03)
                            if _suppress.get(bk, 0) > time.time():
                                return
                            try:
                                cb()
                            except Exception as e:
                                print(f"[hotkeys] Error in handler: {e}")
                        threading.Thread(target=_delayed, daemon=True).start()
                    else:
                        try:
                            cb()
                        except Exception as e:
                            print(f"[hotkeys] Error in handler: {e}")
                return handler
            pynput_map[parsed] = make_handler(callback)

        if not pynput_map:
            print("[hotkeys] No hotkeys configured")
            return

        try:
            self._listener = pynput_keyboard.GlobalHotKeys(pynput_map)
            print(f"[hotkeys] Listening for {len(pynput_map)} hotkeys")
            self._listener.run()
        except Exception as e:
            print(f"[hotkeys] Listener error: {e}")
        finally:
            self._running = False
