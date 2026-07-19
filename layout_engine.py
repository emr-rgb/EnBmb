# ============================================================
#  EnB Multibox Manager — layout_engine.py
#  Calculates window geometry for tiling presets
#  Works with monitor info from window_manager.get_monitors()
# ============================================================


def _fit_43(w: int, h: int) -> tuple[int, int]:
    """Return largest 4:3 rectangle that fits within (w, h)."""
    if w * 3 > h * 4:   # wider than 4:3 — constrain width
        return h * 4 // 3, h
    else:               # taller than 4:3 — constrain height
        return w, w * 3 // 4


def calculate_grid(monitor: dict, count: int, gap: int = 4,
                   fill_vertical: bool = True,
                   ar_lock: str = "none") -> list[dict]:
    """
    Divide a monitor into 'count' equal cells in a grid.
    Returns list of {x, y, w, h} dicts, one per cell.

    fill_vertical=True  → fills column by column (top-to-bottom, left-to-right)
                          e.g. for 5 slots in 3 cols:
                          [0][2][4]
                          [1][3][ ]
    fill_vertical=False → fills row by row (left-to-right, top-to-bottom)
    """
    if count <= 0:
        return []
    if count == 1:
        return [{"x": monitor["x"], "y": monitor["y"],
                 "w": monitor["w"], "h": monitor["h"]}]

    # 2-slot special case: side by side with 640×480 (4:3) aspect ratio,
    # scaled to fill width, centered vertically — windows touch but don't
    # stretch full monitor height.
    if count == 2:
        cell_w = (monitor["w"] - gap * 3) // 2
        cell_h = cell_w * 480 // 640          # 4:3 AR
        y_off  = monitor["y"] + gap
        return [
            {"x": monitor["x"] + gap,                "y": y_off, "w": cell_w, "h": cell_h},
            {"x": monitor["x"] + gap + cell_w + gap, "y": y_off, "w": cell_w, "h": cell_h},
        ]

    # Choose grid dimensions based on count:
    #   3 – 4   → 2 cols, 2 rows (2×2, with empty bottom-right for 3)
    #   5 – 6   → 3 cols, 2 rows
    if count <= 4:
        cols, rows = 2, 2
    else:
        cols, rows = 3, 2

    cell_w = (monitor["w"] - gap * (cols + 1)) // cols
    cell_h = (monitor["h"] - gap * (rows + 1)) // rows

    if ar_lock == "4:3":
        cell_w, cell_h = _fit_43(cell_w, cell_h)

    cells = []
    for i in range(count):
        if fill_vertical:
            # Fill column by column
            col = i // rows
            row = i % rows
        else:
            # Fill row by row
            col = i % cols
            row = i // cols
        x = monitor["x"] + gap + col * (cell_w + gap)
        y = monitor["y"] + gap + row * (cell_h + gap)
        cells.append({"x": x, "y": y, "w": cell_w, "h": cell_h})

    return cells


def calculate_layout(monitors: list[dict], slots, secondary_count: int,
                     main_monitor: int = 0, secondary_monitor: int = 1,
                     gap: int = 4, ar_lock: str = "none") -> list[dict]:
    """
    Main layout calculation.

    - Slot 0 (the driver/main) → full size on main_monitor
    - Slots 1..secondary_count → equal grid on secondary_monitor
    - Remaining slots → empty (no geometry change)

    monitors : list of monitor dicts from get_monitors()
    slots    : list of Slot objects (for count reference)
    secondary_count : how many windows to tile on secondary (slider value)

    Returns list of geometry dicts indexed by slot index:
    [{x, y, w, h, monitor}, ...] — one per slot, None if not placed
    """
    result = [None] * len(slots)

    # Get monitor objects
    mon_main = _get_monitor(monitors, main_monitor)
    mon_sec  = _get_monitor(monitors, secondary_monitor)

    # Slot 0 — full main monitor (AR-locked if requested)
    if slots:
        w0, h0 = mon_main["w"], mon_main["h"]
        if ar_lock == "4:3":
            w0, h0 = _fit_43(w0, h0)
        result[0] = {
            "x": mon_main["x"],
            "y": mon_main["y"],
            "w": w0,
            "h": h0,
            "monitor": main_monitor,
        }

    # Slots 1..secondary_count — grid sized to the actual slot count so cells
    # are as large as possible. MGR cell is lowest priority: it only appears
    # when sec_count+1 fits within the same grid dimensions as sec_count.
    if secondary_count > 0 and mon_sec:
        full_grid = calculate_grid(mon_sec, secondary_count, gap, ar_lock=ar_lock)
        for i in range(secondary_count):
            slot_index = i + 1
            if slot_index < len(slots) and i < len(full_grid):
                result[slot_index] = {**full_grid[i], "monitor": secondary_monitor}

    return result


