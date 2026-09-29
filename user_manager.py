# -*- coding: utf-8 -*-
"""
user_manager.py — Gerenciamento de usuários locais do Windows.

Todas as funções aceitam um parâmetro opcional `creds` (CredentialCache).
Se fornecido e o processo atual não for admin, as operações rodam com as
credenciais do admin informado via Invoke-Command localhost.

Sem dependências externas.
"""

import subprocess
import logging
import re
import os
import json
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Execução de comandos ──────────────────────────────────────────────────────

def _run(cmd: str, encoding: str = "cp850") -> tuple:
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags    = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, encoding=encoding, errors="replace",
                           creationflags=0x08000000,   # CREATE_NO_WINDOW
                           startupinfo=si)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)


def _run_ps(script: str) -> tuple:
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags    = subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=0x08000000,
            startupinfo=si
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def _run_ps_as(script: str, creds) -> tuple:
    from credential_helper import run_ps_as_admin
    return run_ps_as_admin(script, creds.username, creds.get_password(), creds.domain)


def _run_net_as(net_args: str, creds) -> tuple:
    from credential_helper import run_net_as_admin
    return run_net_as_admin(net_args, creds.username, creds.get_password(), creds.domain)

    script = (
        f'$pw = ConvertTo-SecureString "{p}" -AsPlainText -Force; '
        f'$cr = New-Object System.Management.Automation.PSCredential ("{full}", $pw); '
        f'$sb = [scriptblock]::Create("net {net_args}"); '
        f'Invoke-Command -ComputerName localhost -Credential $cr '
        f'-ScriptBlock $sb -ErrorAction Stop'
    )
    return _run_ps(script)


# ── Listar usuários ───────────────────────────────────────────────────────────

_PS_LIST = r"""
Get-LocalUser | ForEach-Object {
    $u = $_
    $g = (Get-LocalGroup | Where-Object {
        try { (Get-LocalGroupMember $_ -EA SilentlyContinue |
               Where-Object Name -like "*\$($u.Name)") } catch { $false }
    } | Select-Object -ExpandProperty Name) -join ', '
    [PSCustomObject]@{
        Name            = $u.Name
        FullName        = $u.FullName
        Enabled         = $u.Enabled
        LastLogon       = if($u.LastLogon){$u.LastLogon.ToString('dd/MM/yyyy HH:mm')}else{'Nunca'}
        PasswordExpires = if($u.PasswordExpires){$u.PasswordExpires.ToString('dd/MM/yyyy')}else{'Nunca expira'}
        PasswordRequired = $u.PasswordRequired
        UserMayChangePassword = $u.UserMayChangePassword
        Description     = $u.Description
        Groups          = if($g){$g}else{'—'}
        SID             = $u.SID.Value
    }
} | ConvertTo-Json -Depth 2
"""


def list_users(creds=None) -> list:
    """Lista usuários locais. Aceita credenciais opcionais de admin."""
    if creds and creds.has_credentials:
        rc, out, err = _run_ps_as(_PS_LIST, creds)
    else:
        rc, out, err = _run_ps(_PS_LIST)

    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            return [_parse_user(u) for u in data]
        except Exception as e:
            logger.warning(f"JSON parse: {e}")

    return _list_users_fallback()


def _parse_user(u: dict) -> dict:
    return {
        "name":              str(u.get("Name", "")),
        "full_name":         str(u.get("FullName", "") or ""),
        "enabled":           bool(u.get("Enabled", True)),
        "status":            "Ativa" if u.get("Enabled") else "Desativada",
        "last_logon":        str(u.get("LastLogon", "Nunca")),
        "password_expires":  str(u.get("PasswordExpires", "—")),
        "password_required": bool(u.get("PasswordRequired", True)),
        "user_may_change_pwd": bool(u.get("UserMayChangePassword", True)),
        "description":       str(u.get("Description", "") or ""),
        "groups":            str(u.get("Groups", "—")),
        "sid":               str(u.get("SID", "")),
    }


