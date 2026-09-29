# -*- coding: utf-8 -*-
"""
Módulo de restauração do tema padrão do Windows.
Versão : 1.3

Correções:
  - Cor de destaque: remove personalização → Windows escolhe automaticamente
  - Ponteiro: tamanho 1 (menor/padrão), cor padrão Windows, esquema Aero
  - Papel de parede: aplica o wallpaper padrão Windows (Windows claro 1 / img0.jpg)
  - Histórico de navegação: Chrome, Edge, Firefox, Internet Explorer
"""

import os
import ctypes
import winreg
import subprocess
import logging
import shutil

logger = logging.getLogger(__name__)

# ── Constantes Win32 ──────────────────────────────────────────────────────────
SPI_SETDESKWALLPAPER     = 0x0014
SPI_SETSCREENSAVEACTIVE  = 0x0011
SPI_SETSCREENSAVETIMEOUT = 0x000F
SPI_SETCURSORS           = 0x0057
SPI_SETMOUSE             = 0x0004
SPI_SETMOUSESPEED        = 0x0071
SPIF_UPDATEINIFILE       = 0x01
SPIF_SENDCHANGE          = 0x02

REG_DESKTOP     = r"Control Panel\Desktop"
REG_COLORS      = r"Control Panel\Colors"
REG_CURSORS     = r"Control Panel\Cursors"
REG_PERSONALIZE = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
REG_ACCENT      = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
REG_CDM         = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
REG_LOCK_POLICY = r"Software\Policies\Microsoft\Windows\Personalization"

# ── Papel de parede padrão Windows (Windows claro 1 / img0) ──────────────────
_WALLPAPER_PATHS = [
    r"C:\Windows\Web\Wallpaper\Windows\img0.jpg",       # Windows 10/11 padrão
    r"C:\Windows\Web\Wallpaper\Windows\img19.jpg",      # Windows 11 claro
    r"C:\Windows\Web\Wallpaper\Theme1\img1.jpg",
    r"C:\Windows\Web\Wallpaper\Theme2\img0.jpg",
    r"C:\Windows\Web\4K\Wallpaper\Windows\img0_1920x1200.jpg",
]

# ── Cores padrão Windows 10/11 ────────────────────────────────────────────────
DEFAULT_COLORS = {
    "ActiveBorder":          "180 180 180",
    "ActiveTitle":           "153 180 209",
    "AppWorkSpace":          "171 171 171",
    "Background":            "0 0 0",
    "ButtonAlternativeFace": "0 0 0",
    "ButtonDkShadow":        "105 105 105",
    "ButtonFace":            "240 240 240",
    "ButtonHilight":         "255 255 255",
    "ButtonLight":           "227 227 227",
    "ButtonShadow":          "160 160 160",
    "ButtonText":            "0 0 0",
    "GradientActiveTitle":   "185 209 234",
    "GradientInactiveTitle": "215 228 242",
    "GrayText":              "109 109 109",
    "Hilight":               "0 120 215",
    "HilightText":           "255 255 255",
    "HotTrackingColor":      "0 102 204",
    "InactiveBorder":        "244 247 252",
    "InactiveTitle":         "191 205 219",
    "InactiveTitleText":     "0 0 0",
    "InfoText":              "0 0 0",
    "InfoWindow":            "255 255 225",
    "Menu":                  "240 240 240",
    "MenuBar":               "240 240 240",
    "MenuHilight":           "0 120 215",
    "MenuText":              "0 0 0",
    "Scrollbar":             "200 200 200",
    "TitleText":             "0 0 0",
    "Window":                "255 255 255",
    "WindowFrame":           "100 100 100",
    "WindowText":            "0 0 0",
}

