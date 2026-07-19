/*
 * winresize.c — Move and resize a Wine window by Win32 title.
 *
 * xdotool windowsize/windowmove have no effect on Wine windows; SetWindowPos
 * is the only path that works. This tool is called by enbmb via Wine under
 * the same WINEPREFIX as the target window (FindWindow is prefix-scoped).
 *
 * Usage: winresize.exe <title> <x> <y> <w> <h>
 *
 * Compile (Linux cross-compiler):
 *   i686-w64-mingw32-gcc -o winresize.exe winresize.c -luser32 -mwindows
 */

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char *argv[]) {
    if (argc != 6) {
        fprintf(stderr, "Usage: winresize <title> <x> <y> <w> <h>\n");
        return 1;
    }

    const char *title = argv[1];
    int x = atoi(argv[2]);
    int y = atoi(argv[3]);
    int w = atoi(argv[4]);
    int h = atoi(argv[5]);

    HWND hwnd = FindWindow(NULL, title);
    if (!hwnd) {
        fprintf(stderr, "Window not found: %s\n", title);
        return 1;
    }

    SetWindowPos(hwnd, NULL, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE);
    return 0;
}