def _list_users_fallback() -> list:
    users = []
    rc, out, _ = _run("net user")
    if rc != 0:
        return users
    capture = False
    names   = []
    for line in out.splitlines():
        if "---" in line:
            capture = not capture
            continue
        if capture and line.strip():
            names.extend(line.split())
    for name in names:
        if name and not name.startswith("\\"):
            users.append({
                "name": name, "full_name": "", "enabled": True,
                "status": "Ativa", "last_logon": "—",
                "password_expires": "—", "password_required": True,
                "user_may_change_pwd": True, "description": "",
                "groups": "—", "sid": "",
            })
    return users


def get_admin_users() -> list:
    """Retorna lista de usuários que são membros do grupo Administradores."""
    ps = r"""
$admins = @()
$groups = @('Administrators','Administradores')
foreach ($g in $groups) {
    try {
        $members = Get-LocalGroupMember -Group $g -ErrorAction Stop
        $admins += $members | Where-Object ObjectClass -eq 'User' |
                   ForEach-Object { ($_.Name -split '\\')[-1] }
    } catch {}
}
$admins | Sort-Object -Unique | ConvertTo-Json
"""
    rc, out, _ = _run_ps(ps)
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            if isinstance(data, str): data = [data]
            return [str(x) for x in data]
        except Exception:
            pass
    # Fallback: net localgroup
    rc2, out2, _ = _run("net localgroup Administradores")
    if rc2 != 0:
        rc2, out2, _ = _run("net localgroup Administrators")
    admins = []
    capture = False
    for line in out2.splitlines():
        if "---" in line: capture = True; continue
        if capture and line.strip() and "O comando foi" not in line:
            admins.append(line.strip())
    return admins


# ── Alterar senha ─────────────────────────────────────────────────────────────

def change_password(username: str, new_password: str,
                    callback=None, creds=None) -> bool:
    if not username or not new_password:
        if callback: callback("✘ Usuário e senha são obrigatórios.")
        return False
    if callback: callback(f"Alterando senha de '{username}'...")

    net_args = f'user "{username}" "{new_password}"'

    if creds and creds.has_credentials:
        rc, out, err = _run_net_as(net_args, creds)
    else:
        rc, out, err = _run(f"net {net_args}")

    ok = rc == 0
    if ok:
        if callback: callback(f"✔ Senha de '{username}' alterada.")
    else:
        msg = (err or out).strip()
        if callback: callback(f"✘ Erro: {msg}")
    return ok


# ── Expiração de senha ────────────────────────────────────────────────────────

def set_password_never_expires(username: str, never: bool,
                                callback=None, creds=None) -> bool:
    label = "nunca expira" if never else "expira conforme política"
    if callback: callback(f"Configurando senha de '{username}': {label}...")

    ps = f'Set-LocalUser -Name "{username}" -PasswordNeverExpires ${str(never).lower()}'

    rc, _, err = (_run_ps_as(ps, creds) if creds and creds.has_credentials
                  else _run_ps(ps))

    if rc == 0:
        if callback: callback(f"✔ Senha de '{username}': {label}.")
        return True

    # Fallback wmic
    wmic_val = "FALSE" if never else "TRUE"
    rc2, _, _ = _run(
        f'wmic useraccount where name="{username}" set PasswordExpires={wmic_val}'
    )
    if rc2 == 0:
        if callback: callback(f"✔ Senha de '{username}': {label} (wmic).")
        return True

    if callback: callback(f"✘ Erro: {(err or '').strip()}")
    return False


