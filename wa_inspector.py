import win32gui
import win32con
from pywinauto import Desktop
import time

pyautogui_available = False
try:
    import pyautogui
    pyautogui_available = True
except ImportError:
    pass


def inspect_window(hwnd):
    rect             = win32gui.GetWindowRect(hwnd)
    left, top, right, bottom = rect
    print(f"\n📐 Window rect  : left={left} top={top} right={right} bottom={bottom}")
    print(f"   Size          : {right-left} x {bottom-top}\n")

    win32gui.ShowWindow(hwnd, 9)
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 100, 100, 1100, 750, win32con.SWP_SHOWWINDOW)
    time.sleep(1)

    app = Desktop(backend="uia").window(handle=hwnd)

    # ── DataItem chat rows ────────────────────────────────────────────────────
    items = app.descendants(control_type="DataItem")
    print(f"✅ Found {len(items)} DataItems (chat rows)")
    print("=" * 60)
    print("🔍 FIRST 15 DataItems:")
    print("=" * 60)

    for i, item in enumerate(items[:15]):
        try:
            title = item.window_text().strip()
            print(f"\n  ── DataItem [{i}] ──────────────────────────")
            print(f"     Title  : '{title[:80]}'")

            # Child Text elements
            children = item.descendants(control_type="Text")
            texts    = [c.window_text().strip() for c in children if c.window_text().strip()]
            print(f"     Texts  : {texts[:6]}")

            # Child Buttons
            btns     = item.descendants(control_type="Button")
            btn_txts = [b.window_text().strip() for b in btns if b.window_text().strip()]
            if btn_txts:
                print(f"     Buttons: {btn_txts[:4]}")

            # Rectangle
            try:
                r = item.rectangle()
                print(f"     Rect   : left={r.left} top={r.top} w={r.right-r.left} h={r.bottom-r.top}")
            except Exception:
                pass

        except Exception as e:
            print(f"  ⚠️ Error on DataItem [{i}]: {e}")

    # ── Edit controls (message boxes) ────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🔍 ALL EDIT CONTROLS (potential message boxes):")
    print("=" * 60)
    try:
        edits = app.descendants(control_type="Edit")
        print(f"   Found {len(edits)} Edit controls\n")
        for i, e in enumerate(edits):
            try:
                r   = e.rectangle()
                w   = r.right  - r.left
                h   = r.bottom - r.top
                cx  = r.left   + w // 2
                cy  = r.top    + h // 2
                vis = e.is_visible()
                ena = e.is_enabled()
                txt = e.window_text()[:50]
                flag = " ← 🎯 LIKELY MSGBOX" if (vis and ena and w > 200 and h < 60 and cx > 600) else ""
                print(f"   Edit[{i}]: size={w}x{h} center=({cx},{cy}) "
                      f"vis={vis} ena={ena} text='{txt}'{flag}")
            except Exception as ex:
                print(f"   Edit[{i}]: error — {ex}")
    except Exception as ex:
        print(f"   ⚠️ Edit scan failed: {ex}")

    # ── Document controls ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("🔍 ALL DOCUMENT CONTROLS:")
    print("=" * 60)
    try:
        docs = app.descendants(control_type="Document")
        print(f"   Found {len(docs)} Document controls\n")
        for i, d in enumerate(docs):
            try:
                r   = d.rectangle()
                w   = r.right  - r.left
                h   = r.bottom - r.top
                cx  = r.left   + w // 2
                cy  = r.top    + h // 2
                vis = d.is_visible()
                ena = d.is_enabled()
                flag = " ← 🎯 LIKELY MSGBOX" if (vis and ena and w > 200 and h < 60 and cx > 600) else ""
                print(f"   Doc[{i}]: size={w}x{h} center=({cx},{cy}) "
                      f"vis={vis} ena={ena}{flag}")
            except Exception as ex:
                print(f"   Doc[{i}]: error — {ex}")
    except Exception as ex:
        print(f"   ⚠️ Document scan failed: {ex}")

    # ── Control type summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("📊 CONTROL TYPE COUNTS (top-level descendants):")
    print("=" * 60)
    from collections import Counter
    try:
        all_ctrl = app.descendants()
        counts   = Counter(c.element_info.control_type for c in all_ctrl)
        for ctype, cnt in counts.most_common(15):
            print(f"   {ctype:<25} : {cnt}")
    except Exception as ex:
        print(f"   ⚠️ Count failed: {ex}")


if __name__ == "__main__":
    print("=" * 60)
    print("🛡️  ZULU WhatsApp UI Inspector v2")
    print("   Keep WhatsApp open with chat list visible!")
    print("=" * 60)

    hwnd = win32gui.FindWindow(None, "WhatsApp")
    if not hwnd:
        print("❌ WhatsApp not found! Open it first.")
        exit()

    inspect_window(hwnd)

    print("\n✅ Inspection complete!")
    print("📋 Paste this output to Perplexity to diagnose any issues.")
    print("=" * 60)