# ── Cursores Aero padrão (tamanho 1 = menor = padrão) ────────────────────────
DEFAULT_CURSORS = {
    "Arrow":       "%SystemRoot%\\cursors\\aero_arrow.cur",
    "Hand":        "%SystemRoot%\\cursors\\aero_link.cur",
    "Help":        "%SystemRoot%\\cursors\\aero_helpsel.cur",
    "AppStarting": "%SystemRoot%\\cursors\\aero_working.ani",
    "Wait":        "%SystemRoot%\\cursors\\aero_busy.ani",
    "NWPen":       "%SystemRoot%\\cursors\\aero_pen.cur",
    "No":          "%SystemRoot%\\cursors\\aero_unavail.cur",
    "SizeNS":      "%SystemRoot%\\cursors\\aero_ns.cur",
    "SizeWE":      "%SystemRoot%\\cursors\\aero_ew.cur",
    "SizeNWSE":    "%SystemRoot%\\cursors\\aero_nwse.cur",
    "SizeNESW":    "%SystemRoot%\\cursors\\aero_nesw.cur",
    "SizeAll":     "%SystemRoot%\\cursors\\aero_move.cur",
    "UpArrow":     "%SystemRoot%\\cursors\\aero_up.cur",
    "Cross":       "",
    "IBeam":       "",
}

# Localização padrão da tela de bloqueio
_LOCK_DEFAULT_PATHS = [
    r"C:\Windows\Web\Screen\img100.jpg",
    r"C:\Windows\Web\Screen\img0.jpg",
    r"C:\Windows\Web\Wallpaper\Windows\img0.jpg",
]


# ── Auxiliares ────────────────────────────────────────────────────────────────

def _reg_set(hive, key_path, name, value, reg_type=winreg.REG_SZ):
    try:
        with winreg.OpenKey(hive, key_path, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.SetValueEx(k, name, 0, reg_type, value)
        return True
    except Exception as e:
        logger.error(f"Registro [{key_path}] {name}: {e}")
        return False


def _reg_delete_value(hive, key_path, name):
    try:
        with winreg.OpenKey(hive, key_path, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _broadcast():
    try:
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Policy", 0x0002, 5000, None)
    except Exception:
        pass


# ── Papel de parede ───────────────────────────────────────────────────────────

def restore_wallpaper(callback=None):
    """
    Aplica o papel de parede padrão do Windows (Windows claro 1 / img0.jpg).
    Se não encontrar, remove o papel de parede (fundo sólido).
    """
    try:
        if callback: callback("Configurando papel de parede padrão...")

        # Procura o wallpaper padrão do Windows
        wallpaper_path = ""
        for p in _WALLPAPER_PATHS:
            if os.path.exists(p):
                wallpaper_path = p
                break

        if wallpaper_path:
            # Aplica via API do Windows
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETDESKWALLPAPER, 0, wallpaper_path,
                SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
            )
            _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP,
                     "Wallpaper", wallpaper_path)
            _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP,
                     "WallpaperStyle", "10")   # 10 = preenchimento
            _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP,
                     "TileWallpaper", "0")
            if callback: callback(f"✔ Papel de parede definido: {os.path.basename(wallpaper_path)}")
        else:
            # Sem wallpaper padrão encontrado → fundo preto sólido
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_SETDESKWALLPAPER, 0, "",
                SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
            )
            _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP, "Wallpaper", "")
            if callback: callback("✔ Papel de parede removido (wallpaper padrão não encontrado).")

        return True
    except Exception as e:
        logger.error(f"restore_wallpaper: {e}")
        if callback: callback(f"✘ Erro no papel de parede: {e}")
        return False


# ── Proteção de tela ──────────────────────────────────────────────────────────

def restore_screensaver(callback=None):
    try:
        if callback: callback("Desativando proteção de tela...")
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETSCREENSAVEACTIVE, 0, None, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETSCREENSAVETIMEOUT, 0, None, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP, "ScreenSaveActive",    "0")
        _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP, "ScreenSaverIsSecure", "0")
        _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP, "SCRNSAVE.EXE",        "")
        _reg_set(winreg.HKEY_CURRENT_USER, REG_DESKTOP, "ScreenSaveTimeOut",   "0")
        if callback: callback("✔ Proteção de tela desativada.")
        return True
    except Exception as e:
        if callback: callback(f"✘ {e}")
        return False


# ── Tela de bloqueio ──────────────────────────────────────────────────────────

