# -*- coding: utf-8 -*-
"""
W.B. SystemCare — Ferramenta de limpeza e restauração para laboratórios.

Desenvolvedor : Waldemir (@romeuwb)
Local         : Usina da Paz Salinópolis — Sala de Tecnologia
Versão        : 1.2
"""

import os
import sys
import threading
import logging
import subprocess
import winreg
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime

import theme_restore
import file_scanner
import user_manager
from tray_win32 import TrayIcon
from credential_helper import CredentialCache, validate_credentials, is_elevated

# ── Logging ───────────────────────────────────────────────────────────────────
def _base_dir():
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

LOG_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wb_systemcare.log")
ICON_PATH = os.path.join(_base_dir(), "assets", "logo.ico")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── Constantes de inicialização com Windows ───────────────────────────────────
APP_NAME      = "WB_SystemCare"
TASK_NAME     = "WB_SystemCare_AutoClean"
STARTUP_TASK  = "WB_SystemCare_Startup"

# ── Paleta âmbar / dourado / terracota ────────────────────────────────────────
C = {
    # Fundos
    "bg":           "#17140f",   # fundo principal
    "bg_card":      "#211d16",   # cartões
    "bg_sidebar":   "#0f0d09",   # sidebar
    "bg_header":    "#0b0905",   # header/footer
    "bg_input":     "#2a2318",   # campos
    "bg_row":       "#1e1a13",   # linhas de tabela (não selecionadas)

    # Âmbar / dourado
    "accent":       "#d4982e",
    "accent_light": "#f0b840",
    "accent_dim":   "#8a6218",

    # Azul de contraste (usado em seleções e destaques)
    "blue":         "#4a8fd4",
    "blue_light":   "#6aaaf0",
    "blue_dim":     "#2a5a9a",

    # Semânticas
    "success":      "#5cb85c",
    "danger":       "#d9534f",
    "danger_light": "#f07070",
    "warning":      "#f0a830",
    "info":         "#5a9fc8",

    # Texto — alto contraste
    "text":         "#f5ede0",   # texto principal — creme claro
    "text_dim":     "#b8a888",   # texto secundário — bege médio
    "text_muted":   "#6a5e4a",   # texto desabilitado
    "text_row":     "#e0d0b8",   # texto em linhas de tabela não selecionadas

    # Bordas / divisores
    "border":       "#3a3028",
    "progress_bg":  "#3a3028",
    "progress_fg":  "#d4982e",

    # Seleção — azul para contrastar com o dourado
    "sel_bg":       "#1a3a6e",
    "sel_fg":       "#f5ede0",

    # Steps
    "step_done":    "#5cb85c",
    "step_active":  "#d4982e",
    "step_pending": "#4a4038",
}
FONT_TITLE = ("Segoe UI", 15, "bold")
FONT_SUB   = ("Segoe UI", 11, "bold")
FONT_BODY  = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI",  9)
FONT_TINY  = ("Segoe UI",  8)
FONT_MONO  = ("Consolas",  9)


# ── Helpers de widget ─────────────────────────────────────────────────────────
def _btn(parent, text, cmd, variant="primary", width=18, **kw):
    bg  = C["accent"]       if variant == "primary" else C["danger"]
    hov = C["accent_light"] if variant == "primary" else C["danger_light"]
    b = tk.Button(parent, text=text, command=cmd,
                  bg=bg, fg="#0d0b09", activebackground=hov,
                  activeforeground="#0d0b09", relief="flat", cursor="hand2",
                  bd=0, font=("Segoe UI", 10, "bold"), width=width,
                  padx=10, pady=6, **kw)
    b.bind("<Enter>", lambda e: b.config(bg=hov))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b

def _hsep(parent, pady=6):
    tk.Frame(parent, bg=C["border"], height=1).pack(fill="x", padx=16, pady=pady)

def _page_title(parent, title, subtitle=""):
    f = tk.Frame(parent, bg=C["bg"])
    f.pack(fill="x", padx=20, pady=(16, 8))
    tk.Label(f, text=title, bg=C["bg"], fg=C["text"],     font=FONT_TITLE).pack(anchor="w")
    if subtitle:
        tk.Label(f, text=subtitle, bg=C["bg"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w")

def _log_box(parent, height=8):
    f = tk.Frame(parent, bg=C["bg_card"])
    f.pack(fill="both", expand=True, padx=20, pady=(2, 10))
    t = tk.Text(f, height=height, bg=C["bg_card"], fg=C["text"],
                font=FONT_MONO, relief="flat", bd=0, wrap="word",
                insertbackground=C["text"], selectbackground=C["sel_bg"])
    sb = ttk.Scrollbar(f, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True, padx=6, pady=4)
    sb.pack(side="right", fill="y")
    t.config(state="disabled")
    return t

def _card(parent, **kw):
    return tk.Frame(parent, bg=C["bg_card"], relief="flat", bd=0, **kw)


def _scrollable_frame(parent):
    """
    Retorna (outer_frame, inner_frame).
    outer_frame deve ser packed no content.
    inner_frame é onde se adiciona os widgets — tem scroll vertical automático.
    """
    outer = tk.Frame(parent, bg=C["bg"])
    canvas = tk.Canvas(outer, bg=C["bg"], highlightthickness=0)
    vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)

    inner = tk.Frame(canvas, bg=C["bg"])
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(win_id, width=canvas.winfo_width())

    inner.bind("<Configure>", _on_configure)
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

    # Scroll com roda do mouse
    def _mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind_all("<MouseWheel>", _mousewheel)

    canvas.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    return outer, inner


# ── subprocess silencioso (sem janela preta) ──────────────────────────────────
_NO_WIN = 0x08000000  # CREATE_NO_WINDOW

def _run_silent(cmd: str) -> subprocess.CompletedProcess:
    si = subprocess.STARTUPINFO()
    si.dwFlags     = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        creationflags=_NO_WIN, startupinfo=si
    )


# ── Inicialização com Windows (HKCU + HKLM + Task Scheduler) ──────────────────

def _exe_path() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(__file__)}"'

