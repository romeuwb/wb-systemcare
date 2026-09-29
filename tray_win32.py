# -*- coding: utf-8 -*-
"""
tray_win32.py — System tray usando Win32 puro via ctypes.

Arquitetura correta:
  - Thread dedicada cria uma janela oculta (HWND) e roda sua própria
    message loop (GetMessageW), garantindo que WM_TRAYICON seja entregue.
  - Callbacks de menu/clique são despachados de volta para a thread tkinter
    via `root.after(0, callback)`, mantendo thread-safety.
  - Sem pystray, sem PIL para o tray — apenas ctypes + win32.
"""

import ctypes
import ctypes.wintypes as wt
import os
import threading
import logging

logger = logging.getLogger(__name__)

# ── Win32 constantes ──────────────────────────────────────────────────────────
WM_USER          = 0x0400
WM_TRAYICON      = WM_USER + 20
WM_DESTROY       = 0x0002
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP     = 0x0205
WM_COMMAND       = 0x0111
WM_APP_CALLBACK  = WM_USER + 21   # mensagem interna para parar o loop

NIM_ADD    = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002

NIF_MESSAGE = 0x00000001
NIF_ICON    = 0x00000002
NIF_TIP     = 0x00000004
NIF_INFO    = 0x00000010

NIIF_INFO    = 0x00000001
NIIF_WARNING = 0x00000002
NIIF_NOSOUND = 0x00000010

MF_STRING    = 0x00000000
MF_SEPARATOR = 0x00000800
MF_GRAYED    = 0x00000001

TPM_BOTTOMALIGN = 0x0020
TPM_RIGHTALIGN  = 0x0008
TPM_RETURNCMD   = 0x0100

CS_HREDRAW   = 0x0002
CS_VREDRAW   = 0x0001
WS_OVERLAPPED = 0x00000000
CW_USEDEFAULT = 0x80000000

MENU_ID_BASE = 2000

# ── Win32 API ─────────────────────────────────────────────────────────────────
shell32  = ctypes.windll.shell32
user32   = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Declara tipos corretos para DefWindowProcW em 64-bit
user32.DefWindowProcW.restype  = ctypes.c_ssize_t
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]

WNDPROCTYPE = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM
)


# ── NOTIFYICONDATA ────────────────────────────────────────────────────────────
class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize",           wt.DWORD),
        ("hWnd",             wt.HWND),
        ("uID",              wt.UINT),
        ("uFlags",           wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon",            wt.HICON),
        ("szTip",            wt.WCHAR * 128),
        ("dwState",          wt.DWORD),
        ("dwStateMask",      wt.DWORD),
        ("szInfo",           wt.WCHAR * 256),
        ("uTimeoutVersion",  wt.UINT),
        ("szInfoTitle",      wt.WCHAR * 64),
        ("dwInfoFlags",      wt.DWORD),
    ]


# ── WNDCLASSEX ────────────────────────────────────────────────────────────────
class WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize",        wt.UINT),
        ("style",         wt.UINT),
        ("lpfnWndProc",   WNDPROCTYPE),
        ("cbClsExtra",    ctypes.c_int),
        ("cbWndExtra",    ctypes.c_int),
        ("hInstance",     wt.HINSTANCE),
        ("hIcon",         wt.HICON),
        ("hCursor",       wt.HANDLE),
        ("hbrBackground", wt.HBRUSH),
        ("lpszMenuName",  wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
        ("hIconSm",       wt.HICON),
    ]


# ── POINT ─────────────────────────────────────────────────────────────────────
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


