# -*- coding: utf-8 -*-
"""
credential_helper.py — Credenciais administrativas para WB SystemCare.
Versão 1.4

Mudanças:
  - Todos os subprocess usam CREATE_NO_WINDOW — nenhuma janela preta aparece
  - relaunch_as_admin(): relança o exe atual com ShellExecuteW "runas"
    e passa --admin-user / --admin-pass como argumentos para o novo processo
    recuperar o token elevado.
  - validate_credentials() via LogonUserW (sem processo externo)
"""

import ctypes
import ctypes.wintypes as wt
import subprocess
import logging
import os
import sys
import threading
import tempfile

logger = logging.getLogger(__name__)

# ── Win32 ─────────────────────────────────────────────────────────────────────
LOGON32_LOGON_NETWORK    = 3
LOGON32_PROVIDER_DEFAULT = 0
CREATE_NO_WINDOW         = 0x08000000
SW_HIDE                  = 0

advapi32 = ctypes.windll.advapi32
shell32  = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32


# ── STARTUPINFO para suprimir janelas ─────────────────────────────────────────
def _no_window_si():
    """Retorna STARTUPINFO que oculta a janela do processo filho."""
    si = subprocess.STARTUPINFO()
    si.dwFlags    = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0   # SW_HIDE
    return si


# ── Helpers de execução silenciosa ────────────────────────────────────────────

def _run_silent(cmd: str, encoding: str = "cp850") -> tuple:
    """Roda comando shell SEM abrir janela preta."""
    try:
        r = subprocess.run(
            cmd, shell=True,
            capture_output=True, text=True,
            encoding=encoding, errors="replace",
            creationflags=CREATE_NO_WINDOW,
            startupinfo=_no_window_si()
        )
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)


