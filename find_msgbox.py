# Save as: find_exact_msgbox.py
# Run: python find_exact_msgbox.py

import time
import win32gui
import win32con
from pywinauto import Desktop

print("Opening WhatsApp and scanning in 3 seconds...")
print("Make sure a chat is OPEN in WhatsApp before running this!")
time.sleep(3)

hwnd = win32gui.FindWindow(None, "WhatsApp")
if not hwnd:
    print("❌ WhatsApp not found!")
    exit()

win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 100, 100, 1100, 750, win32con.SWP_SHOWWINDOW)
time.sleep(1)

rect = win32gui.GetWindowRect(hwnd)
print(f"Window rect: {rect}")
print(f"Window size: {rect[2]-rect[0]} x {rect[3]-rect[1]}")
print()

app = Desktop(backend="uia").window(handle=hwnd)
print("Scanning ALL controls...")
print()

for ctrl_type in ["Edit", "Document", "Text", "Custom"]:
    try:
        items = app.descendants(control_type=ctrl_type)
        for e in items:
            try:
                r = e.rectangle()
                w = r.right - r.left
                h = r.bottom - r.top
                cx = r.left + w // 2
                cy = r.top + h // 2
                print(f"  [{ctrl_type}] w={w} h={h} cx={cx} cy={cy} | visible={e.is_visible()} enabled={e.is_enabled()}")
            except:
                pass
    except:
        pass