def startup_is_registered() -> bool:
    """Verifica se o app está registrado para iniciar com o Windows."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except FileNotFoundError:
        pass
    # Verifica também via task scheduler
    r = _run_silent(f'schtasks /Query /TN "{STARTUP_TASK}" /FO LIST')
    return r.returncode == 0

def startup_register(all_users: bool, minimized: bool, callback=None) -> bool:
    """
    Registra o app para iniciar com o Windows.
    all_users=True → usa HKLM + Task Scheduler (requer admin).
    all_users=False → usa HKCU Run (só o usuário atual).
    minimized=True  → passa --minimized para abrir na tray.
    """
    try:
        exe   = _exe_path()
        args  = f"{exe} --minimized" if minimized else exe
        ok    = True

        if all_users:
            # Task Scheduler com SYSTEM ou USERS — funciona para todos os perfis
            cmd = (
                f'schtasks /Create /F /TN "{STARTUP_TASK}" '
                f'/TR "{exe} --minimized" '
                f'/SC ONLOGON /RL HIGHEST /DELAY 0000:30'
            )
            r = _run_silent(cmd)
            if r.returncode != 0:
                if callback: callback(f"⚠ Task Scheduler: {r.stderr.strip()}")
                ok = False
            else:
                if callback: callback("✔ Tarefa de inicialização criada (todos os perfis).")

            # Também tenta HKLM para garantir
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                                    0, winreg.KEY_SET_VALUE) as k:
                    winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, args)
                if callback: callback("✔ Registro HKLM Run atualizado.")
            except PermissionError:
                if callback: callback("⚠ Sem permissão para HKLM (execute como Admin).")
        else:
            # Só o usuário atual — HKCU, sem precisar de admin
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Run",
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, args)
            if callback: callback("✔ Inicialização registrada para o usuário atual (HKCU).")

        return ok
    except Exception as e:
        if callback: callback(f"✘ Erro ao registrar inicialização: {e}")
        return False

def startup_remove(callback=None) -> bool:
    """Remove o registro de inicialização automática."""
    removed = False
    # HKCU
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
        if callback: callback("✔ Removido do HKCU Run.")
        removed = True
    except FileNotFoundError:
        pass
    except Exception as e:
        if callback: callback(f"⚠ HKCU: {e}")

    # HKLM
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, APP_NAME)
        if callback: callback("✔ Removido do HKLM Run.")
        removed = True
    except FileNotFoundError:
        pass
    except Exception as e:
        if callback: callback(f"⚠ HKLM: {e}")

    # Task Scheduler (startup)
    r = _run_silent(f'schtasks /Delete /F /TN "{STARTUP_TASK}"')
    if r.returncode == 0:
        if callback: callback("✔ Tarefa de inicialização removida.")
        removed = True

    if not removed:
        if callback: callback("⚠ Nenhum registro de inicialização encontrado.")
    return removed


# ── Agendamento periódico ─────────────────────────────────────────────────────

def schedule_create(days, hour, minute, do_theme, do_scan, do_delete, callback=None):
    try:
        exe   = _exe_path()
        flags = " ".join(f for f, v in [
            ("--auto-theme",  do_theme),
            ("--auto-scan",   do_scan),
            ("--auto-delete", do_delete),
        ] if v)
        cmd = (
            f'schtasks /Create /F /TN "{TASK_NAME}" '
            f'/TR "{exe} {flags}" '
            f'/SC DAILY /MO {days} /ST {hour:02d}:{minute:02d} /RL HIGHEST'
        )
        r = _run_silent(cmd)
        ok = r.returncode == 0
        if callback:
            callback(f"✔ Agendamento criado: a cada {days} dia(s) às {hour:02d}:{minute:02d}."
                     if ok else f"✘ {r.stderr.strip()}")
        return ok
    except Exception as e:
        if callback: callback(f"✘ {e}")
        return False

def schedule_delete(callback=None):
    r = _run_silent(f'schtasks /Delete /F /TN "{TASK_NAME}"')
    ok = r.returncode == 0
    if callback: callback("✔ Agendamento removido." if ok else f"⚠ {r.stderr.strip()}")
    return ok

def schedule_status():
    r = _run_silent(f'schtasks /Query /TN "{TASK_NAME}" /FO LIST')
    if r.returncode != 0:
        return "Nenhuma tarefa agendada encontrada."
    info = {}
    for line in r.stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            info[k.strip()] = v.strip()
    nxt = info.get("Próxima execução", info.get("Next Run Time", "—"))
    lst = info.get("Última execução",  info.get("Last Run Time",  "—"))
    sts = info.get("Status", "—")
    return f"✔ Tarefa ativa\n   Próxima: {nxt}\n   Última: {lst}\n   Status: {sts}"


# ── Modo headless (agendador chama sem GUI) ────────────────────────────────────
def run_headless():
    args = sys.argv[1:]
    logger.info("=== WB SystemCare — Execução automática ===")
    if "--auto-theme"  in args:
        theme_restore.restore_all_theme(lambda m: logger.info(m))
    if "--auto-scan"   in args:
        items = file_scanner.scan_profile_folders(lambda m: logger.info(m))
        if "--auto-delete" in args:
            res = file_scanner.delete_items(items, lambda m: logger.info(m))
            logger.info(f"Excluídos: {res['deleted']}  Falhas: {res['failed']}")
    logger.info("=== Execução automática concluída ===")


# ─────────────────────────────────────────────────────────────────────────────
# Aplicativo principal
# ─────────────────────────────────────────────────────────────────────────────
class WBSystemCare(tk.Tk):

    def __init__(self, start_minimized=False):
        super().__init__()
        self.title("W.B. SystemCare")
        self.configure(bg=C["bg"])
        self.resizable(True, True)
        self._start_minimized = start_minimized

        # Detecta resolução e define tamanho fixo (não muda entre abas)
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # Inicia sempre maximizado para não cortar conteúdo em nenhuma resolução
        self.state("zoomed")
        self.minsize(900, 600)

        # Ícone
        if os.path.exists(ICON_PATH):
            try: self.iconbitmap(ICON_PATH)
            except Exception: pass

        # Estado
        self._scan_items  = []
        self._check_vars  = {}
        self._running     = False
        self._auto_steps  = {k: tk.BooleanVar(value=v) for k, v in {
            "theme": True, "scan": True, "delete": False, "confirm": True
        }.items()}
        self._steps = [
            {"label": "Restaurar Tema"},
            {"label": "Varrer Arquivos"},
            {"label": "Selecionar"},
            {"label": "Excluir"},
        ]
        self._step_labels = []
        self._step_cards  = []
        self._tray        = None
        self._cred_cache  = CredentialCache()   # credenciais admin da sessão

        self._build_ui()
        self._init_tray()
        self._center()

        if start_minimized:
            self.after(100, self._minimize_to_tray)

    # ── Tray ──────────────────────────────────────────────────────────────────

    def _init_tray(self):
        menu = [
            ("Abrir W.B. SystemCare", self._restore_from_tray),
            None,
            ("Varredura rápida",      self._tray_quick_scan),
            ("Restaurar tema",        self._tray_restore_theme),
            None,
            ("Sair",                  self._quit_app),
        ]
        self._tray = TrayIcon(
            root=self,
            icon_path=ICON_PATH,
            tooltip="W.B. SystemCare",
            menu_items=menu,
            on_restore=self._restore_from_tray,
        )
        self._tray.show()

    def _tray_pump(self):
        pass  # Não necessário: tray usa thread dedicada com GetMessageW

    def _minimize_to_tray(self):
        self.withdraw()
        if self._tray:
            self._tray.show_balloon(
                "W.B. SystemCare",
                "Executando em segundo plano. Clique duas vezes no ícone para abrir."
            )

    def _restore_from_tray(self):
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()

    def _tray_quick_scan(self):
        self._restore_from_tray()
        self.after(300, self._run_scan)

    def _tray_restore_theme(self):
        if self._running: return
        for v in self._theme_vars.values(): v.set(True)
        self._exec_theme(set(self._theme_vars.keys()))

    def _quit_app(self):
        if self._tray: self._tray.hide()
        self.destroy()

    # ── Protocolo fechar janela → tray ────────────────────────────────────────
    def _on_close(self):
        self.withdraw()
        if self._tray:
            self._tray.show_balloon("W.B. SystemCare",
                                    "Minimizado para a bandeja do sistema.")

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_header()
        wrap = tk.Frame(self, bg=C["bg"])
        wrap.pack(fill="both", expand=True)
        self._build_sidebar(wrap)
        self._content = tk.Frame(wrap, bg=C["bg"])
        self._content.pack(side="left", fill="both", expand=True)
        self._pages = {}
        self._build_page_theme()
        self._build_page_scan()
        self._build_page_auto()
        self._build_page_schedule()
        self._build_page_users()
        self._build_page_progress()
        self._build_page_update()
        self._build_statusbar()
        self._show("theme")

    def _build_header(self):
        hdr = tk.Frame(self, bg=C["bg_header"], height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        # Logo
        if os.path.exists(ICON_PATH):
            try:
                from PIL import Image, ImageTk
                img = Image.open(ICON_PATH).resize((40, 40))
                self._logo_img = ImageTk.PhotoImage(img)
                tk.Label(hdr, image=self._logo_img,
                         bg=C["bg_header"]).pack(side="left", padx=(16, 8), pady=10)
            except Exception:
                tk.Label(hdr, text="🖥", bg=C["bg_header"], fg=C["accent"],
                         font=("Segoe UI Emoji", 22)).pack(side="left", padx=(16, 8))
        else:
            tk.Label(hdr, text="🖥", bg=C["bg_header"], fg=C["accent"],
                     font=("Segoe UI Emoji", 22)).pack(side="left", padx=(16, 8))

        tk.Frame(hdr, bg=C["accent"], width=2).pack(side="left", fill="y", pady=12)

        info = tk.Frame(hdr, bg=C["bg_header"])
        info.pack(side="left", padx=12, pady=8)
        tk.Label(info, text="W.B. SystemCare",
                 bg=C["bg_header"], fg=C["accent"],
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(info,
                 text="Usina da Paz Salinópolis — Sala de Tecnologia  •  Restauração & Limpeza",
                 bg=C["bg_header"], fg=C["text_dim"], font=FONT_TINY).pack(anchor="w")

        right = tk.Frame(hdr, bg=C["bg_header"])
        right.pack(side="right", padx=20)
        tk.Label(right, text=f"v1.3  •  {datetime.now().strftime('%d/%m/%Y')}",
                 bg=C["bg_header"], fg=C["text_dim"], font=FONT_TINY).pack(anchor="e")
        tk.Label(right, text="Dev: Waldemir  @romeuwb",
                 bg=C["bg_header"], fg=C["accent_dim"], font=FONT_TINY).pack(anchor="e")

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=C["bg_sidebar"], width=200)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)
        tk.Frame(sb, bg=C["accent"], height=3).pack(fill="x")

        def _sec(t):
            tk.Label(sb, text=t, bg=C["bg_sidebar"], fg=C["text_muted"],
                     font=("Segoe UI", 7, "bold")).pack(pady=(14,4), padx=16, anchor="w")

        _sec("NAVEGAÇÃO")
        nav = [
            ("🎨", "Personalização",  "theme"),
            ("🔍", "Varredura",       "scan"),
            ("⚡", "Automação",       "auto"),
            ("🗓", "Agendamento",     "schedule"),
            ("👥", "Usuários",        "users"),
            ("📊", "Progresso",       "progress"),
            ("🔄", "Atualização",     "update"),
        ]
        self._nav_btns = {}
        for icon, label, key in nav:
            f = tk.Frame(sb, bg=C["bg_sidebar"])
            f.pack(fill="x")
            b = tk.Button(f, text=f"  {icon}  {label}", anchor="w",
                          bg=C["bg_sidebar"], fg=C["text_dim"],
                          activebackground=C["bg_card"], activeforeground=C["text"],
                          relief="flat", cursor="hand2", bd=0,
                          font=FONT_BODY, padx=8, pady=9,
                          command=lambda k=key: self._show(k))
            b.pack(fill="x")
            bar = tk.Frame(f, bg=C["accent"], width=3)
            self._nav_btns[key] = (b, bar, f)

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=12, pady=8)
        _sec("ETAPAS")
        for step in self._steps:
            row = tk.Frame(sb, bg=C["bg_sidebar"])
            row.pack(fill="x", padx=10, pady=3)
            il = tk.Label(row, text="○", bg=C["bg_sidebar"],
                          fg=C["step_pending"], font=("Segoe UI", 11))
            il.pack(side="left", padx=(2, 6))
            tl = tk.Label(row, text=step["label"], bg=C["bg_sidebar"],
                          fg=C["text_muted"], font=FONT_SMALL, anchor="w")
            tl.pack(side="left")
            self._step_labels.append({"icon": il, "text": tl})

        tk.Frame(sb, bg=C["border"], height=1).pack(fill="x", padx=12, pady=(12,4))

        # Usuário atual
        self._user_lbl = tk.Label(
            sb,
            text=f"👤 {file_scanner.get_current_username()}",
            bg=C["bg_sidebar"], fg=C["accent_dim"], font=FONT_TINY
        )
        self._user_lbl.pack(pady=(2, 2))
        tk.Label(sb, text="W.B. SystemCare © 2026",
                 bg=C["bg_sidebar"], fg=C["text_muted"],
                 font=("Segoe UI", 7)).pack(pady=(0, 8))

    def _show(self, key):
        for k, frm in self._pages.items(): frm.pack_forget()
        if key in self._pages: self._pages[key].pack(fill="both", expand=True)
        for k, (b, bar, f) in self._nav_btns.items():
            active = (k == key)
            b.config(bg=C["bg_card"] if active else C["bg_sidebar"],
                     fg=C["accent"]  if active else C["text_dim"],
                     font=("Segoe UI", 10, "bold") if active else FONT_BODY)
            bar.place(x=0, y=0, relheight=1) if active else bar.place_forget()
        # Carrega usuários apenas na primeira vez que a aba for acessada
        if key == "users" and not self._users_loaded:
            self._users_loaded = True
            self.after(100, self._users_load_admins)

    # ── Página: Tema ──────────────────────────────────────────────────────────

    def _build_page_theme(self):
        outer = tk.Frame(self._content, bg=C["bg"])
        self._pages["theme"] = outer
        scroll_outer, p = _scrollable_frame(outer)
        scroll_outer.pack(fill="both", expand=True)
        _page_title(p, "🎨  Personalização do Windows",
                    "Selecione o que deseja restaurar para os padrões de fábrica.")

        self._theme_vars = {k: tk.BooleanVar(value=True) for k in
                            ["wallpaper","screensaver","lock_screen","cursors","colors",
                             "browser_history","recycle_bin"]}

        opts = [
            ("wallpaper",        "🖼",  "Papel de Parede",
             "Aplica wallpaper\npadrão Windows"),
            ("screensaver",      "🔒",  "Proteção de Tela",
             "Desativa e define\n'Nenhuma'"),
            ("lock_screen",      "🖥",  "Tela de Bloqueio",
             "Reativa Spotlight\ne imagem padrão"),
            ("cursors",          "🖱",  "Ponteiros",
             "Restaura Aero\ntamanho padrão"),
            ("colors",           "🎨",  "Cores do Sistema",
             "Cor de destaque\nautomática"),
            ("browser_history",  "🌐",  "Histórico Web",
             "Limpa Chrome, Edge,\nFirefox, IE"),
            ("recycle_bin",      "🗑",  "Lixeira",
             "Esvazia a lixeira\ndo usuário atual"),
        ]

        cf = tk.Frame(p, bg=C["bg"])
        cf.pack(fill="x", padx=20, pady=6)
        for col, (key, icon, title, desc) in enumerate(opts):
            c = _card(cf)
            c.grid(row=0, column=col, padx=5, pady=4, sticky="nsew")
            cf.columnconfigure(col, weight=1)
            tk.Frame(c, bg=C["accent"], height=3).pack(fill="x")
            tk.Label(c, text=icon, bg=C["bg_card"], fg=C["accent"],
                     font=("Segoe UI Emoji", 22)).pack(pady=(12,4))
            tk.Label(c, text=title, bg=C["bg_card"], fg=C["text"],
                     font=("Segoe UI",10,"bold")).pack()
            tk.Label(c, text=desc, bg=C["bg_card"], fg=C["text_dim"],
                     font=FONT_TINY, justify="center").pack(pady=(4,8), padx=8)
            tk.Checkbutton(c, variable=self._theme_vars[key],
                           bg=C["bg_card"], fg=C["text"],
                           activebackground=C["bg_card"],
                           selectcolor=C["accent_dim"],
                           relief="flat", cursor="hand2").pack(pady=(0,12))

        _hsep(p)
        bf = tk.Frame(p, bg=C["bg"])
        bf.pack(anchor="w", padx=20, pady=8)
        _btn(bf, "✔  Restaurar Selecionados", self._run_theme_restore, width=24).pack(side="left", padx=(0,8))
        _btn(bf, "✔  Restaurar Tudo",         self._run_theme_all,    width=18).pack(side="left")
        _hsep(p)
        tk.Label(p, text="Log:", bg=C["bg"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w", padx=20)
        self._theme_log = _log_box(p, 9)

    # ── Página: Varredura ─────────────────────────────────────────────────────

    def _build_page_scan(self):
        p = tk.Frame(self._content, bg=C["bg"])
        self._pages["scan"] = p
        _page_title(p, "🔍  Varredura de Arquivos",
                    "Lista recursiva das pastas do usuário. Selecione os itens para excluir.")

        # ── Linha 1: Configuração ANTES de escanear ─────────────────────────
        config_bar = tk.Frame(p, bg=C["bg_card"])
        config_bar.pack(fill="x", padx=20, pady=(0, 2))
        tk.Frame(config_bar, bg=C["accent"], height=2).pack(fill="x")
        cf_inner = tk.Frame(config_bar, bg=C["bg_card"])
        cf_inner.pack(fill="x", padx=12, pady=6)

        tk.Label(cf_inner, text="① Preparar:", bg=C["bg_card"],
                 fg=C["text_dim"], font=FONT_SMALL).pack(side="left", padx=(0,8))

        _btn(cf_inner, "📂  Escolher Pastas para Varrer",
             self._choose_folders_to_scan, width=28).pack(side="left", padx=(0,6))

        # Label mostrando pastas escolhidas
        self._chosen_folders_lbl = tk.Label(
            cf_inner, text="Todas as pastas do perfil (padrão)",
            bg=C["bg_card"], fg=C["text_dim"], font=FONT_TINY, anchor="w"
        )
        self._chosen_folders_lbl.pack(side="left", fill="x", expand=True, padx=(4,0))

        # ── Linha 2: Ações principais ─────────────────────────────────────
        ab = tk.Frame(p, bg=C["bg"])
        ab.pack(fill="x", padx=20, pady=(6, 4))

        tk.Label(ab, text="② Executar:", bg=C["bg"],
                 fg=C["text_dim"], font=FONT_SMALL).pack(side="left", padx=(0,8))

        _btn(ab, "🔍  Escanear",         self._run_scan,           width=14).pack(side="left", padx=(0,6))
        _btn(ab, "🗑  Excluir Marcados",  self._run_delete, "danger", width=18).pack(side="left", padx=(0,6))
        _btn(ab, "🔄  Limpar / Recomeçar", self._scan_clear,        width=20).pack(side="left")

        # ── Linha 3: Seleção ──────────────────────────────────────────────
        sf = tk.Frame(p, bg=C["bg"])
        sf.pack(fill="x", padx=20, pady=(0, 4))

        tk.Label(sf, text="③ Selecionar:", bg=C["bg"],
                 fg=C["text_dim"], font=FONT_SMALL).pack(side="left", padx=(0,8))

        for txt, cmd in [("☑ Tudo", self._sel_all), ("☐ Nenhum", self._desel_all)]:
            tk.Button(sf, text=txt, font=FONT_SMALL,
                      bg=C["bg_card"], fg=C["text_dim"],
                      activebackground=C["border"], relief="flat", cursor="hand2",
                      command=cmd).pack(side="left", padx=(0,6))

        self._scan_sum_lbl = tk.Label(sf, text="Nenhuma varredura realizada.",
                                      bg=C["bg"], fg=C["text_dim"], font=FONT_SMALL)
        self._scan_sum_lbl.pack(side="right")

        # Tabela com nova coluna "Caminho Completo"
        tf = tk.Frame(p, bg=C["bg"])
        tf.pack(fill="both", expand=True, padx=20, pady=(0,4))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("WB.Treeview",
                        background=C["bg_row"],
                        foreground=C["text_row"],
                        fieldbackground=C["bg_row"],
                        rowheight=22, font=FONT_SMALL)
        style.configure("WB.Treeview.Heading",
                        background=C["bg_header"], foreground=C["accent"],
                        font=("Segoe UI",9,"bold"), relief="flat")
        style.map("WB.Treeview",
                  background=[("selected", C["sel_bg"])],
                  foreground=[("selected", C["sel_fg"])])

        cols = ("sel","tipo","tamanho","modificado","pasta")
        self._tree = ttk.Treeview(tf, columns=cols,
                                  show="tree headings",   # mostra a coluna de árvore + setas nativas
                                  selectmode="extended", style="WB.Treeview")

        # Coluna de árvore (col #0) — mostra nome com cascata
        self._tree.column("#0", width=280, minwidth=160, stretch=True, anchor="w")
        self._tree.heading("#0", text="Nome / Caminho",
                           command=lambda: self._sort_scan("nome"))

        col_defs = [
            ("sel",       "✔",          30,  False, "center"),
            ("tipo",      "Tipo",        60, False, "center"),
            ("tamanho",   "Tamanho",     90, False, "e"),
            ("modificado","Modificado", 130, False, "center"),
            ("pasta",     "Pasta Raiz", 120, False, "w"),
        ]
        for col, hd, w, stretch, anchor in col_defs:
            self._tree.heading(col, text=hd,
                               command=lambda c=col: self._sort_scan(c))
            self._tree.column(col, width=w, minwidth=max(w-20,30),
                              stretch=stretch, anchor=anchor)
        self._sort_col = None
        self._sort_rev = False

        vsb = ttk.Scrollbar(tf, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(tf, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tf.rowconfigure(0, weight=1); tf.columnconfigure(0, weight=1)

        self._tree.bind("<space>",            self._toggle_items)
        self._tree.bind("<Double-1>",          self._toggle_items)
        self._tree.bind("<ButtonRelease-1>",   self._on_tree_click)
        self._tree.bind("<<TreeviewOpen>>",    self._on_tree_expand)
        self._tree.bind("<<TreeviewClose>>",   self._on_tree_collapse)
        self._tree.tag_configure("checked",     background=C["sel_bg"],  foreground=C["sel_fg"])
        self._tree.tag_configure("unchecked",   background=C["bg_row"],  foreground=C["text_row"])
        self._tree.tag_configure("depth_0",     foreground=C["text"])
        self._tree.tag_configure("depth_1",     foreground=C["text_dim"])
        self._tree.tag_configure("depth_2plus", foreground=C["text_muted"])

    # ── Página: Automação ─────────────────────────────────────────────────────

    def _build_page_auto(self):
        p = tk.Frame(self._content, bg=C["bg"])
        self._pages["auto"] = p
        _page_title(p, "⚡  Automação Completa",
                    "Execute todas as etapas com um único clique.")

        warn = tk.Frame(p, bg="#2e1a0a")
        warn.pack(fill="x", padx=20, pady=(0,10))
        tk.Frame(warn, bg=C["warning"], width=4).pack(side="left", fill="y")
        tk.Label(warn, text="  ⚠  A exclusão automática remove arquivos permanentemente, sem lixeira!",
                 bg="#2e1a0a", fg=C["warning"], font=("Segoe UI",10,"bold"),
                 pady=10, padx=8).pack(side="left")

        oc = _card(p)
        oc.pack(fill="x", padx=20, pady=4)
        tk.Frame(oc, bg=C["accent"], height=3).pack(fill="x")

        for key, icon, title, desc in [
            ("theme",   "🎨", "Restaurar tema padrão do Windows",
             "Papel de parede, proteção de tela, tela de bloqueio, cursores e cores"),
            ("scan",    "🔍", "Escanear pastas do usuário",
             "Documentos, Downloads, Desktop, Músicas, Vídeos, Imagens, Temp"),
            ("confirm", "🔔", "Confirmar antes de excluir",
             "Exibe lista para revisão antes de deletar (recomendado)"),
            ("delete",  "🗑", "Excluir arquivos automaticamente",
             "⚠ Exclui TODOS os itens encontrados sem confirmação individual"),
        ]:
            row = tk.Frame(oc, bg=C["bg_card"])
            row.pack(fill="x", padx=16, pady=6)
            tk.Checkbutton(row, variable=self._auto_steps[key],
                           bg=C["bg_card"], fg=C["text"],
                           activebackground=C["bg_card"],
                           selectcolor=C["accent_dim"],
                           relief="flat", cursor="hand2").pack(side="left")
            tk.Label(row, text=f"  {icon}  ", bg=C["bg_card"], fg=C["accent"],
                     font=("Segoe UI Emoji",14)).pack(side="left")
            inf = tk.Frame(row, bg=C["bg_card"])
            inf.pack(side="left", fill="x", expand=True)
            tk.Label(inf, text=title, bg=C["bg_card"], fg=C["text"],
                     font=("Segoe UI",10,"bold"), anchor="w").pack(anchor="w")
            tk.Label(inf, text=desc, bg=C["bg_card"], fg=C["text_dim"],
                     font=FONT_SMALL, anchor="w").pack(anchor="w")

        _hsep(p)
        bf = tk.Frame(p, bg=C["bg"])
        bf.pack(pady=12, padx=20, anchor="w")
        big = tk.Button(bf, text="⚡  INICIAR LIMPEZA AUTOMÁTICA",
                        command=self._run_auto,
                        bg=C["accent"], fg="#0d0b09",
                        activebackground=C["accent_light"],
                        activeforeground="#0d0b09",
                        relief="flat", cursor="hand2", bd=0,
                        font=("Segoe UI",12,"bold"), padx=24, pady=12)
        big.bind("<Enter>", lambda e: big.config(bg=C["accent_light"]))
        big.bind("<Leave>", lambda e: big.config(bg=C["accent"]))
        big.pack(side="left", padx=(0,10))
        _btn(bf, "↺  Nova Sessão", self._reset, width=14).pack(side="left")
        _hsep(p)
        tk.Label(p, text="Log de Automação:", bg=C["bg"],
                 fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w", padx=20)
        self._auto_log = _log_box(p, 9)
        tk.Label(p,
                 text="W.B. SystemCare  •  Waldemir (@romeuwb)  •  Usina da Paz Salinópolis",
                 bg=C["bg"], fg=C["text_muted"], font=("Segoe UI",7)).pack(pady=(0,6))

    # ── Página: Agendamento ───────────────────────────────────────────────────

    def _build_page_schedule(self):
        outer = tk.Frame(self._content, bg=C["bg"])
        self._pages["schedule"] = outer
        scroll_outer, p = _scrollable_frame(outer)
        scroll_outer.pack(fill="both", expand=True)
        _page_title(p, "🗓  Agendamento & Inicialização",
                    "Configure a execução periódica e o arranque automático com o Windows.")

        # ── Seção: Inicialização com o Windows ────────────────────────────────
        sc_init = _card(p)
        sc_init.pack(fill="x", padx=20, pady=(4,8))
        tk.Frame(sc_init, bg=C["accent"], height=3).pack(fill="x")

        hf = tk.Frame(sc_init, bg=C["bg_card"])
        hf.pack(fill="x", padx=16, pady=(10,6))
        tk.Label(hf, text="🚀  Inicializar com o Windows",
                 bg=C["bg_card"], fg=C["accent"],
                 font=("Segoe UI",11,"bold")).pack(anchor="w")
        tk.Label(hf,
                 text="Registra o app para iniciar automaticamente quando o Windows ligar.",
                 bg=C["bg_card"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w")

        opts_f = tk.Frame(sc_init, bg=C["bg_card"])
        opts_f.pack(fill="x", padx=16, pady=(0,8))

        self._startup_minimized = tk.BooleanVar(value=True)
        self._startup_all_users = tk.BooleanVar(value=False)

        tk.Checkbutton(opts_f,
                       text="  Iniciar minimizado (na bandeja do sistema)",
                       variable=self._startup_minimized,
                       bg=C["bg_card"], fg=C["text"], font=FONT_BODY,
                       activebackground=C["bg_card"],
                       selectcolor=C["accent_dim"],
                       relief="flat", cursor="hand2").pack(anchor="w", pady=2)

        all_users_chk = tk.Checkbutton(opts_f,
                       text="  Todos os perfis / usuários (requer Administrador)",
                       variable=self._startup_all_users,
                       bg=C["bg_card"], fg=C["text"], font=FONT_BODY,
                       activebackground=C["bg_card"],
                       selectcolor=C["accent_dim"],
                       relief="flat", cursor="hand2")
        all_users_chk.pack(anchor="w", pady=2)

        tk.Label(opts_f,
                 text="     → Usa o Agendador de Tarefas (schtasks /ONLOGON) para cobrir todos os logins.",
                 bg=C["bg_card"], fg=C["text_muted"], font=FONT_TINY).pack(anchor="w")

        # Status de inicialização
        self._startup_status_lbl = tk.Label(
            sc_init, text="", bg=C["bg_card"],
            fg=C["text_dim"], font=FONT_SMALL, padx=16, pady=4, anchor="w"
        )
        self._startup_status_lbl.pack(fill="x")

        bf_init = tk.Frame(sc_init, bg=C["bg_card"])
        bf_init.pack(padx=16, pady=(0,12), anchor="w")
        _btn(bf_init, "🚀  Ativar Inicialização",  self._startup_register,         width=24).pack(side="left", padx=(0,8))
        _btn(bf_init, "✗  Remover Inicialização",  self._startup_remove, "danger", width=22).pack(side="left", padx=(0,8))
        _btn(bf_init, "🔍  Verificar",              self._startup_check,            width=12).pack(side="left")

        _hsep(p, pady=4)

        # ── Seção: Agendamento periódico ──────────────────────────────────────
        sc_sched = _card(p)
        sc_sched.pack(fill="x", padx=20, pady=(0,8))
        tk.Frame(sc_sched, bg=C["warning"], height=3).pack(fill="x")

        hf2 = tk.Frame(sc_sched, bg=C["bg_card"])
        hf2.pack(fill="x", padx=16, pady=(10,6))
        tk.Label(hf2, text="🗓  Limpeza Periódica Agendada",
                 bg=C["bg_card"], fg=C["warning"],
                 font=("Segoe UI",11,"bold")).pack(anchor="w")
        tk.Label(hf2, text="Executa a limpeza automaticamente a cada X dias.",
                 bg=C["bg_card"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w")

        inner = tk.Frame(sc_sched, bg=C["bg_card"])
        inner.pack(fill="x", padx=16, pady=(0,8))

        # Linha: intervalo
        r1 = tk.Frame(inner, bg=C["bg_card"])
        r1.pack(fill="x", pady=4)
        tk.Label(r1, text="Executar a cada", bg=C["bg_card"],
                 fg=C["text"], font=FONT_BODY).pack(side="left")
        self._sched_days = tk.Spinbox(r1, from_=1, to=365, width=4,
                                      bg=C["bg_input"], fg=C["text"], font=FONT_BODY,
                                      buttonbackground=C["bg_card"], relief="flat",
                                      insertbackground=C["text"])
        self._sched_days.delete(0,"end"); self._sched_days.insert(0,"1")
        self._sched_days.pack(side="left", padx=8)
        tk.Label(r1, text="dia(s)  às",
                 bg=C["bg_card"], fg=C["text"], font=FONT_BODY).pack(side="left")
        self._sched_hour = tk.Spinbox(r1, from_=0, to=23, width=3,
                                      bg=C["bg_input"], fg=C["text"], font=FONT_BODY,
                                      buttonbackground=C["bg_card"], relief="flat",
                                      insertbackground=C["text"])
        self._sched_hour.delete(0,"end"); self._sched_hour.insert(0,"08")
        self._sched_hour.pack(side="left", padx=8)
        tk.Label(r1, text=":", bg=C["bg_card"], fg=C["text"], font=FONT_BODY).pack(side="left")
        self._sched_min = tk.Spinbox(r1, from_=0, to=59, width=3,
                                     bg=C["bg_input"], fg=C["text"], font=FONT_BODY,
                                     buttonbackground=C["bg_card"], relief="flat",
                                     insertbackground=C["text"])
        self._sched_min.delete(0,"end"); self._sched_min.insert(0,"00")
        self._sched_min.pack(side="left", padx=4)

        # O que executar
        r2 = tk.Frame(inner, bg=C["bg_card"])
        r2.pack(fill="x", pady=(8,4))
        tk.Label(r2, text="O que executar:", bg=C["bg_card"],
                 fg=C["text"], font=("Segoe UI",10,"bold")).pack(anchor="w")

        self._sched_vars = {
            "theme":  tk.BooleanVar(value=True),
            "scan":   tk.BooleanVar(value=True),
            "delete": tk.BooleanVar(value=False),
        }
        for key, lbl in [("theme","🎨  Restaurar tema Windows"),
                         ("scan", "🔍  Escanear pastas do usuário"),
                         ("delete","🗑  Excluir tudo sem confirmação ⚠")]:
            tk.Checkbutton(r2, variable=self._sched_vars[key],
                           text=f"  {lbl}", font=FONT_BODY,
                           bg=C["bg_card"], fg=C["text"],
                           activebackground=C["bg_card"],
                           selectcolor=C["accent_dim"],
                           relief="flat", cursor="hand2").pack(anchor="w", pady=2)

        bf2 = tk.Frame(sc_sched, bg=C["bg_card"])
        bf2.pack(padx=16, pady=(0,12), anchor="w")
        _btn(bf2, "🗓  Criar / Atualizar",  self._sched_create,          width=22).pack(side="left", padx=(0,8))
        _btn(bf2, "🗑  Remover",             self._sched_delete, "danger", width=14).pack(side="left", padx=(0,8))
        _btn(bf2, "🔄  Status",              self._sched_status_check,    width=12).pack(side="left")

        _hsep(p, pady=4)

        # Status / Log
        self._sched_status_lbl2 = tk.Label(
            p, text="Clique em 'Status' para consultar o agendamento atual.",
            bg=C["bg_card"], fg=C["text_dim"], font=FONT_BODY,
            justify="left", anchor="w", padx=16, pady=8, wraplength=700
        )
        self._sched_status_lbl2.pack(fill="x", padx=20, pady=(0,4))

        tk.Label(p, text="Log:", bg=C["bg"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w", padx=20)
        self._sched_log = _log_box(p, 6)

    # ── Página: Usuários ──────────────────────────────────────────────────────

    # ── Página: Usuários ──────────────────────────────────────────────────────

    def _build_page_users(self):
        outer = tk.Frame(self._content, bg=C["bg"])
        self._pages["users"] = outer

        # Scroll vertical — resolve o corte em resoluções baixas
        scroll_outer, p = _scrollable_frame(outer)
        scroll_outer.pack(fill="both", expand=True)
        _page_title(p, "👥  Gerenciamento de Usuários",
                    "Selecione um usuário, informe credenciais de admin e gerencie senhas e contas.")

        # ── Card: Credenciais de Administrador ────────────────────────────────
        cred_card = _card(p)
        cred_card.pack(fill="x", padx=20, pady=(0, 6))
        tk.Frame(cred_card, bg=C["warning"], height=3).pack(fill="x")

        cred_hdr = tk.Frame(cred_card, bg=C["bg_card"])
        cred_hdr.pack(fill="x", padx=16, pady=(10, 4))
        tk.Label(cred_hdr, text="🔐  Credenciais de Administrador",
                 bg=C["bg_card"], fg=C["warning"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(cred_hdr,
                 text="Selecione o admin na lista, informe a senha e clique em Autenticar.",
                 bg=C["bg_card"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w")

        cred_row = tk.Frame(cred_card, bg=C["bg_card"])
        cred_row.pack(fill="x", padx=16, pady=(4, 6))

        # Dropdown: apenas admins detectados no sistema
        tk.Label(cred_row, text="Admin:", bg=C["bg_card"],
                 fg=C["text"], font=FONT_BODY, width=8, anchor="w").pack(side="left")

        self._admin_var = tk.StringVar()
        self._admin_combo = ttk.Combobox(
            cred_row, textvariable=self._admin_var,
            state="readonly", width=20, font=FONT_BODY
        )
        self._admin_combo.pack(side="left", padx=(0, 14))

        # Senha
        tk.Label(cred_row, text="Senha:", bg=C["bg_card"],
                 fg=C["text"], font=FONT_BODY, width=7, anchor="w").pack(side="left")

        self._admin_pwd_var = tk.StringVar()
        self._admin_pwd_entry = tk.Entry(
            cred_row, textvariable=self._admin_pwd_var,
            show="●", bg=C["bg_input"], fg=C["text"],
            font=FONT_BODY, relief="flat", bd=4,
            insertbackground=C["text"], width=22
        )
        self._admin_pwd_entry.pack(side="left", padx=(0, 6))
        self._admin_pwd_entry.bind("<Return>", lambda e: self._creds_authenticate())

        # Olho
        self._show_admin_pwd = tk.BooleanVar(value=False)
        tk.Button(
            cred_row, text="👁", bg=C["bg_card"], fg=C["text_dim"],
            activebackground=C["bg_card"], relief="flat", cursor="hand2",
            bd=0, font=("Segoe UI Emoji", 12),
            command=lambda: (
                self._show_admin_pwd.set(not self._show_admin_pwd.get()),
                self._admin_pwd_entry.config(
                    show="" if self._show_admin_pwd.get() else "●")
            )
        ).pack(side="left", padx=(0, 10))

        _btn(cred_row, "🔓  Autenticar",
             self._creds_authenticate, width=14).pack(side="left", padx=(0, 6))
        _btn(cred_row, "✗  Limpar",
             self._creds_clear, "danger", width=10).pack(side="left")

        # Status da autenticação
        self._cred_status_lbl = tk.Label(
            cred_card,
            text="⚪  Sem credenciais — operações requerem execução como Administrador.",
            bg=C["bg_card"], fg=C["text_muted"],
            font=FONT_SMALL, padx=16, anchor="w"
        )
        self._cred_status_lbl.pack(fill="x", pady=(0, 8))

        # ── Barra de ações ────────────────────────────────────────────────────
        ab = tk.Frame(p, bg=C["bg"])
        ab.pack(fill="x", padx=20, pady=(4, 4))
        _btn(ab, "🔄  Atualizar Lista", self._users_refresh, width=18).pack(side="left", padx=(0, 6))
        self._users_sum_lbl = tk.Label(ab, text="", bg=C["bg"],
                                       fg=C["text_dim"], font=FONT_SMALL)
        self._users_sum_lbl.pack(side="right")

        # Legenda
        leg = tk.Frame(p, bg=C["bg"])
        leg.pack(fill="x", padx=22, pady=(0, 2))
        for sym, col, txt in [
            ("→", C["accent"],  "Você"),
            ("★", C["warning"], "Admin"),
            ("  ", C["text"],   "Ativo"),
            ("  ", C["text_muted"], "Desativado"),
        ]:
            tk.Label(leg, text=f"{sym} {txt}", bg=C["bg"],
                     fg=col, font=FONT_TINY).pack(side="left", padx=(0, 14))

        # ── Tabela ────────────────────────────────────────────────────────────
        tf = tk.Frame(p, bg=C["bg"])
        tf.pack(fill="x", padx=20, pady=(0, 4))

        ucols = ("nome", "nome_completo", "status", "ultimo_login", "pwd_expira", "grupos")
        self._users_tree = ttk.Treeview(
            tf, columns=ucols, show="headings",
            selectmode="browse", style="WB.Treeview", height=7
        )
        for col, hd, w, stretch, anchor in [
            ("nome",          "Usuário",        140, False, "w"),
            ("nome_completo", "Nome Completo",  170, True,  "w"),
            ("status",        "Status",          80, False, "center"),
            ("ultimo_login",  "Último Login",   140, False, "center"),
            ("pwd_expira",    "Senha Expira",   130, False, "center"),
            ("grupos",        "Grupos",         200, True,  "w"),
        ]:
            self._users_tree.heading(col, text=hd)
            self._users_tree.column(col, width=w, minwidth=60,
                                    stretch=stretch, anchor=anchor)

        uvsb = ttk.Scrollbar(tf, orient="vertical", command=self._users_tree.yview)
        self._users_tree.configure(yscrollcommand=uvsb.set)
        self._users_tree.grid(row=0, column=0, sticky="nsew")
        uvsb.grid(row=0, column=1, sticky="ns")
        tf.columnconfigure(0, weight=1)

        self._users_tree.tag_configure("enabled",  background=C["bg_row"],  foreground=C["text_row"])
        self._users_tree.tag_configure("disabled", background=C["bg_row"],  foreground=C["text_muted"])
        self._users_tree.tag_configure("current",  background=C["blue_dim"],foreground=C["accent_light"])
        self._users_tree.tag_configure("admin",    background=C["bg_row"],  foreground=C["accent"])
        self._users_tree.bind("<<TreeviewSelect>>", self._users_on_select)

        # ── Painel de ações ───────────────────────────────────────────────────
        _hsep(p, pady=3)
        action_card = _card(p)
        action_card.pack(fill="x", padx=20, pady=3)
        tk.Frame(action_card, bg=C["accent"], height=3).pack(fill="x")
        ac = tk.Frame(action_card, bg=C["bg_card"])
        ac.pack(fill="x", padx=16, pady=8)

        self._sel_user_lbl = tk.Label(
            ac, text="← Selecione um usuário na lista acima.",
            bg=C["bg_card"], fg=C["text_dim"],
            font=("Segoe UI", 11, "bold")
        )
        self._sel_user_lbl.pack(anchor="w", pady=(0, 6))

        # Nome completo
        nf = tk.Frame(ac, bg=C["bg_card"])
        nf.pack(fill="x", pady=(0, 5))
        tk.Label(nf, text="Nome completo:", bg=C["bg_card"], fg=C["text"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        self._full_name_var = tk.StringVar()
        tk.Entry(nf, textvariable=self._full_name_var,
                 bg=C["bg_input"], fg=C["text"], font=FONT_BODY,
                 relief="flat", bd=4, insertbackground=C["text"], width=24
                 ).pack(side="left", padx=(0, 8))
        _btn(nf, "💾  Salvar Nome", self._users_save_full_name, width=16).pack(side="left")

        # Nova senha
        pf = tk.Frame(ac, bg=C["bg_card"])
        pf.pack(fill="x", pady=(0, 5))
        tk.Label(pf, text="Nova senha:", bg=C["bg_card"], fg=C["text"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        self._new_pwd_var = tk.StringVar()
        npe = tk.Entry(pf, textvariable=self._new_pwd_var, show="●",
                       bg=C["bg_input"], fg=C["text"], font=FONT_BODY,
                       relief="flat", bd=4, insertbackground=C["text"], width=24)
        npe.pack(side="left", padx=(0, 6))
        self._show_new_pwd = tk.BooleanVar(value=False)
        tk.Button(pf, text="👁", bg=C["bg_card"], fg=C["text_dim"],
                  activebackground=C["bg_card"], relief="flat", cursor="hand2",
                  bd=0, font=("Segoe UI Emoji", 12),
                  command=lambda: (
                      self._show_new_pwd.set(not self._show_new_pwd.get()),
                      npe.config(show="" if self._show_new_pwd.get() else "●")
                  )).pack(side="left", padx=(0, 10))
        _btn(pf, "🔑  Alterar Senha", self._users_change_pwd, width=16).pack(side="left")

        # Expiração
        ef = tk.Frame(ac, bg=C["bg_card"])
        ef.pack(fill="x", pady=(0, 5))
        tk.Label(ef, text="Senha:", bg=C["bg_card"], fg=C["text"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        for lbl, cmd in [
            ("🔒  Nunca Expira",      self._users_never_expires),
            ("🗓  Expira c/ Política", self._users_set_expires),
            ("🔄  Forçar Troca Login", self._users_force_change),
        ]:
            _btn(ef, lbl, cmd, width=20).pack(side="left", padx=(0, 6))

        # Conta
        af = tk.Frame(ac, bg=C["bg_card"])
        af.pack(fill="x", pady=(0, 2))
        tk.Label(af, text="Conta:", bg=C["bg_card"], fg=C["text"],
                 font=FONT_BODY, width=14, anchor="w").pack(side="left")
        _btn(af, "✔  Ativar",    self._users_enable,           width=14).pack(side="left", padx=(0, 6))
        _btn(af, "✘  Desativar", self._users_disable, "danger", width=14).pack(side="left")

        # Log
        _hsep(p, pady=3)
        tk.Label(p, text="Log:", bg=C["bg"], fg=C["text_dim"],
                 font=FONT_SMALL).pack(anchor="w", padx=20)
        self._users_log = _log_box(p, 4)

        # Estado
        self._users_data    = []
        self._admin_users   = []
        self._selected_user = None
        self._users_loaded  = False   # carrega apenas quando aba for acessada

    # ── Credenciais ───────────────────────────────────────────────────────────

    def _users_load_admins(self):
        def task():
            admins = user_manager.get_admin_users()
            # Filtra apenas nomes válidos (sem espaços = não são mensagens de erro)
            admins = [a for a in admins
                      if a and len(a) <= 64
                      and not any(c in a for c in ".,;:!?()[]{}\\/<>")]
            self._admin_users = admins
            values = admins if admins else ["(sem admin detectado)"]
            self.after(0, lambda: self._admin_combo.config(values=values))
            if admins:
                self.after(0, lambda: self._admin_var.set(admins[0]))
            users = user_manager.list_users()
            # Filtra apenas usuários com nome válido
            users = [u for u in users
                     if u.get("name") and len(u["name"]) <= 64
                     and not any(c in u["name"] for c in ".,;!?()[]{}")]
            self._users_data = users
            current = user_manager.get_current_user()
            self.after(0, lambda: self._users_fill_tree(users, current, admins))
            self.after(0, lambda: self._users_sum_lbl.config(
                text=f"{len(users)} usuário(s)  •  "
                     f"{sum(1 for u in users if u['enabled'])} ativo(s)"))
        threading.Thread(target=task, daemon=True).start()

    def _creds_authenticate(self):
        username = self._admin_var.get().strip()
        password = self._admin_pwd_var.get()
        if not username or username.startswith("("):
            messagebox.showwarning("Admin não selecionado",
                                   "Selecione um administrador na lista."); return
        if not password:
            messagebox.showwarning("Senha vazia",
                                   "Digite a senha do administrador.")
            self._admin_pwd_entry.focus_set(); return

        def task():
            self.after(0, lambda: self._cred_status_lbl.config(
                text="⏳  Validando...", fg=C["info"]))
            ok, msg = validate_credentials(username, password)
            if ok:
                self._cred_cache.set(username, password)
                self._log(self._users_log, f"✔ Credenciais de '{username}' validadas.")

                # Pergunta se quer relançar com privilégios elevados
                def _ask_relaunch():
                    if is_elevated():
                        # Já é admin — apenas recarrega a lista
                        self._cred_status_lbl.config(
                            text=f"✔  Rodando como Administrador. Operações privilegiadas ativas.",
                            fg=C["success"])
                        self._admin_pwd_var.set("")
                        users = user_manager.list_users(self._cred_cache)
                        users = [u for u in users
                                 if u.get("name") and len(u["name"]) <= 64
                                 and not any(c in u["name"] for c in ".,;!?()[]{}")]
                        self._users_data = users
                        current = user_manager.get_current_user()
                        self._users_fill_tree(users, current, self._admin_users)
                    else:
                        answer = messagebox.askyesno(
                            "Relançar como Administrador",
                            f"Credenciais de '{username}' validadas.\n\n"
                            "Para que TODAS as operações funcionem com privilégios\n"
                            "elevados, o programa precisa ser relançado como\n"
                            f"Administrador ({username}).\n\n"
                            "Deseja relançar agora?\n\n"
                            "(Clique Não para continuar sem reiniciar — algumas\n"
                            "operações usarão as credenciais via PowerShell.)"
                        )
                        if answer:
                            from credential_helper import relaunch_as_admin
                            launched = relaunch_as_admin(username, password)
                            if launched:
                                self._log(self._users_log,
                                          "Relançando com privilégios elevados...")
                                self.after(500, self._quit_app)
                            else:
                                messagebox.showerror(
                                    "Falha no relançamento",
                                    "Não foi possível relançar como administrador.\n"
                                    "Verifique se o UAC está habilitado.\n\n"
                                    "Continuando com credenciais via PowerShell.")
                                self._cred_status_lbl.config(
                                    text=f"✔  Autenticado como '{username}' (PowerShell).",
                                    fg=C["success"])
                        else:
                            self._cred_status_lbl.config(
                                text=f"✔  Autenticado como '{username}' — operações via PowerShell.",
                                fg=C["success"])
                            self._admin_pwd_var.set("")
                            users = user_manager.list_users(self._cred_cache)
                            users = [u for u in users
                                     if u.get("name") and len(u["name"]) <= 64
                                     and not any(c in u["name"] for c in ".,;!?()[]{}")]
                            self._users_data = users
                            current = user_manager.get_current_user()
                            self._users_fill_tree(users, current, self._admin_users)

                self.after(0, _ask_relaunch)
            else:
                self._cred_cache.clear()
                self.after(0, lambda: self._cred_status_lbl.config(
                    text=f"✘  Falha: {msg}", fg=C["danger"]))
                self._log(self._users_log, f"✘ Autenticação falhou: {msg}")
        threading.Thread(target=task, daemon=True).start()

    def _creds_clear(self):
        self._cred_cache.clear()
        self._admin_pwd_var.set("")
        self._cred_status_lbl.config(
            text="⚪  Credenciais removidas da sessão.", fg=C["text_muted"])
        self._log(self._users_log, "Credenciais da sessão limpas.")

    def _creds_needed(self) -> bool:
        if user_manager.is_admin() or self._cred_cache.has_credentials:
            return False
        messagebox.showwarning(
            "Credenciais necessárias",
            "Esta operação requer privilégios de Administrador.\n\n"
            "No painel acima:\n"
            "1. Selecione o usuário administrador\n"
            "2. Digite a senha\n"
            "3. Clique em 'Autenticar'"
        )
        return True

    # ── Ações: Usuários ───────────────────────────────────────────────────────

    def _users_refresh(self):
        self._log(self._users_log, "Atualizando lista...")
        def task():
            creds = self._cred_cache if self._cred_cache.has_credentials else None
            users = user_manager.list_users(creds)
            users = [u for u in users
                     if u.get("name") and len(u["name"]) <= 64
                     and not any(c in u["name"] for c in ".,;!?()[]{}")]
            self._users_data = users
            current = user_manager.get_current_user()
            self.after(0, lambda: self._users_fill_tree(
                users, current, self._admin_users))
            self.after(0, lambda: self._users_sum_lbl.config(
                text=f"{len(users)} usuário(s)  •  "
                     f"{sum(1 for u in users if u['enabled'])} ativo(s)"))
            self._log(self._users_log, f"✔ {len(users)} usuário(s) encontrado(s).")
        threading.Thread(target=task, daemon=True).start()

    def _users_fill_tree(self, users: list, current_user: str, admins: list = None):
        adm_lower = [a.lower() for a in (admins or [])]
        for r in self._users_tree.get_children():
            self._users_tree.delete(r)
        for u in users:
            is_cur = u["name"].lower() == current_user.lower()
            is_adm = u["name"].lower() in adm_lower
            if is_cur:
                tag = "current"
            elif is_adm:
                tag = "admin"
            elif u["enabled"]:
                tag = "enabled"
            else:
                tag = "disabled"
            prefix = "→ " if is_cur else ("★ " if is_adm else "   ")
            self._users_tree.insert("", "end", iid=u["name"], tags=(tag,),
                                    values=(prefix + u["name"],
                                            u["full_name"] or "—",
                                            u["status"],
                                            u["last_logon"],
                                            u["password_expires"],
                                            u["groups"]))

    def _users_on_select(self, _=None):
        sel = self._users_tree.selection()
        if not sel: return
        self._selected_user = sel[0]
        user = next((u for u in self._users_data
                     if u["name"] == self._selected_user), None)
        if user:
            adm_mark = " ★ Admin" if self._selected_user.lower() in [
                a.lower() for a in self._admin_users] else ""
            self._sel_user_lbl.config(
                text=f"👤  {user['name']}{adm_mark}  —  "
                     f"{'Ativa' if user['enabled'] else 'Desativada'}  •  {user['groups']}",
                fg=C["accent"] if user["enabled"] else C["text_muted"]
            )
            # Preenche o campo de nome completo
            self._full_name_var.set(user.get("full_name", "") or "")

    def _get_selected_username(self):
        if not self._selected_user:
            messagebox.showwarning("Nenhum usuário", "Selecione um usuário na lista.")
            return None
        return self._selected_user

    def _users_save_full_name(self):
        u = self._get_selected_username()
        if not u: return
        if self._creds_needed(): return
        name = self._full_name_var.get().strip()
        creds = self._cred_cache if self._cred_cache.has_credentials else None
        def task():
            ok = user_manager.change_full_name(
                u, name, lambda m: self._log(self._users_log, m), creds)
            if ok:
                self.after(0, lambda: self._set_status(f"✔ Nome completo de '{u}' atualizado."))
                self.after(0, self._users_refresh)
            else:
                self.after(0, lambda: messagebox.showerror(
                    "Falha", f"Não foi possível atualizar o nome de '{u}'."))
        threading.Thread(target=task, daemon=True).start()

    def _users_change_pwd(self):
        u = self._get_selected_username()
        if not u: return
        if self._creds_needed(): return
        pwd = self._new_pwd_var.get()
        if not pwd:
            messagebox.showwarning("Senha vazia", "Digite a nova senha."); return
        if not messagebox.askyesno("Confirmar",
                f"Alterar senha de '{u}'?\n\nComunique o usuário após alterar."): return

        def task():
            # Se já rodando como admin, usa net user diretamente (mais confiável)
            if is_elevated():
                ok = user_manager.change_password_direct(
                    u, pwd, lambda m: self._log(self._users_log, m))
            else:
                creds = self._cred_cache if self._cred_cache.has_credentials else None
                ok = user_manager.change_password(
                    u, pwd, lambda m: self._log(self._users_log, m), creds)

            if ok:
                self.after(0, lambda: self._new_pwd_var.set(""))
                self.after(0, lambda: self._set_status(f"✔ Senha de '{u}' alterada."))
                self.after(0, lambda: messagebox.showinfo(
                    "Senha Alterada",
                    f"✔ Senha do usuário '{u}' alterada com sucesso.\n\n"
                    f"O usuário pode utilizar a nova senha imediatamente."))
            else:
                self.after(0, lambda: messagebox.showerror(
                    "Falha ao Alterar Senha",
                    f"✘ Não foi possível alterar a senha de '{u}'.\n\n"
                    f"Verifique:\n"
                    f"• Credenciais de admin corretas\n"
                    f"• Nova senha atende à política (mín. 8 caracteres, maiúscula, número)\n"
                    f"• Log abaixo para detalhes"))
        threading.Thread(target=task, daemon=True).start()

    def _users_never_expires(self):
        u = self._get_selected_username()
        if not u: return
        if self._creds_needed(): return
        creds = self._cred_cache if self._cred_cache.has_credentials else None
        def task():
            user_manager.set_password_never_expires(
                u, True, lambda m: self._log(self._users_log, m), creds)
            self.after(0, self._users_refresh)
        threading.Thread(target=task, daemon=True).start()

    def _users_set_expires(self):
        u = self._get_selected_username()
        if not u: return
        if self._creds_needed(): return
        creds = self._cred_cache if self._cred_cache.has_credentials else None
        def task():
            user_manager.set_password_never_expires(
                u, False, lambda m: self._log(self._users_log, m), creds)
            self.after(0, self._users_refresh)
        threading.Thread(target=task, daemon=True).start()

    def _users_force_change(self):
        u = self._get_selected_username()
        if not u: return
        if self._creds_needed(): return
        if not messagebox.askyesno("Forçar troca",
                f"'{u}' será obrigado a trocar a senha no próximo login.\nContinuar?"): return
        creds = self._cred_cache if self._cred_cache.has_credentials else None
        def task():
            user_manager.force_password_change_on_next_logon(
                u, lambda m: self._log(self._users_log, m), creds)
        threading.Thread(target=task, daemon=True).start()

    def _users_enable(self):
        u = self._get_selected_username()
        if not u: return
        if self._creds_needed(): return
        creds = self._cred_cache if self._cred_cache.has_credentials else None
        def task():
            user_manager.set_account_enabled(
                u, True, lambda m: self._log(self._users_log, m), creds)
            self.after(0, self._users_refresh)
        threading.Thread(target=task, daemon=True).start()

    def _users_disable(self):
        u = self._get_selected_username()
        if not u: return
        if self._creds_needed(): return
        if u.lower() == user_manager.get_current_user().lower():
            messagebox.showerror("Inválido", "Não pode desativar o usuário atual."); return
        if not messagebox.askyesno("Desativar",
                f"Desativar '{u}'?\nO usuário não conseguirá fazer login."): return
        creds = self._cred_cache if self._cred_cache.has_credentials else None
        def task():
            user_manager.set_account_enabled(
                u, False, lambda m: self._log(self._users_log, m), creds)
            self.after(0, self._users_refresh)
        threading.Thread(target=task, daemon=True).start()

    # ── Página: Progresso ─────────────────────────────────────────────────────

    def _build_page_progress(self):
        p = tk.Frame(self._content, bg=C["bg"])
        self._pages["progress"] = p
        _page_title(p, "📊  Progresso das Etapas",
                    "Acompanhe em tempo real o que foi concluído e o que está pendente.")

        # ── Barra global ──────────────────────────────────────────────────────
        pb_f = tk.Frame(p, bg=C["bg"])
        pb_f.pack(fill="x", padx=20, pady=(0, 6))

        pb_header = tk.Frame(pb_f, bg=C["bg"])
        pb_header.pack(fill="x")
        tk.Label(pb_header, text="Progresso Geral:", bg=C["bg"],
                 fg=C["text"], font=FONT_BODY).pack(side="left")
        self._pb_pct = tk.Label(pb_header, text="0%", bg=C["bg"],
                                fg=C["accent"], font=("Segoe UI", 10, "bold"))
        self._pb_pct.pack(side="right")

        bar_bg = tk.Frame(pb_f, bg=C["progress_bg"], height=22)
        bar_bg.pack(fill="x", pady=4)
        bar_bg.pack_propagate(False)
        self._pb_inner = tk.Frame(bar_bg, bg=C["progress_fg"], height=22)
        self._pb_inner.place(x=0, y=0, relheight=1, relwidth=0)
        # Texto dentro da barra
        self._pb_bar_lbl = tk.Label(bar_bg, text="", bg=C["progress_fg"],
                                    fg="#0d0b09", font=FONT_TINY)
        self._pb_bar_lbl.place(relx=0.5, rely=0.5, anchor="center")

        _hsep(p, pady=4)

        # ── Cards de etapas (estilo timeline vertical) ────────────────────────
        steps_frame = tk.Frame(p, bg=C["bg"])
        steps_frame.pack(fill="x", padx=20, pady=4)

        defs = [
            ("🎨", "Restaurar Tema",   "Cores, wallpaper, cursores, proteção de tela"),
            ("🔍", "Varrer Arquivos",  "Escanear pastas do perfil do usuário"),
            ("📋", "Selecionar",       "Marcar itens para exclusão"),
            ("🗑", "Excluir",          "Remover arquivos e pastas selecionados"),
        ]

        self._step_cards = []
        for i, (icon, title, desc) in enumerate(defs):
            # Linha de conexão entre etapas
            if i > 0:
                conn = tk.Frame(steps_frame, bg=C["border"], width=2, height=20)
                conn.pack(pady=0)

            row = tk.Frame(steps_frame, bg=C["bg_card"], relief="flat")
            row.pack(fill="x", pady=1)

            # Faixa lateral de status (esquerda)
            side_bar = tk.Frame(row, bg=C["step_pending"], width=6)
            side_bar.pack(side="left", fill="y")

            # Ícone em círculo
            icon_frame = tk.Frame(row, bg=C["step_pending"], width=48, height=48)
            icon_frame.pack(side="left", padx=(8, 0), pady=8)
            icon_frame.pack_propagate(False)
            icon_lbl = tk.Label(icon_frame, text=icon,
                                bg=C["step_pending"], fg=C["bg_header"],
                                font=("Segoe UI Emoji", 16))
            icon_lbl.place(relx=0.5, rely=0.5, anchor="center")

            # Texto
            txt_f = tk.Frame(row, bg=C["bg_card"])
            txt_f.pack(side="left", fill="x", expand=True, padx=12, pady=6)

            title_lbl = tk.Label(txt_f, text=f"{i+1}. {title}",
                                 bg=C["bg_card"], fg=C["text_muted"],
                                 font=("Segoe UI", 10, "bold"), anchor="w")
            title_lbl.pack(anchor="w")

            desc_lbl = tk.Label(txt_f, text=desc,
                                bg=C["bg_card"], fg=C["text_muted"],
                                font=FONT_SMALL, anchor="w")
            desc_lbl.pack(anchor="w")

            # Status à direita
            status_lbl = tk.Label(row, text="⏳ Aguardando",
                                  bg=C["bg_card"], fg=C["step_pending"],
                                  font=("Segoe UI", 9, "bold"), width=16)
            status_lbl.pack(side="right", padx=12)

            # Guarda referências
            row._side_bar   = side_bar
            row._icon_frame = icon_frame
            row._icon_lbl   = icon_lbl
            row._title_lbl  = title_lbl
            row._desc_lbl   = desc_lbl
            row._status_lbl = status_lbl
            row._top_bar    = side_bar   # compatibilidade com _update_step
            self._step_cards.append(row)

        _hsep(p, pady=4)

        # ── Resultados ────────────────────────────────────────────────────────
        rc = _card(p)
        rc.pack(fill="x", padx=20, pady=4)
        tk.Frame(rc, bg=C["accent"], height=3).pack(fill="x")
        tk.Label(rc, text="Resultados:", bg=C["bg_card"], fg=C["accent"],
                 font=("Segoe UI", 10, "bold"), pady=6, padx=16).pack(anchor="w")
        self._result_lbl = tk.Label(rc, text="Nenhuma operação realizada ainda.",
                                    bg=C["bg_card"], fg=C["text_dim"],
                                    font=FONT_BODY, padx=16, pady=6,
                                    justify="left", anchor="w")
        self._result_lbl.pack(fill="x")

        _hsep(p, pady=4)
        tk.Label(p, text="Log Completo:", bg=C["bg"],
                 fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w", padx=20)
        self._progress_log = _log_box(p, 7)

    def _build_statusbar(self):
        bar = tk.Frame(self, bg=C["bg_header"], height=26)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=C["accent"], height=1).place(x=0, y=0, relwidth=1)
        self._status_var = tk.StringVar(value="Pronto.")
        tk.Label(bar, textvariable=self._status_var,
                 bg=C["bg_header"], fg=C["text_dim"],
                 font=FONT_SMALL, anchor="w").pack(side="left", padx=14)
        self._running_lbl = tk.Label(bar, text="",
                                     bg=C["bg_header"], fg=C["accent"],
                                     font=FONT_SMALL)
        self._running_lbl.pack(side="right", padx=14)

    # ── Utilitários de UI ─────────────────────────────────────────────────────

    def _log(self, widget, msg):
        def _w():
            widget.config(state="normal")
            widget.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
            widget.see("end")
            widget.config(state="disabled")
        self.after(0, _w)

    def _log_all(self, msg):
        for w in (self._theme_log, self._auto_log, self._progress_log):
            self._log(w, msg)
        logger.info(msg)

    def _set_status(self, txt):
        self.after(0, lambda: self._status_var.set(txt))

    def _set_running(self, running, msg=""):
        self._running = running
        self.after(0, lambda: self._running_lbl.config(
            text="⚙ Processando..." if running else msg))

    def _set_progress(self, pct):
        def _u():
            self._pb_inner.place(relwidth=min(pct, 1.0))
            self._pb_pct.config(text=f"{int(pct * 100)}%")
        self.after(0, _u)

    def _update_step(self, idx, state):
        cfg = {
            "pending": ("⏳ Aguardando",    C["step_pending"], C["text_muted"], C["step_pending"]),
            "active":  ("⚙ Em andamento…", C["step_active"],  C["text"],       C["step_active"]),
            "done":    ("✔ Concluído",      C["step_done"],    C["text"],       C["step_done"]),
            "error":   ("✘ Erro",           C["danger"],       C["text"],       C["danger"]),
        }
        stxt, scol, tcol, bcol = cfg.get(state, cfg["pending"])
        icons = {"pending":"○","active":"◉","done":"●","error":"✘"}
        icols = {"pending":C["step_pending"],"active":C["step_active"],
                 "done":C["step_done"],"error":C["danger"]}

        def _u():
            if idx < len(self._step_cards):
                c = self._step_cards[idx]
                c._status_lbl.config(text=stxt, fg=scol)
                c._title_lbl.config(fg=tcol)
                c._top_bar.config(bg=bcol)
            if idx < len(self._step_labels):
                sl = self._step_labels[idx]
                sl["icon"].config(text=icons.get(state,"○"),
                                  fg=icols.get(state, C["step_pending"]))
                sl["text"].config(fg=C["text"] if state != "pending" else C["text_muted"])
        self.after(0, _u)

    def _center(self):
        """Centraliza a janela. Não faz nada se estiver maximizada."""
        if self.state() == "zoomed":
            return
        self.update_idletasks()
        w  = self.winfo_width()
        h  = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = max(0, (sw - w) // 2)
        y  = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _show_safe(self, key):
        self.after(0, lambda: self._show(key))

    # ── Ações: Tema ───────────────────────────────────────────────────────────

    def _run_theme_restore(self):
        if self._running: return
        sel = {k for k, v in self._theme_vars.items() if v.get()}
        if not sel:
            messagebox.showwarning("Nada selecionado","Selecione ao menos uma opção."); return
        self._exec_theme(sel)

    def _run_theme_all(self):
        if self._running: return
        for v in self._theme_vars.values(): v.set(True)
        self._exec_theme(set(self._theme_vars.keys()))

    def _exec_theme(self, sel):
        funcs = {
            "wallpaper":       theme_restore.restore_wallpaper,
            "screensaver":     theme_restore.restore_screensaver,
            "lock_screen":     theme_restore.restore_lock_screen,
            "cursors":         theme_restore.restore_cursors,
            "colors":          theme_restore.restore_colors,
            "browser_history": theme_restore.clear_browser_history,
            "recycle_bin":     theme_restore.empty_recycle_bin,
        }
        def task():
            self._set_running(True)
            self._update_step(0, "active")
            ok = 0
            for i, key in enumerate(sel):
                if key in funcs:
                    if funcs[key](lambda m: self._log_all(m)): ok += 1
                self._set_progress((i + 1) / (len(sel) * 2))
            self._set_progress(1.0)
            self._update_step(0, "done")
            self._set_running(False, f"✔ Tema ({ok}/{len(sel)})")
            self._set_status(f"Tema restaurado: {ok}/{len(sel)} etapas.")
        threading.Thread(target=task, daemon=True).start()
        self._show_safe("progress")

    # ── Ações: Varredura ──────────────────────────────────────────────────────

    def _run_scan(self):
        if self._running: return
        def task():
            self._set_running(True)
            self._update_step(1, "active")
            self._set_status("Varrendo pastas…")

            items = []

            # Pastas padrão filtradas pela seleção do usuário
            folder_vars = getattr(self, "_scan_folder_vars", {})
            from file_scanner import PROFILE_FOLDERS, resolve_special_folder, _make_item
            import os

            for key, label in PROFILE_FOLDERS:
                # Se o usuário fez uma seleção, respeita; senão varre tudo
                if folder_vars and not folder_vars.get(key, True):
                    continue
                path = resolve_special_folder(key)
                if not os.path.isdir(path):
                    continue
                self._log_all(f"Escaneando {label}...")
                try:
                    entries = sorted(os.listdir(path),
                                     key=lambda e: (not os.path.isdir(
                                         os.path.join(path, e)), e.lower()))
                    for entry in entries:
                        full = os.path.join(path, entry)
                        item = _make_item(full, path, label, key, depth=0)
                        items.append(item)
                    self._log_all(f"✔ {label}: {len(entries)} item(ns).")
                except Exception as e:
                    self._log_all(f"✘ {label}: {e}")

            # Pastas extras selecionadas pelo usuário
            for folder in getattr(self, "_extra_folders", []):
                self._log_all(f"Escaneando pasta extra: {folder}")
                extra_items = file_scanner.scan_single_folder(
                    folder, lambda m: self._log_all(m))
                items.extend(extra_items)

            self._scan_items = items
            self._check_vars = {i: tk.BooleanVar(value=False) for i in range(len(items))}
            self.after(0, self._fill_tree)
            summary = file_scanner.get_summary(items)
            self._update_result(summary)
            self._update_step(1, "done")
            self._update_step(2, "active")
            self._set_running(False, "✔ Varredura concluída")
            self._set_status(
                f"Usuário: {summary['username']}  •  "
                f"{summary['total_items']} itens  •  {summary['total_size']}"
            )
            self._log_all(
                f"Varredura concluída [{summary['username']}]: "
                f"{summary['total_items']} item(ns) / {summary['total_size']}"
            )
            self.after(0, lambda: self._user_lbl.config(
                text=f"👤 {summary['username']}"))
        threading.Thread(target=task, daemon=True).start()
        self._show_safe("scan")

    def _fill_tree(self):
        """Preenche a Treeview em cascata nativa (col #0 = árvore com setas)."""
        for r in self._tree.get_children():
            self._tree.delete(r)

        for i, item in enumerate(self._scan_items):
            sel_tag = "checked" if item.get("selected") else "unchecked"
            icon    = "📁" if item["is_dir"] else "📄"
            iid     = str(i)

            self._tree.insert(
                "", "end", iid=iid,
                text=f" {icon}  {item['name']}",   # coluna #0 — cascata nativa
                tags=(sel_tag,),
                open=item.get("expanded", False),
                values=(
                    "☑" if item.get("selected") else "☐",
                    item["type"],
                    item["size_str"],
                    item["modified"],
                    item["folder_label"],
                )
            )
            # Pasta com conteúdo → placeholder para mostrar seta ▶
            if item["is_dir"] and item.get("has_children", False) and not item.get("expanded", False):
                self._tree.insert(iid, "end", iid=f"_ph_{iid}",
                                  text="  ⏳ expandindo...", values=("", "", "", "", ""))

        summary = file_scanner.get_summary(self._scan_items)
        sel_count = sum(1 for it in self._scan_items if it.get("selected"))
        self._scan_sum_lbl.config(
            text=f"{summary['total_items']} itens  •  {summary['total_size']}"
                 + (f"  •  {sel_count} selecionado(s)" if sel_count else "")
        )

    def _expand_folder(self, iid: str):
        """Expande uma pasta inserindo filhos como nós filhos reais na árvore."""
        try:
            idx = int(iid)
        except ValueError:
            return
        if idx >= len(self._scan_items):
            return
        item = self._scan_items[idx]
        if not item["is_dir"] or item.get("expanded", False):
            return

        item["expanded"] = True

        # Remove placeholder
        ph = f"_ph_{iid}"
        if self._tree.exists(ph):
            self._tree.delete(ph)

        # Carrega filhos via file_scanner
        child_depth = item.get("depth", 0) + 1
        children = file_scanner.scan_folder_children(
            item["full_path"],
            item["folder_label"],
            item["folder_key"],
            child_depth,
            lambda m: None  # silencioso
        )

        if not children:
            item["has_children"] = False
            return

        base = len(self._scan_items)
        self._scan_items.extend(children)
        for j in range(base, len(self._scan_items)):
            self._check_vars[j] = tk.BooleanVar(value=False)

        for j, child in enumerate(children):
            ci   = base + j
            ciid = str(ci)
            icon = "📁" if child["is_dir"] else "📄"
            self._tree.insert(
                iid, "end", iid=ciid,
                text=f" {icon}  {child['name']}",
                tags=("unchecked",),
                open=False,
                values=(
                    "☐",
                    child["type"],
                    child["size_str"],
                    child["modified"],
                    child["folder_label"],
                )
            )
            # Sub-pasta com filhos → placeholder
            if child["is_dir"] and child.get("has_children", False):
                self._tree.insert(ciid, "end", iid=f"_ph_{ciid}",
                                  text="  ⏳ expandindo...",
                                  values=("", "", "", "", ""))

    def _collapse_folder(self, iid: str):
        """Recolhe uma pasta: remove todos os filhos e marca como não expandida."""
        idx = int(iid)
        if idx >= len(self._scan_items):
            return
        item = self._scan_items[idx]
        if not item.get("expanded", False):
            return
        item["expanded"] = False

        # Remove filhos do Treeview recursivamente
        for child_iid in self._tree.get_children(iid):
            self._tree.delete(child_iid)

        # Adiciona o placeholder de volta
        ph = f"_ph_{iid}"
        if item.get("has_children", False):
            self._tree.insert(iid, "end", iid=ph,
                              values=("", "  ▶ clique para expandir...", "", "", "", "", ""))

        # Remove os filhos do scan_items e check_vars
        # (mantém somente itens cujo path não está dentro do pai)
        parent_path = item["full_path"]
        keep = []
        removed_paths = set()
        for it in self._scan_items:
            try:
                from pathlib import Path
                if it["full_path"] != parent_path and \
                   Path(it["full_path"]).is_relative_to(Path(parent_path)):
                    removed_paths.add(it["full_path"])
                    continue
            except Exception:
                pass
            keep.append(it)
        self._scan_items = keep
        self._check_vars = {i: tk.BooleanVar(value=self._scan_items[i].get("selected", False))
                            for i in range(len(self._scan_items))}

    def _on_tree_click(self, event):
        """Seleção por clique único — qualquer coluna alterna o checkbox."""
        region = self._tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        # Seleciona a linha no Treeview
        self._tree.selection_set(iid)
        # Alterna o estado de seleção
        self._toggle_items()

    def _on_tree_expand(self, event):
        """Chamado quando o usuário expande uma pasta (clica na seta ▶)."""
        iid = self._tree.focus()
        if not iid or iid.startswith("_ph_"):
            return
        try:
            int(iid)  # só processa nós reais (índice numérico)
        except ValueError:
            return
        threading.Thread(target=lambda: (
            self._expand_folder(iid),
        ), daemon=True).start()

    def _on_tree_collapse(self, event):
        """Chamado quando o usuário recolhe uma pasta (clica na seta ▼)."""
        iid = self._tree.focus()
        if not iid or iid.startswith("_ph_"):
            return
        try:
            int(iid)
        except ValueError:
            return
        self._collapse_folder(iid)

    def _collapse_all(self):
        """Recolhe todas as pastas expandidas."""
        for iid in list(self._tree.get_children()):
            try:
                idx = int(iid)
                if self._scan_items[idx].get("expanded", False):
                    self._collapse_folder(iid)
            except (ValueError, IndexError):
                pass

    def _sel_by_folder(self):
        """Abre diálogo para selecionar apenas itens de uma pasta específica."""
        if not self._scan_items:
            messagebox.showinfo("Sem itens", "Execute a varredura primeiro."); return

        # Coleta pastas raiz disponíveis
        folders = sorted(set(it.get("folder_label", "—") for it in self._scan_items))
        if not folders:
            return

        # Janela de seleção
        win = tk.Toplevel(self)
        win.title("Selecionar por Pasta")
        win.geometry("380x320")
        win.configure(bg=C["bg"])
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        tk.Label(win, text="Selecione quais pastas incluir:",
                 bg=C["bg"], fg=C["text"],
                 font=("Segoe UI", 11, "bold")).pack(pady=(16, 8), padx=20, anchor="w")

        # Lista de checkboxes
        scroll_f = tk.Frame(win, bg=C["bg"])
        scroll_f.pack(fill="both", expand=True, padx=20)
        vars_map = {}
        for folder in folders:
            count = sum(1 for it in self._scan_items if it.get("folder_label") == folder)
            var = tk.BooleanVar(value=True)
            vars_map[folder] = var
            tk.Checkbutton(
                scroll_f, text=f"  {folder}  ({count} item(ns))",
                variable=var,
                bg=C["bg"], fg=C["text"], font=FONT_BODY,
                activebackground=C["bg"], selectcolor=C["accent_dim"],
                relief="flat", cursor="hand2", anchor="w"
            ).pack(fill="x", pady=2)

        def _apply():
            selected_folders = {f for f, v in vars_map.items() if v.get()}
            for item in self._scan_items:
                item["selected"] = item.get("folder_label") in selected_folders
            # Atualiza Treeview
            for iid in self._tree.get_children():
                try:
                    idx = int(iid)
                    it  = self._scan_items[idx]
                    sel = it.get("selected", False)
                    dep = it.get("depth", 0)
                    ind = "    " * dep
                    ico = "📁 " if it["is_dir"] else "📄 "
                    nom = ind + ico + it["name"]
                    self._tree.item(iid,
                                    tags=("checked" if sel else "unchecked",),
                                    values=("☑" if sel else "☐", nom,
                                            it["type"], it["size_str"],
                                            it["modified"], it["folder_label"],
                                            it["full_path"]))
                except (ValueError, IndexError):
                    pass
            sel_count = sum(1 for it in self._scan_items if it.get("selected"))
            self._scan_sum_lbl.config(
                text=f"{len(self._scan_items)} itens  •  {sel_count} selecionado(s)")
            win.destroy()

        def _sel_all_f():
            for v in vars_map.values(): v.set(True)

        def _desel_all_f():
            for v in vars_map.values(): v.set(False)

        btn_f = tk.Frame(win, bg=C["bg"])
        btn_f.pack(fill="x", padx=20, pady=(8, 16))
        _btn(btn_f, "✔ Todos",   _sel_all_f,  width=10).pack(side="left", padx=(0, 6))
        _btn(btn_f, "✗ Nenhum",  _desel_all_f,"danger", width=10).pack(side="left", padx=(0, 12))
        _btn(btn_f, "✔ Aplicar", _apply,       width=12).pack(side="right")

    def _sort_scan(self, col):
        """Ordena a tabela de varredura ao clicar no cabeçalho da coluna."""
        if not self._scan_items:
            return
        # Alterna direção se clicar na mesma coluna
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        col_map = {
            "nome":       lambda i: i["name"].lower(),
            "tipo":       lambda i: i["type"].lower(),
            "tamanho":    lambda i: i["size_bytes"],
            "modificado": lambda i: i["modified"],
            "pasta":      lambda i: i.get("folder_label","").lower(),
        }
        key_fn = col_map.get(col, lambda i: i["name"].lower())
        self._scan_items.sort(key=key_fn, reverse=self._sort_rev)
        # Reconstrói os check_vars na nova ordem
        self._check_vars = {i: tk.BooleanVar(value=self._scan_items[i].get("selected", False))
                            for i in range(len(self._scan_items))}
        # Atualiza seta no cabeçalho
        arrow = " ▼" if self._sort_rev else " ▲"
        col_labels = {
            "nome":"Nome / Caminho","tipo":"Tipo","tamanho":"Tamanho",
            "modificado":"Modificado","pasta":"Pasta Raiz"
        }
        for c, lbl in col_labels.items():
            if c == "nome":
                self._tree.heading("#0", text=lbl + (arrow if c == col else ""),
                                   command=lambda: self._sort_scan("nome"))
            else:
                self._tree.heading(c, text=lbl + (arrow if c == col else ""),
                                   command=lambda cc=c: self._sort_scan(cc))
        self._fill_tree()

    def _toggle_items(self, _=None):
        for iid in self._tree.selection():
            if iid.startswith("_ph_"):
                continue
            try:
                idx = int(iid)
            except ValueError:
                continue
            if idx not in self._check_vars:
                continue

            new = not self._check_vars[idx].get()
            self._scan_items[idx]["selected"] = new
            self._check_vars[idx].set(new)

            it   = self._scan_items[idx]
            icon = "📁" if it["is_dir"] else "📄"
            if self._tree.exists(iid):
                self._tree.item(iid,
                                text=f" {icon}  {it['name']}",
                                tags=("checked" if new else "unchecked",),
                                values=("☑" if new else "☐", it["type"],
                                        it["size_str"], it["modified"],
                                        it["folder_label"]))

            # Propaga para filhos carregados
            if it["is_dir"] and it.get("expanded", False):
                parent_path = it["full_path"]
                for j, child in enumerate(self._scan_items):
                    if j == idx:
                        continue
                    try:
                        from pathlib import Path
                        if Path(child["full_path"]).is_relative_to(Path(parent_path)):
                            child["selected"] = new
                            if j in self._check_vars:
                                self._check_vars[j].set(new)
                            cico = "📁" if child["is_dir"] else "📄"
                            ciid = str(j)
                            if self._tree.exists(ciid):
                                self._tree.item(ciid,
                                                text=f" {cico}  {child['name']}",
                                                tags=("checked" if new else "unchecked",),
                                                values=("☑" if new else "☐", child["type"],
                                                        child["size_str"], child["modified"],
                                                        child["folder_label"]))
                    except Exception:
                        pass

        sel_count = sum(1 for it in self._scan_items if it.get("selected"))
        if self._scan_items:
            summary = file_scanner.get_summary(self._scan_items)
            self._scan_sum_lbl.config(
                text=f"{summary['total_items']} itens  •  {summary['total_size']}"
                     + (f"  •  {sel_count} selecionado(s)" if sel_count else ""))

    def _sel_all(self):
        for i, item in enumerate(self._scan_items):
            item["selected"] = True
            if i in self._check_vars: self._check_vars[i].set(True)
            if self._tree.exists(str(i)):
                icon = "📁" if item["is_dir"] else "📄"
                self._tree.item(str(i),
                                text=f" {icon}  {item['name']}",
                                tags=("checked",),
                                values=("☑", item["type"], item["size_str"],
                                        item["modified"], item["folder_label"]))
        sel_count = len(self._scan_items)
        if self._scan_items:
            summary = file_scanner.get_summary(self._scan_items)
            self._scan_sum_lbl.config(
                text=f"{summary['total_items']} itens  •  {sel_count} selecionado(s)")

    def _desel_all(self):
        for i, item in enumerate(self._scan_items):
            item["selected"] = False
            if i in self._check_vars: self._check_vars[i].set(False)
            if self._tree.exists(str(i)):
                icon = "📁" if item["is_dir"] else "📄"
                self._tree.item(str(i),
                                text=f" {icon}  {item['name']}",
                                tags=("unchecked",),
                                values=("☐", item["type"], item["size_str"],
                                        item["modified"], item["folder_label"]))
        if self._scan_items:
            summary = file_scanner.get_summary(self._scan_items)
            self._scan_sum_lbl.config(text=f"{summary['total_items']} itens  •  0 selecionado(s)")

    def _choose_folders_to_scan(self):
        """
        Janela modal CENTRALIZADA no programa principal para escolher pastas.
        Bloqueia a janela principal até o usuário clicar OK ou Cancelar.
        """
        from file_scanner import PROFILE_FOLDERS, resolve_special_folder
        import os

        # ── Cria janela modal ────────────────────────────────────────────
        win = tk.Toplevel(self)
        win.title("Escolher Pastas para Varrer")
        win.configure(bg=C["bg"])
        win.transient(self)          # filho da janela principal
        win.grab_set()               # bloqueia interação com o pai
        win.resizable(False, False)

        WIN_W, WIN_H = 500, 520

        # Centraliza sobre a janela principal
        self.update_idletasks()
        px = self.winfo_rootx() + (self.winfo_width()  - WIN_W) // 2
        py = self.winfo_rooty() + (self.winfo_height() - WIN_H) // 2
        px = max(0, px)
        py = max(0, py)
        win.geometry(f"{WIN_W}x{WIN_H}+{px}+{py}")

        # ── Cabeçalho ────────────────────────────────────────────────────
        hdr = tk.Frame(win, bg=C["bg_header"])
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=C["accent"], height=3).pack(fill="x")
        tk.Label(hdr, text="📂  Escolher Pastas para Varrer",
                 bg=C["bg_header"], fg=C["accent"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(12,2))
        tk.Label(hdr, text="Marque as pastas que deseja incluir. Clique OK para confirmar.",
                 bg=C["bg_header"], fg=C["text_dim"],
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(0,10))

        # ── Lista de pastas ───────────────────────────────────────────────
        list_frame = tk.Frame(win, bg=C["bg_card"])
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0,0))

        # Inicializa estado anterior
        if not hasattr(self, "_scan_folder_vars"):
            self._scan_folder_vars = {}
        if not hasattr(self, "_extra_folders"):
            self._extra_folders = []

        folder_vars = {}
        for key, label in PROFILE_FOLDERS:
            path   = resolve_special_folder(key)
            exists = os.path.isdir(path)
            prev   = self._scan_folder_vars.get(key, True)
            var    = tk.BooleanVar(value=prev and exists)
            folder_vars[key] = (var, label)

            row = tk.Frame(list_frame, bg=C["bg_card"])
            row.pack(fill="x", padx=8, pady=2)

            tk.Checkbutton(
                row, variable=var,
                text=f"  {label}",
                bg=C["bg_card"],
                fg=C["text"] if exists else C["text_muted"],
                activebackground=C["bg_card"],
                selectcolor=C["accent_dim"],
                relief="flat",
                cursor="hand2" if exists else "arrow",
                font=FONT_BODY,
                state="normal" if exists else "disabled",
                width=18, anchor="w"
            ).pack(side="left")

            short = path if len(path) <= 42 else "…" + path[-39:]
            tk.Label(row, text=short, bg=C["bg_card"],
                     fg=C["text_muted"], font=FONT_TINY).pack(side="right", padx=4)

        # Separador + pastas extras
        if self._extra_folders:
            tk.Frame(list_frame, bg=C["border"], height=1).pack(fill="x", padx=8, pady=4)
            for fp in self._extra_folders:
                ev  = tk.BooleanVar(value=True)
                folder_vars[f"_extra_{fp}"] = (ev, os.path.basename(fp))
                er  = tk.Frame(list_frame, bg=C["bg_card"])
                er.pack(fill="x", padx=8, pady=2)
                tk.Checkbutton(er, variable=ev, text=f"  📁 {fp}",
                               bg=C["bg_card"], fg=C["accent"],
                               activebackground=C["bg_card"],
                               selectcolor=C["accent_dim"],
                               relief="flat", cursor="hand2",
                               font=FONT_SMALL).pack(side="left")

        # ── Botão adicionar pasta extra ───────────────────────────────────
        add_f = tk.Frame(win, bg=C["bg"])
        add_f.pack(fill="x", padx=16, pady=4)

        def _add_extra():
            folder = filedialog.askdirectory(title="Adicionar pasta extra", parent=win)
            if folder and folder not in self._extra_folders:
                self._extra_folders.append(folder)
                ev  = tk.BooleanVar(value=True)
                folder_vars[f"_extra_{folder}"] = (ev, os.path.basename(folder))
                er  = tk.Frame(list_frame, bg=C["bg_card"])
                er.pack(fill="x", padx=8, pady=2)
                tk.Checkbutton(er, variable=ev, text=f"  📁 {folder}",
                               bg=C["bg_card"], fg=C["accent"],
                               activebackground=C["bg_card"],
                               selectcolor=C["accent_dim"],
                               relief="flat", cursor="hand2",
                               font=FONT_SMALL).pack(side="left")

        tk.Button(add_f, text="➕  Adicionar pasta extra…",
                  font=FONT_SMALL, bg=C["bg_card"], fg=C["text_dim"],
                  activebackground=C["border"], relief="flat",
                  cursor="hand2", command=_add_extra).pack(side="left")

        # ── Barra de botões OK / Cancelar ─────────────────────────────────
        btn_bar = tk.Frame(win, bg=C["bg_header"])
        btn_bar.pack(fill="x", side="bottom")
        tk.Frame(btn_bar, bg=C["accent"], height=2).pack(fill="x")
        bi = tk.Frame(btn_bar, bg=C["bg_header"])
        bi.pack(fill="x", padx=16, pady=10)

        def _sel_all_f():
            for v, _ in folder_vars.values(): v.set(True)

        def _none_f():
            for v, _ in folder_vars.values(): v.set(False)

        def _ok():
            # Salva seleção das pastas padrão
            self._scan_folder_vars = {}
            for k, (v, lbl) in folder_vars.items():
                if not k.startswith("_extra_"):
                    self._scan_folder_vars[k] = v.get()

            # Atualiza extras
            self._extra_folders = [
                k.replace("_extra_", "", 1)
                for k, (v, _) in folder_vars.items()
                if k.startswith("_extra_") and v.get()
            ]

            # Monta resumo para o label
            sel = [lbl for k, (v, lbl) in folder_vars.items()
                   if not k.startswith("_extra_") and v.get()]
            n_extra = len(self._extra_folders)
            if len(sel) == len(PROFILE_FOLDERS) and n_extra == 0:
                txt = "Todas as pastas do perfil (padrão)"
            elif not sel and not n_extra:
                txt = "⚠ Nenhuma pasta selecionada"
            else:
                txt = ", ".join(sel[:3])
                if len(sel) > 3: txt += f" +{len(sel)-3}"
                if n_extra:     txt += f"  +{n_extra} extra(s)"

            self._chosen_folders_lbl.config(text=txt, fg=C["accent"])
            self._log_all(f"📂 Configurado para varrer: {txt}")
            win.destroy()

        def _cancel():
            win.destroy()

        tk.Button(bi, text="Marcar Tudo",  font=FONT_SMALL, bg=C["bg_card"],
                  fg=C["text_dim"], relief="flat", cursor="hand2",
                  command=_sel_all_f).pack(side="left", padx=(0,6))
        tk.Button(bi, text="Desmarcar",    font=FONT_SMALL, bg=C["bg_card"],
                  fg=C["text_dim"], relief="flat", cursor="hand2",
                  command=_none_f).pack(side="left", padx=(0,16))
        _btn(bi, "✘  Cancelar", _cancel, "danger", width=12).pack(side="right", padx=(6,0))
        _btn(bi, "✔  OK — Confirmar",  _ok, width=20).pack(side="right")

        # Bloqueia até fechar
        win.wait_window()

    def _scan_clear(self):
        """Limpa os resultados e recomeça do zero."""
        if self._running:
            messagebox.showwarning("Em andamento", "Aguarde a operação atual terminar."); return
        if self._scan_items:
            if not messagebox.askyesno("Limpar varredura",
                    "Limpar os resultados da varredura e recomeçar?\n\n"
                    "As pastas selecionadas para varrer serão mantidas."): return
        # Limpa a Treeview e o estado
        for r in self._tree.get_children():
            self._tree.delete(r)
        self._scan_items = []
        self._check_vars = {}
        self._scan_sum_lbl.config(text="Nenhuma varredura realizada.")
        self._set_status("Varredura limpa. Pronto para novo scan.")
        self._log_all("🔄 Varredura limpa. Configure as pastas e clique em 'Escanear'.")
        # Reseta etapas
        self._update_step(1, "pending")
        self._update_step(2, "pending")
        self._update_step(3, "pending")

    def _add_folder(self):
        """Atalho rápido — abre o diálogo de escolha de pastas."""
        self._choose_folders_to_scan()

    def _sel_by_folder(self):
        """Janela para MARCAR para exclusão apenas itens de certas pastas (após varredura)."""
        if not self._scan_items:
            messagebox.showinfo("Sem itens",
                                "Execute a varredura primeiro antes de selecionar por pasta."); return

        folders = sorted(set(it.get("folder_label","—") for it in self._scan_items))

        win = tk.Toplevel(self)
        win.title("Selecionar por Pasta")
        win.configure(bg=C["bg"])
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)

        sw = win.winfo_screenwidth()
        win.geometry(f"{min(420, sw-80)}x360")

        _page_title(win, "📋  Selecionar por Pasta",
                    "Marque as pastas cujos itens devem ser marcados para exclusão.")

        fc = _card(win)
        fc.pack(fill="both", expand=True, padx=16, pady=(0,8))
        tk.Frame(fc, bg=C["danger"], height=2).pack(fill="x")
        fi = tk.Frame(fc, bg=C["bg_card"])
        fi.pack(fill="x", padx=12, pady=8)

        vars_map = {}
        for folder in folders:
            count = sum(1 for it in self._scan_items if it.get("folder_label") == folder)
            sz    = file_scanner._get_size_str(
                sum(it["size_bytes"] for it in self._scan_items
                    if it.get("folder_label") == folder))
            var = tk.BooleanVar(value=False)
            vars_map[folder] = var
            row = tk.Frame(fi, bg=C["bg_card"])
            row.pack(fill="x", pady=2)
            tk.Checkbutton(
                row, variable=var, text=f"  {folder}",
                bg=C["bg_card"], fg=C["text"], font=FONT_BODY,
                activebackground=C["bg_card"], selectcolor=C["accent_dim"],
                relief="flat", cursor="hand2"
            ).pack(side="left")
            tk.Label(row, text=f"{count} item(ns)  •  {sz}",
                     bg=C["bg_card"], fg=C["text_dim"],
                     font=FONT_TINY).pack(side="right", padx=4)

        def _apply():
            sel_folders = {f for f, v in vars_map.items() if v.get()}
            if not sel_folders:
                messagebox.showwarning("Nenhuma pasta",
                                       "Selecione ao menos uma pasta.", parent=win); return
            # Marca itens das pastas escolhidas, desmarca as demais
            for i, item in enumerate(self._scan_items):
                in_sel = item.get("folder_label") in sel_folders
                item["selected"] = in_sel
                if i in self._check_vars:
                    self._check_vars[i].set(in_sel)
                if self._tree.exists(str(i)):
                    icon = "📁" if item["is_dir"] else "📄"
                    self._tree.item(str(i),
                                    text=f" {icon}  {item['name']}",
                                    tags=("checked" if in_sel else "unchecked",),
                                    values=("☑" if in_sel else "☐", item["type"],
                                            item["size_str"], item["modified"],
                                            item["folder_label"]))
            sel_count = sum(1 for it in self._scan_items if it.get("selected"))
            self._scan_sum_lbl.config(
                text=f"{len(self._scan_items)} itens  •  {sel_count} selecionado(s)")
            win.destroy()

        btn_bar = tk.Frame(win, bg=C["bg_header"])
        btn_bar.pack(fill="x", side="bottom")
        tk.Frame(btn_bar, bg=C["accent"], height=1).pack(fill="x")
        bi = tk.Frame(btn_bar, bg=C["bg_header"])
        bi.pack(fill="x", padx=16, pady=10)
        tk.Button(bi, text="Marcar Tudo", font=FONT_SMALL, bg=C["bg_card"],
                  fg=C["text_dim"], relief="flat", cursor="hand2",
                  command=lambda: [v.set(True) for v in vars_map.values()]
                  ).pack(side="left", padx=(0,6))
        _btn(bi, "✘  Cancelar", win.destroy, "danger", width=12).pack(side="right", padx=(6,0))
        _btn(bi, "✔  Aplicar Seleção", _apply, width=20).pack(side="right")

    def _run_delete(self):
        if self._running: return
        sel = [it for it in self._scan_items if it.get("selected")]
        if not sel:
            messagebox.showwarning("Nada selecionado","Marque os itens que deseja excluir."); return
        sz = file_scanner._get_size_str(sum(i["size_bytes"] for i in sel))
        if not messagebox.askyesno("Confirmar Exclusão",
            f"Serão excluídos {len(sel)} item(ns) ({sz}).\n\n"
            "Esta ação é permanente e não pode ser desfeita.\n\nContinuar?"): return
        self._do_delete(sel)

    def _do_delete(self, items):
        count = [0]
        def cb(msg):
            self._log_all(msg)
            if msg.startswith("✔"):
                count[0] += 1
                self._set_progress(count[0] / max(len(items), 1))
        def task():
            self._set_running(True)
            self._update_step(3, "active")
            self._set_progress(0)
            res = file_scanner.delete_items(items, cb)
            self._set_progress(1.0)
            self._update_step(3, "done" if res["failed"]==0 else "error")
            self._set_running(False, f"✔ {res['deleted']} excluído(s)")
            self._set_status(f"Exclusão: {res['deleted']} ok / {res['failed']} falha(s).")
            self._log_all(f"Exclusão: {res['deleted']} ok, {res['failed']} falha(s).")
            deleted_paths = {i["path"] for i in items}
            self._scan_items = [i for i in self._scan_items if i["path"] not in deleted_paths]
            self._check_vars = {j: tk.BooleanVar(value=False) for j in range(len(self._scan_items))}
            self.after(0, self._fill_tree)
        threading.Thread(target=task, daemon=True).start()
        self._show_safe("progress")

    # ── Ações: Automação ──────────────────────────────────────────────────────

    def _run_auto(self):
        if self._running: return
        do_theme   = self._auto_steps["theme"].get()
        do_scan    = self._auto_steps["scan"].get()
        do_delete  = self._auto_steps["delete"].get()
        do_confirm = self._auto_steps["confirm"].get()
        if not any([do_theme, do_scan]):
            messagebox.showwarning("Nada selecionado","Selecione ao menos uma etapa."); return

        def task():
            self._set_running(True)
            self._show_safe("progress")
            total = sum([do_theme, do_scan, do_scan and do_delete])
            done  = 0
            summary = None

            if do_theme:
                self._log_all("══ Automação: Restaurando tema…")
                self._update_step(0, "active")
                res = theme_restore.restore_all_theme(lambda m: self._log_all(m))
                self._update_step(0, "done" if any(res.values()) else "error")
                done += 1; self._set_progress(done / max(total,1))

            if do_scan:
                self._log_all("══ Automação: Varrendo pastas…")
                self._update_step(1, "active")
                items = file_scanner.scan_profile_folders(lambda m: self._log_all(m))
                self._scan_items = items
                self._check_vars = {i: tk.BooleanVar(value=False) for i in range(len(items))}
                self.after(0, self._fill_tree)
                summary = file_scanner.get_summary(items)
                self._update_result(summary)
                self._update_step(1, "done")
                self._update_step(2, "active")
                done += 1; self._set_progress(done / max(total,1))
                self._log_all(f"Varredura [{summary['username']}]: {summary['total_items']} itens / {summary['total_size']}")

            if do_scan and do_delete:
                if do_confirm and summary:
                    ev = threading.Event(); ok = [False]
                    def ask():
                        ok[0] = messagebox.askyesno(
                            "Confirmar Exclusão Automática",
                            f"Encontrado(s): {summary['total_items']} item(ns) ({summary['total_size']}).\n\n"
                            f"Usuário: {summary['username']}\n\n"
                            "Deseja excluir TODOS?\n\n⚠ Ação permanente!")
                        ev.set()
                    self.after(0, ask); ev.wait(120)
                    if not ok[0]:
                        self._log_all("Exclusão cancelada.")
                        self._update_step(2,"done"); self._update_step(3,"pending")
                        self._set_running(False,"Cancelado"); return

                for it in self._scan_items: it["selected"] = True
                self._log_all(f"══ Automação: Excluindo {len(self._scan_items)} item(ns)…")
                self._update_step(2,"done"); self._update_step(3,"active")
                count = [0]
                def del_cb(msg):
                    self._log_all(msg)
                    if msg.startswith("✔"):
                        count[0] += 1
                        self._set_progress(count[0] / max(len(self._scan_items),1))
                res = file_scanner.delete_items(self._scan_items, del_cb)
                self._update_step(3, "done" if res["failed"]==0 else "error")
                done += 1; self._set_progress(1.0)
                self._log_all(f"Exclusão: {res['deleted']} ok / {res['failed']} falha(s).")
                self._scan_items = []
                self._check_vars = {}
                self.after(0, self._fill_tree)
            elif do_scan:
                self._update_step(2,"done")

            self._set_progress(1.0)
            self._set_running(False, "✔ Automação concluída")
            self._set_status("Automação concluída!")
            self._log_all("══ AUTOMAÇÃO FINALIZADA ══")

        threading.Thread(target=task, daemon=True).start()

    def _reset(self):
        if self._running:
            messagebox.showwarning("Em andamento","Aguarde."); return
        if not messagebox.askyesno("Nova Sessão","Limpar logs e resultados?"): return
        for w in (self._theme_log, self._auto_log, self._progress_log):
            w.config(state="normal"); w.delete("1.0","end"); w.config(state="disabled")
        for r in self._tree.get_children(): self._tree.delete(r)
        for i in range(len(self._steps)): self._update_step(i,"pending")
        self._scan_items=[]; self._check_vars={}
        self._set_progress(0); self._set_status("Pronto.")
        self._scan_sum_lbl.config(text="Nenhuma varredura realizada.")
        self._result_lbl.config(text="Nenhuma operação realizada ainda.")
        self._log_all("Nova sessão iniciada.")

    # ── Ações: Inicialização ──────────────────────────────────────────────────

    def _startup_register(self):
        all_u = self._startup_all_users.get()
        mini  = self._startup_minimized.get()
        if all_u and not messagebox.askyesno(
            "Todos os perfis",
            "Isso registrará o app para iniciar para TODOS os usuários via "
            "Agendador de Tarefas.\nRequer privilégios de Administrador.\n\nContinuar?"
        ): return
        def task():
            startup_register(all_u, mini, lambda m: self._log(self._sched_log, m))
            self.after(0, self._startup_check)
        threading.Thread(target=task, daemon=True).start()

    def _startup_remove(self):
        if not messagebox.askyesno("Remover Inicialização",
                                   "Remover o registro de inicialização automática?"): return
        def task():
            startup_remove(lambda m: self._log(self._sched_log, m))
            self.after(0, self._startup_check)
        threading.Thread(target=task, daemon=True).start()

    def _startup_check(self):
        def task():
            registered = startup_is_registered()
            txt = "✔ Inicialização automática ATIVA." if registered else "✗ Inicialização automática não configurada."
            col = C["success"] if registered else C["text_dim"]
            self.after(0, lambda: self._startup_status_lbl.config(text=txt, fg=col))
        threading.Thread(target=task, daemon=True).start()

    # ── Ações: Agendamento ────────────────────────────────────────────────────

    def _sched_create(self):
        try:
            days   = int(self._sched_days.get())
            hour   = int(self._sched_hour.get())
            minute = int(self._sched_min.get())
        except ValueError:
            messagebox.showerror("Valor inválido","Verifique dias e horário."); return
        if not any(v.get() for v in self._sched_vars.values()):
            messagebox.showwarning("Nada selecionado","Selecione ao menos uma tarefa."); return
        do_del = self._sched_vars["delete"].get()
        if do_del and not messagebox.askyesno(
            "Confirmar exclusão automática",
            "A exclusão agendada removerá arquivos sem confirmação.\nTem certeza?"
        ): return
        def task():
            ok = schedule_create(days, hour, minute,
                                 self._sched_vars["theme"].get(),
                                 self._sched_vars["scan"].get(),
                                 do_del,
                                 lambda m: self._log(self._sched_log, m))
            self.after(0, lambda: self._sched_status_lbl2.config(
                fg=C["success"] if ok else C["danger"],
                text="✔ Agendamento criado!" if ok else "✘ Falha ao criar agendamento."))
        threading.Thread(target=task, daemon=True).start()

    def _sched_delete(self):
        if not messagebox.askyesno("Remover Agendamento",
                                   "Remover a tarefa de limpeza periódica?"): return
        def task():
            schedule_delete(lambda m: self._log(self._sched_log, m))
            self.after(0, lambda: self._sched_status_lbl2.config(
                fg=C["text_dim"], text="Agendamento removido."))
        threading.Thread(target=task, daemon=True).start()

    def _sched_status_check(self):
        def task():
            txt = schedule_status()
            self.after(0, lambda: self._sched_status_lbl2.config(
                fg=C["success"] if "✔" in txt else C["text_dim"], text=txt))
            self._log(self._sched_log, txt.replace("\n"," | "))
        threading.Thread(target=task, daemon=True).start()

    # ── Utilitário ────────────────────────────────────────────────────────────

    def _update_result(self, summary):
        lines = [
            f"Usuário: {summary.get('username','—')}  |  "
            f"Total: {summary['total_items']} itens  |  "
            f"Arquivos: {summary['total_files']}  |  "
            f"Pastas: {summary['total_folders']}  |  "
            f"Tamanho: {summary['total_size']}"
        ]
        for folder, data in summary["by_folder"].items():
            lines.append(f"  • {folder}: {data['count']} item(ns)  "
                         f"({file_scanner._get_size_str(data['size'])})")
        self.after(0, lambda: self._result_lbl.config(text="\n".join(lines)))

    # ── Página: Atualização ───────────────────────────────────────────────────

    def _build_page_update(self):
        p = tk.Frame(self._content, bg=C["bg"])
        self._pages["update"] = p
        _page_title(p, "🔄  Atualização do Programa",
                    "Verifique e instale novas versões automaticamente.")

        # ── Card: versão atual ────────────────────────────────────────────
        vc = _card(p)
        vc.pack(fill="x", padx=20, pady=(0, 8))
        tk.Frame(vc, bg=C["accent"], height=3).pack(fill="x")
        vi = tk.Frame(vc, bg=C["bg_card"])
        vi.pack(fill="x", padx=16, pady=14)

        left_vi = tk.Frame(vi, bg=C["bg_card"])
        left_vi.pack(side="left", fill="x", expand=True)
        tk.Label(left_vi, text="Versão instalada:", bg=C["bg_card"],
                 fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w")
        tk.Label(left_vi, text="v1.5", bg=C["bg_card"],
                 fg=C["accent"], font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(left_vi, text="W.B. SystemCare — Usina da Paz Salinópolis",
                 bg=C["bg_card"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w")

        right_vi = tk.Frame(vi, bg=C["bg_card"])
        right_vi.pack(side="right", padx=8)
        tk.Label(right_vi, text="🔗 Repositório:",
                 bg=C["bg_card"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="e")
        tk.Label(right_vi, text="github.com/romeuwb/wb-systemcare",
                 bg=C["bg_card"], fg=C["blue"], font=FONT_SMALL).pack(anchor="e")

        _hsep(p)

        # ── Card: verificação + auto-update ──────────────────────────────
        uc = _card(p)
        uc.pack(fill="x", padx=20, pady=(0, 8))
        tk.Frame(uc, bg=C["blue"], height=3).pack(fill="x")
        uh = tk.Frame(uc, bg=C["bg_card"])
        uh.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(uh, text="🔄  Atualização Automática via GitHub",
                 bg=C["bg_card"], fg=C["blue_light"],
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(uh,
                 text="Verifica, baixa e instala a nova versão automaticamente — "
                      "substitui o .exe atual e reinicia.",
                 bg=C["bg_card"], fg=C["text_dim"], font=FONT_SMALL).pack(anchor="w")

        # Como funciona
        how = tk.Frame(uc, bg=C["bg_card"])
        how.pack(fill="x", padx=16, pady=(0, 10))
        steps_txt = [
            ("1", "Verificar",  "Consulta o GitHub para ver se há versão nova"),
            ("2", "Baixar",     "Faz download do novo .exe em segundo plano"),
            ("3", "Substituir", "Fecha, substitui o arquivo atual e reinicia"),
        ]
        for num, title, desc in steps_txt:
            sr = tk.Frame(how, bg=C["bg_card"])
            sr.pack(anchor="w", pady=2)
            tk.Label(sr, text=f" {num} ", bg=C["accent"], fg="#0d0b09",
                     font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0,8))
            tk.Label(sr, text=f"{title}: ", bg=C["bg_card"], fg=C["text"],
                     font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Label(sr, text=desc, bg=C["bg_card"], fg=C["text_dim"],
                     font=FONT_SMALL).pack(side="left")

        bf = tk.Frame(uc, bg=C["bg_card"])
        bf.pack(padx=16, pady=(0, 14), anchor="w")
        _btn(bf, "🔍  Verificar Agora",
             self._update_check,    width=18).pack(side="left", padx=(0, 8))
        _btn(bf, "⬇  Baixar e Instalar",
             self._update_download, width=20).pack(side="left", padx=(0, 8))
        _btn(bf, "🌐  Ver Releases",
             self._update_open_web, width=16).pack(side="left")

        # Status
        self._update_status_lbl = tk.Label(
            p, text="Clique em 'Verificar Agora' para checar atualizações.",
            bg=C["bg_card"], fg=C["text_dim"], font=FONT_BODY,
            justify="left", anchor="w", padx=16, pady=8, wraplength=700
        )
        self._update_status_lbl.pack(fill="x", padx=20, pady=(0, 4))

        _hsep(p)
        tk.Label(p, text="Log:", bg=C["bg"], fg=C["text_dim"],
                 font=FONT_SMALL).pack(anchor="w", padx=20)
        self._update_log = _log_box(p, 8)

        # Informações de download
        self._update_download_url = ""
        self._update_latest_ver   = ""

    # ── Ações: Atualização ────────────────────────────────────────────────────

    def _update_check(self):
        self._log(self._update_log, "Verificando atualizações em github.com/romeuwb/wb-systemcare...")
        self.after(0, lambda: self._update_status_lbl.config(
            text="⏳  Verificando...", fg=C["info"]))
        API_LATEST = "https://api.github.com/repos/romeuwb/wb-systemcare/releases/latest"
        API_LIST   = "https://api.github.com/repos/romeuwb/wb-systemcare/releases"
        REPO_PAGE  = "https://github.com/romeuwb/wb-systemcare/releases"
        CURRENT    = "1.5"

        def task():
            try:
                import urllib.request
                import urllib.error
                import json as _json

                headers = {
                    "User-Agent":  "WB-SystemCare/1.5",
                    "Accept":      "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }

                data     = None
                latest   = ""
                exe_url  = ""
                notes    = ""

                # Tenta /releases/latest primeiro
                try:
                    req = urllib.request.Request(API_LATEST, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        data = _json.loads(resp.read().decode())
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        # Sem releases ainda — tenta a lista
                        try:
                            req2 = urllib.request.Request(API_LIST, headers=headers)
                            with urllib.request.urlopen(req2, timeout=10) as resp2:
                                releases = _json.loads(resp2.read().decode())
                                if releases:
                                    data = releases[0]  # mais recente
                        except Exception:
                            pass
                    else:
                        raise

                if data:
                    latest  = data.get("tag_name", "").lstrip("vV")
                    notes   = (data.get("body", "") or "")[:400]
                    assets  = data.get("assets", [])
                    for a in assets:
                        name = a.get("name", "")
                        if name.endswith(".exe") and "WB_SystemCare" in name:
                            exe_url = a.get("browser_download_url", "")
                            break
                    if not exe_url and assets:
                        exe_url = assets[0].get("browser_download_url", "")
                    if not exe_url:
                        exe_url = data.get("html_url", REPO_PAGE)

                self._update_download_url = exe_url
                self._update_latest_ver   = latest

                def _show():
                    if not data:
                        msg = ("⚠  Nenhuma release publicada ainda no repositório.\n\n"
                               "Para ativar as atualizações:\n"
                               "1. Compile o WB_SystemCare.exe\n"
                               "2. Vá em github.com/romeuwb/wb-systemcare\n"
                               "3. Clique em 'Releases' → 'Create a new release'\n"
                               "4. Tag: v1.5  •  Anexe o WB_SystemCare.exe")
                        self._update_status_lbl.config(text=msg, fg=C["warning"])
                        self._log(self._update_log,
                                  "⚠ Repositório existe mas sem releases. "
                                  "Publique a v1.5 em github.com/romeuwb/wb-systemcare/releases/new")
                        return

                    if latest and latest != CURRENT:
                        msg = (f"🆕  Nova versão disponível: v{latest}  "
                               f"(você tem: v{CURRENT})\n"
                               f"Clique em '⬇ Baixar Nova Versão' para atualizar.")
                        col = C["accent"]
                    elif latest == CURRENT:
                        msg = f"✔  Você já tem a versão mais recente (v{CURRENT})."
                        col = C["success"]
                    else:
                        msg = f"✔  Conectado ao repositório. Versão encontrada: v{latest or '?'}"
                        col = C["info"]

                    self._update_status_lbl.config(text=msg, fg=col)
                    if notes:
                        self._log(self._update_log, f"📋 Novidades v{latest}:\n{notes}")
                    self._log(self._update_log,
                              f"✔ Verificação OK. "
                              f"Repo: github.com/romeuwb/wb-systemcare  "
                              f"| Última versão: {latest or '—'}")

                self.after(0, _show)

            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._update_status_lbl.config(
                    text=f"✘  Erro ao verificar: {err}\n\nVerifique sua conexão com a internet.",
                    fg=C["danger"]))
                self._log(self._update_log, f"✘ Erro: {err}")

        threading.Thread(target=task, daemon=True).start()

    def _update_download(self):
        """
        Self-update automático:
        1. Baixa o novo .exe para um arquivo temporário
        2. Cria um script .bat que:
           a. Aguarda o processo atual fechar
           b. Substitui o .exe atual pelo novo
           c. Inicia a nova versão
           d. Apaga o script
        3. Pergunta ao usuário se quer atualizar agora
        4. Se sim, inicia o script e fecha o app
        """
        if not self._update_download_url:
            messagebox.showinfo("Verificar primeiro",
                                "Clique em 'Verificar Agora' antes de baixar."); return

        if not messagebox.askyesno(
            "Atualizar Automaticamente",
            f"Baixar e instalar a versão v{self._update_latest_ver or '?'} automaticamente?\n\n"
            "O programa atual será substituído e reiniciará automaticamente.\n\n"
            "Clique SIM para atualizar agora."
        ): return

        self.after(0, lambda: self._update_status_lbl.config(
            text="⬇  Baixando nova versão...", fg=C["info"]))
        self._log(self._update_log, f"Iniciando download de: {self._update_download_url}")

        def task():
            try:
                import urllib.request
                import tempfile

                # Caminho do executável atual
                current_exe = sys.executable if getattr(sys, "frozen", False) \
                    else os.path.abspath(__file__)
                current_dir = os.path.dirname(current_exe)
                current_pid = os.getpid()

                # Arquivo temporário para o novo exe
                tmp_fd, tmp_path = tempfile.mkstemp(suffix=".exe",
                                                    prefix="WB_update_",
                                                    dir=current_dir)
                os.close(tmp_fd)

                # Download com progresso
                downloaded = [0]
                def _progress(block, block_size, total):
                    downloaded[0] += block_size
                    if total > 0:
                        pct = min(int(downloaded[0] * 100 / total), 100)
                        self.after(0, lambda p=pct: self._update_status_lbl.config(
                            text=f"⬇  Baixando... {p}%", fg=C["info"]))

                urllib.request.urlretrieve(
                    self._update_download_url, tmp_path, _progress)

                self._log(self._update_log, f"✔ Download concluído: {tmp_path}")

                # Cria script .bat de substituição automática
                bat_path = os.path.join(current_dir, "_wb_update.bat")
                bat_content = f"""@echo off
:: WB SystemCare — Self-updater
title Atualizando WB SystemCare...
echo Aguardando o programa fechar...
:wait
tasklist /FI "PID eq {current_pid}" 2>nul | find /I "{current_pid}" >nul
if not errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait
)
echo Instalando nova versao...
move /Y "{tmp_path}" "{current_exe}" >nul 2>&1
if errorlevel 1 (
    echo Falha ao substituir. Tentando com xcopy...
    xcopy /Y /Q "{tmp_path}" "{current_exe}" >nul 2>&1
)
echo Iniciando nova versao...
start "" "{current_exe}"
del "%~f0"
"""
                with open(bat_path, "w", encoding="ascii") as f:
                    f.write(bat_content)

                # Pergunta se quer reiniciar agora
                def _ask_restart():
                    if messagebox.askyesno(
                        "✔ Download Concluído — Reiniciar?",
                        f"v{self._update_latest_ver} baixada com sucesso!\n\n"
                        "O programa será fechado, a nova versão instalada\n"
                        "e reiniciado automaticamente.\n\n"
                        "Deseja reiniciar agora?"
                    ):
                        self._update_status_lbl.config(
                            text="🔄  Reiniciando com nova versão...", fg=C["success"])
                        self._log(self._update_log, "Iniciando atualização e reiniciando...")
                        # Inicia o bat em background e fecha o app
                        import subprocess
                        si = subprocess.STARTUPINFO()
                        si.dwFlags = subprocess.STARTF_USESHOWWINDOW
                        si.wShowWindow = 1  # SW_NORMAL — mostra o bat brevemente
                        subprocess.Popen(
                            ["cmd.exe", "/c", bat_path],
                            creationflags=0x00000008,  # DETACHED_PROCESS
                            startupinfo=si
                        )
                        self.after(500, self._quit_app)
                    else:
                        self._update_status_lbl.config(
                            text=f"✔  v{self._update_latest_ver} baixada. "
                                 f"Reinicie manualmente quando quiser.",
                            fg=C["success"])
                        self._log(self._update_log,
                                  f"Nova versão pronta em: {tmp_path}\n"
                                  f"Feche e execute para atualizar.")

                self.after(0, _ask_restart)

            except Exception as e:
                err = str(e)
                self.after(0, lambda: self._update_status_lbl.config(
                    text=f"✘  Falha no download: {err}", fg=C["danger"]))
                self._log(self._update_log, f"✘ Erro: {err}")

        threading.Thread(target=task, daemon=True).start()

    def _update_open_web(self):
        """Abre a página de releases do repositório no browser."""
        import webbrowser
        webbrowser.open("https://github.com/romeuwb/wb-systemcare/releases")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if sys.platform != "win32":
        print("W.B. SystemCare funciona apenas no Windows.")
        input("Pressione Enter para sair...")
        sys.exit(1)

    args = sys.argv[1:]

    # Modo headless — chamado pelo agendador
    if any(a.startswith("--auto-") for a in args):
        run_headless()
        return

    # Se foi relançado com --elevated, recupera as credenciais do arquivo temporário
    elevated_user = ""
    elevated_pass = ""
    if "--elevated" in args:
        from credential_helper import read_elevated_creds
        elevated_user, elevated_pass = read_elevated_creds()

    start_minimized = "--minimized" in args
    app = WBSystemCare(start_minimized=start_minimized)

    # Injeta credenciais no cache se veio de relançamento elevado
    if elevated_user and elevated_pass:
        app._cred_cache.set(elevated_user, elevated_pass)
        app.after(200, lambda: app._cred_status_lbl.config(
            text=f"✔  Rodando como Administrador ({elevated_user}) — privilégios elevados ativos.",
            fg=C["success"]
        ))

    app.mainloop()


if __name__ == "__main__":
    main()