def apply_layout_to_slots(slots, layout_result: list):
    """
    Write geometry from layout_result into slot objects.
    Does NOT move actual windows — call slot_manager.apply_layout() for that.
    """
    for i, geo in enumerate(layout_result):
        if geo and i < len(slots):
            slots[i].x       = geo["x"]
            slots[i].y       = geo["y"]
            slots[i].w       = geo["w"]
            slots[i].h       = geo["h"]
            slots[i].monitor = geo["monitor"]


def mgr_cell(monitor: dict, sec_count: int, gap: int = 4) -> dict | None:
    """
    Return the geometry of the MGR (compact manager) cell, or None if it
    cannot be shown without shrinking the game-slot cells.

    MGR is shown only when sec_count+1 falls within the same grid dimensions
    as sec_count (i.e. the extra cell is naturally empty):
      sec_count=3 → 2×2 grid has 4 cells, 4th is free  → show MGR
      sec_count=5 → 3×2 grid has 6 cells, 6th is free  → show MGR
      all others  → adding a cell would change grid size → hide MGR
    """
    def _dims(n):
        if n <= 2:  return None          # special-case layouts, no spare cell
        if n <= 4:  return (2, 2)
        return (3, 2)

    if _dims(sec_count) is None:
        return None
    if _dims(sec_count) != _dims(sec_count + 1):
        return None

    max_cells = _dims(sec_count)[0] * _dims(sec_count)[1]
    full_grid = calculate_grid(monitor, max_cells, gap)
    if sec_count < len(full_grid):
        return full_grid[sec_count]
    return None


def _get_monitor(monitors: list, index: int) -> dict | None:
    for m in monitors:
        if m["index"] == index:
            return m
    if monitors:
        return monitors[min(index, len(monitors) - 1)]
    return None


def single_monitor_layout(monitor: dict, total_slots: int,
                           secondary_count: int, gap: int = 4,
                           ar_lock: str = "none") -> list[dict | None]:
    """
    Layout for a single-monitor setup:
    - Slot 0 takes the top portion (or left half)
    - Remaining slots tile in a grid on the bottom/right
    """
    result = [None] * total_slots

    if total_slots == 1 or secondary_count == 0:
        result[0] = {"x": monitor["x"], "y": monitor["y"],
                     "w": monitor["w"], "h": monitor["h"], "monitor": 0}
        return result

    # Split horizontally: top half for main, bottom for secondaries
    main_h  = monitor["h"] // 2
    sec_h   = monitor["h"] - main_h - gap
    sec_mon = {
        "index": 0,
        "x":     monitor["x"],
        "y":     monitor["y"] + main_h + gap,
        "w":     monitor["w"],
        "h":     sec_h,
    }

    drv_w, drv_h = (_fit_43(monitor["w"], main_h) if ar_lock == "4:3"
                    else (monitor["w"], main_h))
    result[0] = {
        "x": monitor["x"], "y": monitor["y"],
        "w": drv_w, "h": drv_h,
        "monitor": 0,
    }

    grid = calculate_grid(sec_mon, secondary_count, gap, ar_lock=ar_lock)
    for i, cell in enumerate(grid):
        slot_index = i + 1
        if slot_index < total_slots:
            result[slot_index] = {**cell, "monitor": 0}

    return result