def restore_lock_screen(callback=None):
    try:
        if callback: callback("Restaurando tela de bloqueio...")
        _reg_set(winreg.HKEY_CURRENT_USER, REG_CDM,
                 "RotatingLockScreenEnabled",        1, winreg.REG_DWORD)
        _reg_set(winreg.HKEY_CURRENT_USER, REG_CDM,
                 "RotatingLockScreenOverlayEnabled", 1, winreg.REG_DWORD)
        _reg_set(winreg.HKEY_CURRENT_USER, REG_CDM,
                 "SubscribedContent-338387Enabled",  1, winreg.REG_DWORD)
        _reg_delete_value(winreg.HKEY_CURRENT_USER,  REG_LOCK_POLICY, "LockScreenImage")
        _reg_delete_value(winreg.HKEY_LOCAL_MACHINE, REG_LOCK_POLICY, "LockScreenImage")

        # Limpa cache de imagens personalizadas
        local_app = os.environ.get("LOCALAPPDATA", "")
        for cache_dir in [
            os.path.join(local_app, "Packages\\Microsoft.Windows.ContentDeliveryManager_"
                         "cw5n1h2txyewy\\LocalState\\Assets"),
            os.path.join(local_app, "Microsoft\\Windows\\LockScreen"),
        ]:
            if os.path.isdir(cache_dir):
                for f in os.listdir(cache_dir):
                    try: os.remove(os.path.join(cache_dir, f))
                    except Exception: pass

        _broadcast()
        if callback: callback("✔ Tela de bloqueio restaurada.")
        return True
    except Exception as e:
        if callback: callback(f"✘ {e}")
        return False


# ── Cursores ──────────────────────────────────────────────────────────────────

def restore_cursors(callback=None):
    """
    Restaura os cursores Aero padrão com tamanho 1 (menor = padrão do Windows).
    Remove personalização de cor e tamanho.
    """
    try:
        if callback: callback("Restaurando cursores do mouse...")

        # Restaura esquema de cursores
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_CURSORS, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Windows Default")
            for name, path in DEFAULT_CURSORS.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_EXPAND_SZ, path)

        # Tamanho do cursor: 32 = padrão (menor).
        # O valor é armazenado em HKCU\Software\Microsoft\Accessibility
        _reg_set(winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Accessibility",
                 "CursorSize", 1, winreg.REG_DWORD)

        # Remove personalização de cor do ponteiro (Windows 11)
        # 0 = sem fill/cor personalizada
        for val in ("CursorColor", "CursorType"):
            _reg_delete_value(winreg.HKEY_CURRENT_USER,
                              r"Software\Microsoft\Accessibility", val)

        # Remove tamanho aumentado via política
        _reg_delete_value(winreg.HKEY_CURRENT_USER,
                          r"Control Panel\Cursors", "CursorBaseSize")

        # Aplica imediatamente
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETCURSORS, 0, None, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)

        if callback: callback("✔ Cursores restaurados (tamanho padrão, sem cor personalizada).")
        return True
    except Exception as e:
        logger.error(f"restore_cursors: {e}")
        if callback: callback(f"✘ Erro nos cursores: {e}")
        return False


# ── Cores e cor de destaque ───────────────────────────────────────────────────

def restore_colors(callback=None):
    """
    Restaura as cores do sistema.
    Cor de destaque: remove personalização → Windows escolhe automaticamente.
    """
    try:
        if callback: callback("Restaurando cores do sistema...")

        # Cores de janelas
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_COLORS, 0,
                            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY) as k:
            for name, val in DEFAULT_COLORS.items():
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)

        # Modo claro para apps e sistema
        _reg_set(winreg.HKEY_CURRENT_USER, REG_PERSONALIZE,
                 "AppsUseLightTheme",    1, winreg.REG_DWORD)
        _reg_set(winreg.HKEY_CURRENT_USER, REG_PERSONALIZE,
                 "SystemUsesLightTheme", 1, winreg.REG_DWORD)

        # Cor de destaque: "Automática" (Windows escolhe baseado no wallpaper)
        # AccentColorMenu = 0 remove a preferência manual
        # StartColorMenu  = 0 idem
        _reg_set(winreg.HKEY_CURRENT_USER, REG_PERSONALIZE,
                 "ColorPrevalence", 0, winreg.REG_DWORD)  # 0 = não mostrar cor em barras
        _reg_delete_value(winreg.HKEY_CURRENT_USER, REG_ACCENT, "AccentColor")
        _reg_delete_value(winreg.HKEY_CURRENT_USER, REG_ACCENT, "AccentColorMenu")
        _reg_delete_value(winreg.HKEY_CURRENT_USER, REG_ACCENT, "StartColorMenu")

        # Desativa "mostrar cor de destaque na barra de tarefas" (parece mais limpo)
        _reg_set(winreg.HKEY_CURRENT_USER, REG_PERSONALIZE,
                 "EnableTransparency", 1, winreg.REG_DWORD)

        _broadcast()
        if callback: callback("✔ Cores restauradas (destaque automático pelo Windows).")
        return True
    except Exception as e:
        logger.error(f"restore_colors: {e}")
        if callback: callback(f"✘ Erro nas cores: {e}")
        return False


