# Test helper: print the NAME of the X cursor currently under the pointer (libXfixes via ctypes) — how the smoke tests tell a resize arrow from a hand.
# usage: python3 tests/cursorname.py :99
import ctypes, ctypes.util, sys
class Img(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short), ("width", ctypes.c_ushort), ("height", ctypes.c_ushort),
                ("xhot", ctypes.c_ushort), ("yhot", ctypes.c_ushort), ("serial", ctypes.c_ulong),
                ("pixels", ctypes.POINTER(ctypes.c_ulong)), ("atom", ctypes.c_ulong), ("name", ctypes.c_char_p)]
x11 = ctypes.CDLL("libX11.so.6"); xf = ctypes.CDLL("libXfixes.so.3")
x11.XOpenDisplay.restype = ctypes.c_void_p
xf.XFixesGetCursorImage.restype = ctypes.POINTER(Img)
xf.XFixesGetCursorImage.argtypes = [ctypes.c_void_p]
dpy = x11.XOpenDisplay(sys.argv[1].encode())
im = xf.XFixesGetCursorImage(dpy).contents
n = im.pixels
print(im.name.decode() if im.name else "?", f"{im.width}x{im.height}", f"hot={im.xhot},{im.yhot}")