def force_password_change_on_next_logon(username: str,
                                         callback=None, creds=None) -> bool:
    if callback: callback(f"Forçando troca de senha no próximo login: '{username}'...")

    net_args = f'user "{username}" /logonpasswordchg:yes'
    if creds and creds.has_credentials:
        rc, _, err = _run_net_as(net_args, creds)
    else:
        rc, _, err = _run(f"net {net_args}")

    if rc == 0:
        if callback: callback(f"✔ '{username}' trocará senha no próximo login.")
        return True

    # Fallback ADSI
    ps = (f'$u=[adsi]"WinNT://./{username},user"; '
          f'$u.PasswordExpired=1; $u.SetInfo()')
    rc2, _, err2 = (_run_ps_as(ps, creds) if creds and creds.has_credentials
                    else _run_ps(ps))
    if rc2 == 0:
        if callback: callback(f"✔ '{username}' trocará senha no próximo login (ADSI).")
        return True

    if callback: callback(f"✘ Erro: {(err or err2 or '').strip()}")
    return False


# ── Ativar / Desativar ────────────────────────────────────────────────────────

def set_account_enabled(username: str, enabled: bool,
                         callback=None, creds=None) -> bool:
    action = "Ativando" if enabled else "Desativando"
    if callback: callback(f"{action} conta '{username}'...")

    flag     = "/active:yes" if enabled else "/active:no"
    net_args = f'user "{username}" {flag}'

    if creds and creds.has_credentials:
        rc, _, err = _run_net_as(net_args, creds)
    else:
        rc, _, err = _run(f"net {net_args}")

    if rc == 0:
        verb = "ativada" if enabled else "desativada"
        if callback: callback(f"✔ Conta '{username}' {verb}.")
        return True

    ps_action = "Enable" if enabled else "Disable"
    ps = f'{ps_action}-LocalUser -Name "{username}"'
    rc2, _, err2 = (_run_ps_as(ps, creds) if creds and creds.has_credentials
                    else _run_ps(ps))
    if rc2 == 0:
        verb = "ativada" if enabled else "desativada"
        if callback: callback(f"✔ Conta '{username}' {verb} (PS).")
        return True

    if callback: callback(f"✘ Erro: {(err or err2 or '').strip()}")
    return False


# ── Utilitários ───────────────────────────────────────────────────────────────

def get_current_user() -> str:
    return os.environ.get("USERNAME", "")


def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ── Alterar nome completo ──────────────────────────────────────────────────────

def change_full_name(username: str, full_name: str,
                     callback=None, creds=None) -> bool:
    """Altera o nome completo (display name) de um usuário local."""
    if not username:
        if callback: callback("✘ Nome de usuário obrigatório.")
        return False
    if callback: callback(f"Alterando nome completo de '{username}'...")

    # Tenta via PowerShell Set-LocalUser (mais confiável)
    safe_name = full_name.replace('"', "'")
    ps = f'Set-LocalUser -Name "{username}" -FullName "{safe_name}"'

    if creds and creds.has_credentials:
        rc, _, err = _run_ps_as(ps, creds)
    else:
        rc, _, err = _run_ps(ps)

    if rc == 0:
        if callback: callback(f"✔ Nome completo de '{username}' atualizado para '{full_name}'.")
        return True

    # Fallback via ADSI (WinNT provider)
    adsi_ps = (
        f'$u = [adsi]"WinNT://./{username},user"; '
        f'$u.FullName = "{safe_name}"; '
        f'$u.SetInfo()'
    )
    rc2, _, err2 = _run_ps(adsi_ps)
    if rc2 == 0:
        if callback: callback(f"✔ Nome completo atualizado (ADSI).")
        return True

    if callback: callback(f"✘ Erro: {(err or err2 or '').strip()}")
    return False


def change_password_direct(username: str, new_password: str,
                           callback=None) -> bool:
    """
    Altera senha usando 'net user' DIRETAMENTE (processo atual já é admin).
    Mais confiável que via Invoke-Command quando o processo é elevado.
    """
    if not username or not new_password:
        if callback: callback("✘ Usuário e senha obrigatórios.")
        return False
    if callback: callback(f"Alterando senha de '{username}' (direto)...")

    rc, out, err = _run(f'net user "{username}" "{new_password}"')
    ok = rc == 0
    if ok:
        if callback: callback(f"✔ Senha de '{username}' alterada com sucesso.")
    else:
        msg = (err or out).strip()
        if callback: callback(f"✘ Erro: {msg}")
    return ok