# ── TrayIcon ──────────────────────────────────────────────────────────────────
class TrayIcon:
    """
    Ícone de bandeja do sistema com janela Win32 oculta em thread dedicada.

    Parâmetros
    ----------
    root        : tk.Tk
    icon_path   : caminho do .ico
    tooltip     : texto do tooltip (máx 127 chars)
    menu_items  : [(label, callback), None para separador, ...]
    on_restore  : chamado ao duplo-clique
    """

    def __init__(self, root, icon_path: str, tooltip: str,
                 menu_items: list, on_restore=None):
        self._root       = root
        self._icon_path  = icon_path
        self._tooltip    = tooltip[:127]
        self._menu_items = menu_items
        self._on_restore = on_restore

        self._hwnd       = None
        self._hicon      = None
        self._nid        = None
        self._thread     = None
        self._ready      = threading.Event()
        self._stopped    = False

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def show(self):
        """Inicia a thread do tray e aguarda a janela oculta estar pronta."""
        if self._thread and self._thread.is_alive():
            return
        self._stopped = False
        self._ready.clear()
        self._thread = threading.Thread(target=self._tray_thread,
                                        daemon=True, name="TrayThread")
        self._thread.start()
        self._ready.wait(timeout=3.0)   # aguarda hwnd estar pronto

    def hide(self):
        """Remove o ícone e encerra a thread."""
        self._stopped = True
        if self._hwnd:
            try:
                # Remove o ícone antes de destruir
                if self._nid:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                # Posta WM_DESTROY para encerrar o GetMessageW loop
                user32.PostMessageW(self._hwnd, WM_DESTROY, 0, 0)
            except Exception:
                pass

    def show_balloon(self, title: str, message: str, flag=NIIF_INFO):
        """Exibe notificação balloon."""
        if not self._nid or not self._hwnd:
            return
        try:
            nid = NOTIFYICONDATA()
            nid.cbSize      = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd        = self._hwnd
            nid.uID         = 1
            nid.uFlags      = NIF_INFO
            nid.szInfo      = message[:255]
            nid.szInfoTitle = title[:63]
            nid.dwInfoFlags = flag | NIIF_NOSOUND
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
        except Exception as e:
            logger.debug(f"balloon: {e}")

    # ── Thread do tray ────────────────────────────────────────────────────────

    def _tray_thread(self):
        """Roda na thread dedicada: cria janela oculta + message loop."""
        try:
            hinstance = kernel32.GetModuleHandleW(None)
            class_name = f"WBTray_{id(self)}"

            # Referência forte ao WndProc para evitar GC
            self._wndproc_ref = WNDPROCTYPE(self._wnd_proc)

            wc = WNDCLASSEX()
            wc.cbSize        = ctypes.sizeof(WNDCLASSEX)
            wc.style         = CS_HREDRAW | CS_VREDRAW
            wc.lpfnWndProc   = self._wndproc_ref
            wc.hInstance     = hinstance
            wc.lpszClassName = class_name

            if not user32.RegisterClassExW(ctypes.byref(wc)):
                logger.error("TrayIcon: RegisterClassExW falhou")
                self._ready.set()
                return

            self._hwnd = user32.CreateWindowExW(
                0, class_name, "WBTrayWindow",
                WS_OVERLAPPED, 0, 0, 0, 0,
                None, None, hinstance, None
            )

            if not self._hwnd:
                logger.error("TrayIcon: CreateWindowExW falhou")
                self._ready.set()
                return

            # Carrega ícone
            self._hicon = self._load_icon()

            # Registra o ícone no tray
            self._nid = NOTIFYICONDATA()
            self._nid.cbSize           = ctypes.sizeof(NOTIFYICONDATA)
            self._nid.hWnd             = self._hwnd
            self._nid.uID              = 1
            self._nid.uFlags           = NIF_ICON | NIF_MESSAGE | NIF_TIP
            self._nid.uCallbackMessage = WM_TRAYICON
            self._nid.hIcon            = self._hicon
            self._nid.szTip            = self._tooltip

            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._nid))

            # Sinaliza que está pronto
            self._ready.set()

            # Message loop dedicada — bloqueia até WM_DESTROY
            msg = wt.MSG()
            while not self._stopped:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        except Exception as e:
            logger.error(f"TrayIcon thread: {e}")
            self._ready.set()

    # ── WndProc da janela oculta ──────────────────────────────────────────────

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            event = lparam & 0xFFFF
            if event == WM_LBUTTONDBLCLK:
                self._dispatch(self._on_restore)
            elif event == WM_RBUTTONUP:
                self._show_menu()
            return 0

        if msg == WM_DESTROY:
            try:
                if self._nid:
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            except Exception:
                pass
            user32.PostQuitMessage(0)
            return 0

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ── Menu de contexto ──────────────────────────────────────────────────────

    def _show_menu(self):
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return

        cmd_map = {}
        cmd_id  = MENU_ID_BASE

        for item in self._menu_items:
            if item is None:
                user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            else:
                label, cb = item
                user32.AppendMenuW(hmenu, MF_STRING, cmd_id, label)
                cmd_map[cmd_id] = cb
                cmd_id += 1

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        # Necessário para o menu fechar corretamente
        user32.SetForegroundWindow(self._hwnd)

        cmd = user32.TrackPopupMenu(
            hmenu,
            TPM_BOTTOMALIGN | TPM_RIGHTALIGN | TPM_RETURNCMD,
            pt.x, pt.y, 0, self._hwnd, None
        )
        user32.DestroyMenu(hmenu)
        user32.PostMessageW(self._hwnd, 0, 0, 0)  # flush

        if cmd and cmd in cmd_map:
            self._dispatch(cmd_map[cmd])

    # ── Despacha callback para a thread tkinter ───────────────────────────────

    def _dispatch(self, cb):
        """Executa o callback na thread tkinter via root.after()."""
        if cb and self._root:
            try:
                self._root.after(0, cb)
            except Exception:
                pass

    # ── Carrega ícone ─────────────────────────────────────────────────────────

    def _load_icon(self):
        if self._icon_path and os.path.exists(self._icon_path):
            h = user32.LoadImageW(
                None,
                self._icon_path,
                1,      # IMAGE_ICON
                32, 32,
                0x0010  # LR_LOADFROMFILE
            )
            if h:
                return h
        # Fallback: ícone padrão do sistema (IDI_APPLICATION = 32512)
        return user32.LoadIconW(None, ctypes.cast(32512, wt.LPCWSTR))
