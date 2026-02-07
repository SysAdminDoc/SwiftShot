"""
SwiftShot Hotkey Manager
Uses a low-level keyboard hook (WH_KEYBOARD_LL) to intercept keys BEFORE
Windows processes them. This is the same approach Greenshot uses, and is
required because Windows 10/11 reserves PrintScreen for Snipping Tool,
making RegisterHotKey fail with error 1409.

The LL hook runs in the thread that installed it (which must pump messages),
and we use a signal bridge to dispatch callbacks to the Qt main thread.
"""

import sys
import ctypes
import ctypes.wintypes as wintypes
import threading

from PyQt5.QtCore import QObject, pyqtSignal

from logger import log


# Win32 constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
VK_SNAPSHOT = 0x2C
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12

# Modifier bit flags (our own, not Windows MOD_ flags)
MOD_NONE = 0
MOD_ALT = 1
MOD_CTRL = 2
MOD_SHIFT = 4

# Low-level keyboard hook struct
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]

HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_long,       # LRESULT return
    ctypes.c_int,        # nCode
    ctypes.c_uint,       # wParam (message type)
    ctypes.POINTER(KBDLLHOOKSTRUCT)  # lParam
)


class _HotkeyBridge(QObject):
    """Signal bridge to dispatch hotkey callbacks to the Qt main thread."""
    fired = pyqtSignal(str)  # combo string

    def __init__(self, callbacks):
        super().__init__()
        self._callbacks = callbacks  # {combo_str: callable}
        self.fired.connect(self._dispatch)

    def _dispatch(self, combo):
        cb = self._callbacks.get(combo)
        if cb:
            try:
                cb()
            except Exception as e:
                print(f"Hotkey callback error ({combo}): {e}")
                log.error(f"Hotkey callback error ({combo}): {e}")


class HotkeyManager:
    """
    Global hotkey manager using WH_KEYBOARD_LL low-level hook.
    Intercepts keys before Windows Snipping Tool can claim them.
    """

    def __init__(self):
        self._callbacks = {}   # combo_str -> callable
        self._bindings = {}    # (modifiers, vk) -> combo_str
        self._thread = None
        self._running = False
        self._hook = None
        self._bridge = None
        # Store the HOOKPROC so it doesn't get garbage collected
        self._hook_proc = None

    def register(self, key_combo, callback):
        """Register a global hotkey.
        key_combo: "Print", "Alt+Print", "Ctrl+Print", "Shift+Print"
        """
        if sys.platform != 'win32':
            return
        modifiers, vk = self._parse_combo(key_combo)
        if vk is None:
            log.warning(f"Could not parse hotkey: {key_combo}")
            return
        self._bindings[(modifiers, vk)] = key_combo
        self._callbacks[key_combo] = callback

    def _parse_combo(self, combo):
        parts = [p.strip() for p in combo.split('+')]
        VK_MAP = {
            'Print': VK_SNAPSHOT, 'PrintScreen': VK_SNAPSHOT, 'PrtSc': VK_SNAPSHOT,
            'F1': 0x70, 'F2': 0x71, 'F3': 0x72, 'F4': 0x73,
            'F5': 0x74, 'F6': 0x75, 'F7': 0x76, 'F8': 0x77,
            'F9': 0x78, 'F10': 0x79, 'F11': 0x7A, 'F12': 0x7B,
            'Escape': 0x1B, 'Space': 0x20, 'Enter': 0x0D,
        }
        modifiers = MOD_NONE
        vk = None
        for part in parts:
            low = part.lower()
            if low in ('alt', 'menu'):
                modifiers |= MOD_ALT
            elif low in ('ctrl', 'control'):
                modifiers |= MOD_CTRL
            elif low == 'shift':
                modifiers |= MOD_SHIFT
            elif part in VK_MAP:
                vk = VK_MAP[part]
            elif len(part) == 1 and part.isalpha():
                vk = ord(part.upper())
        return modifiers, vk

    def start(self):
        if sys.platform != 'win32' or not self._bindings:
            return
        self._bridge = _HotkeyBridge(self._callbacks)
        self._running = True
        self._thread = threading.Thread(target=self._hook_thread, daemon=True)
        self._thread.start()

    def _get_active_modifiers(self):
        """Check which modifier keys are currently held down."""
        # Use the cached user32 ref from the hook thread (set in _hook_thread)
        gas = self._user32.GetAsyncKeyState
        mods = MOD_NONE
        if gas(VK_LSHIFT) & 0x8000 or gas(VK_RSHIFT) & 0x8000:
            mods |= MOD_SHIFT
        if gas(VK_LCONTROL) & 0x8000 or gas(VK_RCONTROL) & 0x8000:
            mods |= MOD_CTRL
        if gas(VK_LMENU) & 0x8000 or gas(VK_RMENU) & 0x8000:
            mods |= MOD_ALT
        return mods

    def _hook_thread(self):
        """Install the low-level keyboard hook and pump messages."""
        # Use WinDLL with use_last_error for reliable error reporting,
        # and explicitly declare every function signature so ctypes
        # marshals arguments correctly (this is the fix for error 126).
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

        # --- Declare function signatures ---
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,       # idHook
            HOOKPROC,           # lpfn
            wintypes.HINSTANCE, # hMod
            wintypes.DWORD      # dwThreadId
        ]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p  # HHOOK

        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p,    # hhk
            ctypes.c_int,       # nCode
            ctypes.c_uint,      # wParam
            ctypes.POINTER(KBDLLHOOKSTRUCT)  # lParam
        ]
        user32.CallNextHookEx.restype = ctypes.c_long

        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL

        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND,
            wintypes.UINT, wintypes.UINT
        ]
        user32.GetMessageW.restype = wintypes.BOOL

        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]

        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short

        # Store user32 ref for use in modifier check and CallNextHookEx
        self._user32 = user32

        def ll_keyboard_proc(nCode, wParam, lParam):
            if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                vk = lParam.contents.vkCode
                if vk not in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT,
                              VK_CONTROL, VK_LCONTROL, VK_RCONTROL,
                              VK_MENU, VK_LMENU, VK_RMENU):
                    mods = self._get_active_modifiers()
                    combo = self._bindings.get((mods, vk))
                    if combo and self._bridge:
                        self._bridge.fired.emit(combo)
                        return 1  # Swallow the key

            return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        # Must keep a reference to prevent GC
        self._hook_proc = HOOKPROC(ll_keyboard_proc)

        # For WH_KEYBOARD_LL the hMod is effectively ignored on Vista+,
        # but SetWindowsHookExW still validates it's a loadable module.
        # Try multiple strategies:
        hmod = None
        for candidate in [
            lambda: kernel32.GetModuleHandleW(None),           # python.exe handle
            lambda: kernel32.GetModuleHandleW("python3.dll"),  # embedded python
            lambda: kernel32.GetModuleHandleW("user32.dll"),   # always loaded
            lambda: wintypes.HINSTANCE(user32._handle),        # ctypes internal
        ]:
            try:
                h = candidate()
                if h:
                    hmod = h
                    break
            except Exception:
                continue

        if not hmod:
            hmod = wintypes.HINSTANCE(0)

        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_proc,
            hmod,
            0
        )

        if not self._hook:
            err = ctypes.get_last_error()
            log.warning(f"Could not install keyboard hook (error {err})")
            return

        # Message pump -- required for LL hooks to work
        msg = wintypes.MSG()
        while self._running:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result == 0 or result == -1:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Cleanup
        user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            try:
                # Post WM_QUIT to break the message loop
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread.ident, 0x0012, 0, 0
                )
            except Exception:
                pass
