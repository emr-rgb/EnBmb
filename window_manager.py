# ============================================================
#  EnB Multibox Manager — window_manager.py
#  Platform shim: imports the correct backend based on OS.
# ============================================================

import sys

if sys.platform == "win32":
    from window_manager_windows import *  # noqa: F401, F403
else:
    from window_manager_linux import *    # noqa: F401, F403
    # gui_main.py uses these Linux-internal helpers directly in X11-specific code
    # paths. Explicitly re-export them so the top-level import keeps working.
    # These will be removed from the gui_main import when the platform-branch
    # merge of gui_main is done in Phase 2.
    from window_manager_linux import _is_wine_pid, _run  # noqa: F401