def _run_ps_silent(script: str, timeout: int = 30) -> tuple:
    """Roda PowerShell SEM abrir janela preta."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass",
             "-Command", script],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW,
            startupinfo=_no_window_si(),
            timeout=timeout
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout."
    except Exception as e:
        return -1, "", str(e)


# ── Validação de credenciais (sem processo externo) ───────────────────────────

def validate_credentials(username: str, password: str,
                         domain: str = ".") -> tuple:
    """Valida credenciais via LogonUserW — sem abrir janela."""
    if not username or password is None:
        return False, "Usuário e senha são obrigatórios."
    h_token = wt.HANDLE()
    ok = advapi32.LogonUserW(
        username, domain, password,
        LOGON32_LOGON_NETWORK, LOGON32_PROVIDER_DEFAULT,
        ctypes.byref(h_token)
    )
    if ok:
        kernel32.CloseHandle(h_token)
        return True, ""
    err = ctypes.GetLastError()
    msgs = {
        1326: "Usuário ou senha incorretos.",
        1330: "A senha expirou.",
        1331: "Conta desativada.",
        1907: "A senha precisa ser trocada no próximo login.",
    }
    return False, msgs.get(err, f"Erro de autenticação (código {err}).")


# ── Relançamento como administrador ──────────────────────────────────────────

def relaunch_as_admin(username: str, password: str) -> bool:
    """
    Relança o processo atual com as credenciais do administrador informado.

    Usa CreateProcessWithLogonW (Win32) que aceita user+senha diretamente,
    sem depender do UAC do usuário atual — funciona mesmo com usuário comum.

    O novo processo recebe --elevated e --cred-file para recuperar as
    credenciais e saber que está rodando elevado.
    """
    try:
        import tempfile

        exe       = sys.executable
        args_list = list(sys.argv)

        # Grava credenciais em arquivo temporário para o novo processo ler
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".wbsc", delete=False,
            encoding="utf-8", prefix="wbsc_"
        )
        tmp.write(f"{username}\n{password}\n")
        tmp_path = tmp.name
        tmp.close()

        extra = ["--elevated", f"--cred-file={tmp_path}"]
        clean_args = [a for a in args_list[1:]
                      if not a.startswith("--elevated")
                      and not a.startswith("--cred-file")]
        all_args = clean_args + extra

        if getattr(sys, "frozen", False):
            # .exe compilado
            cmd_line = exe + " " + " ".join(f'"{a}"' for a in all_args)
            app_name = exe
        else:
            # .py em desenvolvimento
            script = os.path.abspath(args_list[0])
            cmd_line = f'"{exe}" "{script}" ' + " ".join(f'"{a}"' for a in all_args)
            app_name = exe

        # Tenta CreateProcessWithLogonW (não precisa de UAC)
        try:
            ok = _launch_with_logon(username, password, app_name, cmd_line)
            if ok:
                return True
        except Exception as e:
            logger.warning(f"CreateProcessWithLogonW falhou: {e}")

        # Fallback: ShellExecuteW runas (pede UAC — funciona se usuário tem conta admin)
        try:
            params = " ".join(f'"{a}"' for a in all_args)
            if not getattr(sys, "frozen", False):
                script = os.path.abspath(args_list[0])
                params = f'"{script}" ' + params
            ret = shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
            if int(ret) > 32:  # >32 = sucesso
                return True
        except Exception as e:
            logger.warning(f"ShellExecuteW runas falhou: {e}")

        return False
    except Exception as e:
        logger.error(f"relaunch_as_admin: {e}")
        return False


def _launch_with_logon(username: str, password: str,
                        app_name: str, cmd_line: str) -> bool:
    """
    Lança processo com as credenciais fornecidas via CreateProcessWithLogonW.
    Não precisa de UAC — usa o token do admin diretamente.
    LOGON_WITH_PROFILE (1) carrega o perfil do admin.
    """
    import ctypes
    import ctypes.wintypes as wt

    # Estruturas necessárias
    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [
            ("cb",              wt.DWORD),
            ("lpReserved",      wt.LPWSTR),
            ("lpDesktop",       wt.LPWSTR),
            ("lpTitle",         wt.LPWSTR),
            ("dwX",             wt.DWORD),
            ("dwY",             wt.DWORD),
            ("dwXSize",         wt.DWORD),
            ("dwYSize",         wt.DWORD),
            ("dwXCountChars",   wt.DWORD),
            ("dwYCountChars",   wt.DWORD),
            ("dwFillAttribute", wt.DWORD),
            ("dwFlags",         wt.DWORD),
            ("wShowWindow",     wt.WORD),
            ("cbReserved2",     wt.WORD),
            ("lpReserved2",     ctypes.c_char_p),
            ("hStdInput",       wt.HANDLE),
            ("hStdOutput",      wt.HANDLE),
            ("hStdError",       wt.HANDLE),
        ]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess",    wt.HANDLE),
            ("hThread",     wt.HANDLE),
            ("dwProcessId", wt.DWORD),
            ("dwThreadId",  wt.DWORD),
        ]

    LOGON_WITH_PROFILE = 1
    CREATE_NO_WINDOW   = 0x08000000
    NORMAL_PRIORITY    = 0x00000020

    si = STARTUPINFOW()
    si.cb        = ctypes.sizeof(STARTUPINFOW)
    si.dwFlags   = 0x0001   # STARTF_USESHOWWINDOW
    si.wShowWindow = 1      # SW_SHOWNORMAL

    pi = PROCESS_INFORMATION()

    # Extrai domínio e usuario
    if "\\" in username:
        domain, uname = username.split("\\", 1)
    else:
        domain, uname = ".", username

    # cmd_line precisa ser mutável (buffer)
    cmd_buf = ctypes.create_unicode_buffer(cmd_line)

    ok = ctypes.windll.advapi32.CreateProcessWithLogonW(
        uname,          # lpUsername
        domain,         # lpDomain ("." = máquina local)
        password,       # lpPassword
        LOGON_WITH_PROFILE,  # dwLogonFlags
        None,           # lpApplicationName (None = usa cmd_line)
        cmd_buf,        # lpCommandLine
        CREATE_NO_WINDOW | NORMAL_PRIORITY,  # dwCreationFlags
        None,           # lpEnvironment
        None,           # lpCurrentDirectory
        ctypes.byref(si),
        ctypes.byref(pi),
    )

    if ok:
        # Fecha handles do processo filho
        ctypes.windll.kernel32.CloseHandle(pi.hProcess)
        ctypes.windll.kernel32.CloseHandle(pi.hThread)
        return True
    else:
        err = ctypes.GetLastError()
        raise RuntimeError(f"CreateProcessWithLogonW falhou: erro {err}")



def read_elevated_creds() -> tuple:
    """
    Lê as credenciais passadas pelo processo pai via arquivo temporário.
    Retorna (username, password) ou ("", "").
    Deleta o arquivo após ler.
    """
    for arg in sys.argv[1:]:
        if arg.startswith("--cred-file="):
            path = arg.split("=", 1)[1]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.read().splitlines()
                os.remove(path)
                if len(lines) >= 2:
                    return lines[0].strip(), lines[1].strip()
            except Exception as e:
                logger.warning(f"read_elevated_creds: {e}")
    return "", ""


def is_elevated() -> bool:
    """Retorna True se o processo atual tem privilégios de Administrador."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ── Execução privilegiada de comandos ─────────────────────────────────────────