def single_monitor_layout_large(monitor: dict, sec_count: int, gap: int = 0,
                                ar_lock: str = "none") -> list[dict | None]:
    """
    Single-monitor layout with driver large in top-left, small slots in a reverse-L.

    Uses a 3-column × 3-row grid where driver occupies the top-left 2×2 block:

      +--------+--------+--------+
      |                 |   5    |
      |    Driver       +--------+
      |   (2/3 W,       |   6    |
      |    2/3 H)       +--------+
      +--------+--------+        |
      |   2    |   3    |   4    |
      +--------+--------+--------+

    Slot order: 2,3,4 across bottom; 5,6 down the right column.
    For sec_count < 5, unused positions are left None (driver stays large).
    For 1+3: driver top-left, 2+3 bottom-left, 4 top-right column (tall).
    """
    mx, my, mw, mh = monitor["x"], monitor["y"], monitor["w"], monitor["h"]
    col = mw // 3        # small cell width
    row = mh // 3        # small cell height
    drv_w = mw - col     # driver width = 2 columns
    drv_h = mh - row     # driver height = 2 rows

    result = [None] * 6  # slots 0..5

    locked_w, locked_h = (_fit_43(drv_w, drv_h) if ar_lock == "4:3" else (drv_w, drv_h))
    result[0] = {"x": mx, "y": my, "w": locked_w, "h": locked_h, "monitor": 0}

    s_col, s_row = (_fit_43(col, row) if ar_lock == "4:3" else (col, row))

    right_x = mx + drv_w
    bot_y = my + drv_h

    # Bottom row: slots 2, 3 (indices 1, 2) — always if sec_count allows
    if sec_count >= 1:
        result[1] = {"x": mx,       "y": bot_y, "w": s_col, "h": s_row, "monitor": 0}
    if sec_count >= 2:
        result[2] = {"x": mx + col, "y": bot_y, "w": s_col, "h": s_row, "monitor": 0}

    # For 4+ secondaries: slot 4 in bottom-right (index 3) + slot 5 in right-top (index 4)
    if sec_count >= 4:
        result[3] = {"x": right_x, "y": bot_y, "w": s_col, "h": s_row, "monitor": 0}
        result[4] = {"x": right_x, "y": my,    "w": s_col, "h": s_row, "monitor": 0}

    # 5th secondary: slot 6 in right-bottom (index 5)
    if sec_count >= 5:
        result[5] = {"x": right_x, "y": my + row, "w": s_col, "h": s_row, "monitor": 0}

    # Special case 1+3: slot 4 as tall right column instead of bottom-right
    if sec_count == 3:
        tc_w, tc_h = (_fit_43(col, drv_h) if ar_lock == "4:3" else (col, drv_h))
        result[3] = {"x": right_x, "y": my, "w": tc_w, "h": tc_h, "monitor": 0}

    return result


# ── Canvas scaling helpers ────────────────────────────────────
# The layout canvas in the UI is a scaled-down view of all monitors.
# These helpers convert between real screen coords and canvas coords.

def screen_to_canvas(sx: int, sy: int, monitors: list[dict],
                     canvas_w: int, canvas_h: int) -> tuple[int, int]:
    """Convert real screen coordinates to canvas pixel coordinates."""
    total_w, total_h, ox, oy = _monitor_bounds(monitors)
    cx = int((sx - ox) / total_w * canvas_w)
    cy = int((sy - oy) / total_h * canvas_h)
    return cx, cy


def canvas_to_screen(cx: int, cy: int, monitors: list[dict],
                     canvas_w: int, canvas_h: int) -> tuple[int, int]:
    """Convert canvas pixel coordinates to real screen coordinates."""
    total_w, total_h, ox, oy = _monitor_bounds(monitors)
    sx = int(cx / canvas_w * total_w) + ox
    sy = int(cy / canvas_h * total_h) + oy
    return sx, sy


def monitor_to_canvas_rect(monitor: dict, monitors: list[dict],
                            canvas_w: int, canvas_h: int) -> tuple[int, int, int, int]:
    """Return (cx, cy, cw, ch) for a monitor on the canvas."""
    total_w, total_h, ox, oy = _monitor_bounds(monitors)
    scale_x = canvas_w / total_w
    scale_y = canvas_h / total_h
    cx = int((monitor["x"] - ox) * scale_x)
    cy = int((monitor["y"] - oy) * scale_y)
    cw = max(1, int(monitor["w"] * scale_x))
    ch = max(1, int(monitor["h"] * scale_y))
    return cx, cy, cw, ch


def slot_to_canvas_rect(slot_geo: dict, monitors: list[dict],
                         canvas_w: int, canvas_h: int) -> tuple[int, int, int, int]:
    """Return (cx, cy, cw, ch) for a slot's geometry on the canvas."""
    total_w, total_h, ox, oy = _monitor_bounds(monitors)
    scale_x = canvas_w / total_w
    scale_y = canvas_h / total_h
    cx = int((slot_geo["x"] - ox) * scale_x)
    cy = int((slot_geo["y"] - oy) * scale_y)
    cw = max(4, int(slot_geo["w"] * scale_x))
    ch = max(4, int(slot_geo["h"] * scale_y))
    return cx, cy, cw, ch


def _monitor_bounds(monitors: list[dict]) -> tuple[int, int, int, int]:
    """Return (total_w, total_h, origin_x, origin_y) for all monitors combined."""
    if not monitors:
        return 1920, 1080, 0, 0
    min_x = min(m["x"] for m in monitors)
    min_y = min(m["y"] for m in monitors)
    max_x = max(m["x"] + m["w"] for m in monitors)
    max_y = max(m["y"] + m["h"] for m in monitors)
    return max_x - min_x, max_y - min_y, min_x, min_y