# ── Tema padrão ───────────────────────────────────────────────────────────────

def apply_default_windows_theme(callback=None):
    try:
        if callback: callback("Aplicando tema padrão do Windows...")
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        theme = os.path.join(system_root, "resources", "Themes", "aero.theme")
        if os.path.exists(theme):
            os.startfile(theme)
            if callback: callback("✔ Tema padrão aplicado.")
            return True
        if callback: callback("⚠ aero.theme não encontrado.")
        return False
    except Exception as e:
        if callback: callback(f"⚠ {e}")
        return False


# ── Histórico de navegação ────────────────────────────────────────────────────

def clear_browser_history(callback=None):
    """
    Limpa histórico de navegação dos principais browsers:
    Chrome, Edge (Chromium), Firefox, Internet Explorer.
    Opera não tem instalação fixa, mas tenta os caminhos padrão.
    """
    profile = os.environ.get("USERPROFILE", os.path.expanduser("~"))
    local   = os.environ.get("LOCALAPPDATA",  os.path.join(profile, "AppData", "Local"))
    roaming = os.environ.get("APPDATA",        os.path.join(profile, "AppData", "Roaming"))
    deleted = 0
    errors  = 0

    def _del_file(path):
        nonlocal deleted, errors
        try:
            if os.path.isfile(path):
                os.remove(path)
                deleted += 1
        except Exception as e:
            errors += 1
            logger.debug(f"Não removeu {path}: {e}")

    def _del_dir_contents(path):
        """Remove conteúdo de um diretório sem remover o diretório em si."""
        nonlocal deleted, errors
        if not os.path.isdir(path):
            return
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            try:
                if os.path.isfile(full):
                    os.remove(full)
                    deleted += 1
                elif os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
                    deleted += 1
            except Exception as e:
                errors += 1
                logger.debug(f"Não removeu {full}: {e}")

    # ── Google Chrome ─────────────────────────────────────────────────────────
    if callback: callback("Limpando Chrome...")
    chrome_base = os.path.join(local, "Google", "Chrome", "User Data")
    for profile_dir in ["Default"] + [f"Profile {i}" for i in range(1, 6)]:
        chrome_profile = os.path.join(chrome_base, profile_dir)
        for item in ["History", "History-journal", "Visited Links",
                     "Top Sites", "Top Sites-journal",
                     "Thumbnails", "Thumbnails-journal",
                     os.path.join("Cache", "Cache_Data"),
                     "Code Cache", "GPUCache"]:
            full = os.path.join(chrome_profile, item)
            if os.path.isdir(full):
                _del_dir_contents(full)
            else:
                _del_file(full)

    # ── Microsoft Edge (Chromium) ─────────────────────────────────────────────
    if callback: callback("Limpando Edge...")
    edge_base = os.path.join(local, "Microsoft", "Edge", "User Data")
    for profile_dir in ["Default"] + [f"Profile {i}" for i in range(1, 6)]:
        edge_profile = os.path.join(edge_base, profile_dir)
        for item in ["History", "History-journal", "Visited Links",
                     "Top Sites", "Top Sites-journal",
                     os.path.join("Cache", "Cache_Data"),
                     "Code Cache", "GPUCache"]:
            full = os.path.join(edge_profile, item)
            if os.path.isdir(full):
                _del_dir_contents(full)
            else:
                _del_file(full)

    # ── Mozilla Firefox ───────────────────────────────────────────────────────
    if callback: callback("Limpando Firefox...")
    firefox_base = os.path.join(roaming, "Mozilla", "Firefox", "Profiles")
    if os.path.isdir(firefox_base):
        for prof in os.listdir(firefox_base):
            prof_path = os.path.join(firefox_base, prof)
            if not os.path.isdir(prof_path):
                continue
            for item in ["places.sqlite", "places.sqlite-wal", "places.sqlite-shm",
                         "favicons.sqlite", "favicons.sqlite-wal",
                         "cookies.sqlite", "cookies.sqlite-wal",
                         "formhistory.sqlite",
                         os.path.join("cache2", "entries")]:
                full = os.path.join(prof_path, item)
                if os.path.isdir(full):
                    _del_dir_contents(full)
                else:
                    _del_file(full)

    # ── Internet Explorer / Windows legado ────────────────────────────────────
    if callback: callback("Limpando Internet Explorer/Windows...")
    ie_paths = [
        os.path.join(local,   "Microsoft", "Windows", "INetCache"),
        os.path.join(local,   "Microsoft", "Windows", "WebCache"),
        os.path.join(roaming, "Microsoft", "Windows", "Cookies"),
        os.path.join(local,   "Microsoft", "Windows", "History"),
        os.path.join(local,   "Microsoft", "Windows", "Temporary Internet Files"),
    ]
    for p in ie_paths:
        _del_dir_contents(p)

    # ── Opera (padrão) ────────────────────────────────────────────────────────
    opera_path = os.path.join(roaming, "Opera Software", "Opera Stable")
    if os.path.isdir(opera_path):
        if callback: callback("Limpando Opera...")
        for item in ["History", "History-journal", "Visited Links"]:
            _del_file(os.path.join(opera_path, item))

    msg = f"✔ Histórico limpo: {deleted} item(ns) removido(s)"
    if errors:
        msg += f" ({errors} não removido(s) — em uso ou sem permissão)"
    if callback: callback(msg)
    return deleted > 0 or errors == 0