def run_ps_as_admin(ps_command: str, username: str, password: str,
                    domain: str = ".", timeout: int = 30) -> tuple:
    """PowerShell silencioso com credenciais admin via Invoke-Command localhost."""
    full = f"{domain}\\{username}" if domain and domain != "." else username
    safe_p = password.replace('"', '`"')
    script = (
        f'$pw = ConvertTo-SecureString "{safe_p}" -AsPlainText -Force; '
        f'$cr = New-Object System.Management.Automation.PSCredential ("{full}", $pw); '
        f'Invoke-Command -ComputerName localhost -Credential $cr '
        f'-ScriptBlock {{ {ps_command} }} -ErrorAction Stop'
    )
    return _run_ps_silent(script, timeout)


def run_net_as_admin(net_args: str, username: str, password: str,
                     domain: str = ".", timeout: int = 30) -> tuple:
    """net <args> silencioso com credenciais admin."""
    full   = f"{domain}\\{username}" if domain and domain != "." else username
    safe_p = password.replace('"', '`"')
    script = (
        f'$pw = ConvertTo-SecureString "{safe_p}" -AsPlainText -Force; '
        f'$cr = New-Object System.Management.Automation.PSCredential ("{full}", $pw); '
        f'$sb = [scriptblock]::Create("net {net_args}"); '
        f'Invoke-Command -ComputerName localhost -Credential $cr '
        f'-ScriptBlock $sb -ErrorAction Stop'
    )
    return _run_ps_silent(script, timeout)


# ── Cache de credenciais da sessão ────────────────────────────────────────────

class CredentialCache:
    def __init__(self):
        self._lock     = threading.Lock()
        self._username = None
        self._password = None
        self._domain   = "."
        self._valid    = False

    def set(self, username: str, password: str, domain: str = "."):
        with self._lock:
            self._username = username
            self._password = password
            self._domain   = domain
            self._valid    = True

    def clear(self):
        with self._lock:
            self._username = None
            self._password = None
            self._domain   = "."
            self._valid    = False

    @property
    def has_credentials(self) -> bool:
        with self._lock:
            return self._valid and bool(self._username)

    @property
    def username(self) -> str:
        with self._lock:
            return self._username or ""

    @property
    def domain(self) -> str:
        with self._lock:
            return self._domain or "."

    def get_password(self) -> str:
        with self._lock:
            return self._password or ""

    def run_net(self, net_args: str, timeout: int = 30) -> tuple:
        with self._lock:
            u, p, d = self._username, self._password, self._domain
        return run_net_as_admin(net_args, u, p, d, timeout)

    def run_ps(self, ps_cmd: str, timeout: int = 30) -> tuple:
        with self._lock:
            u, p, d = self._username, self._password, self._domain
        return run_ps_as_admin(ps_cmd, u, p, d, timeout)


cred_cache = CredentialCache()