# ── Restauração completa ──────────────────────────────────────────────────────

def restore_all_theme(callback=None):
    results = {
        "wallpaper":   restore_wallpaper(callback),
        "screensaver": restore_screensaver(callback),
        "lock_screen": restore_lock_screen(callback),
        "cursors":     restore_cursors(callback),
        "colors":      restore_colors(callback),
        "theme":       apply_default_windows_theme(callback),
    }
    _broadcast()
    ok = sum(1 for v in results.values() if v)
    if callback:
        callback(f"\n✔ Restauração de tema: {ok}/{len(results)} etapas com sucesso.")
    return results


# ── Lixeira ───────────────────────────────────────────────────────────────────

def empty_recycle_bin(callback=None) -> bool:
    """
    Esvazia a Lixeira do usuário atual usando SHEmptyRecycleBinW (Win32).
    Flags: SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND = 0x7
    """
    try:
        if callback: callback("Esvaziando a Lixeira...")
        import ctypes
        # SHEmptyRecycleBinW(hwnd, pszRootPath, dwFlags)
        # hwnd=None, pszRootPath=None (todas as unidades), flags=7 (silencioso)
        ret = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x0007)
        # 0 = sucesso, 0x800700A1 = lixeira já vazia (também ok)
        if ret == 0 or ret == -2147024735:  # 0x800700A1 como signed
            if callback: callback("✔ Lixeira esvaziada.")
            return True
        # Tenta também via PowerShell como fallback
        import subprocess
        si = subprocess.STARTUPINFO()
        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
             "-Command", "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
            capture_output=True, creationflags=0x08000000, startupinfo=si, timeout=30
        )
        if callback: callback("✔ Lixeira esvaziada.")
        return True
    except Exception as e:
        logger.error(f"empty_recycle_bin: {e}")
        if callback: callback(f"✘ Erro ao esvaziar lixeira: {e}")
        return False
