# -*- coding: utf-8 -*-
"""
user_manager.py - Gerenciamento de usuarios locais do Windows.
Versao 1.6.2 - Sem WinRM, tudo via net user / Set-LocalUser / ADSI local.
"""

import subprocess
import logging
import os
import json

logger = logging.getLogger(__name__)

# ── Helpers de execucao silenciosa ────────────────────────────────────────────

def _no_win_si():
    si = subprocess.STARTUPINFO()
    si.dwFlags     = subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0
    return si

def _run(cmd: str) -> tuple:
    """Roda comando shell silenciosamente (sem janela preta)."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, encoding="cp850", errors="replace",
            creationflags=0x08000000,
            startupinfo=_no_win_si()
        )
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return -1, "", str(e)

def _run_ps(script: str, timeout: int = 30) -> tuple:
    """Roda PowerShell localmente sem WinRM."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
             "-Command", script],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            creationflags=0x08000000,
            startupinfo=_no_win_si(),
            timeout=timeout
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


# ── Listar usuarios ───────────────────────────────────────────────────────────

def list_users(creds=None) -> list:
    """Lista usuarios locais via Get-LocalUser (fallback: net user)."""
    ps = r"""
try {
    Get-LocalUser | ForEach-Object {
        $u = $_
        $g = @()
        Get-LocalGroup | ForEach-Object {
            try {
                if (Get-LocalGroupMember $_ -ErrorAction SilentlyContinue |
                    Where-Object { ($_.Name -split '\\')[-1] -eq $u.Name }) {
                    $g += $_.Name
                }
            } catch {}
        }
        [PSCustomObject]@{
            Name            = $u.Name
            FullName        = $u.FullName
            Enabled         = $u.Enabled
            LastLogon       = if($u.LastLogon){ $u.LastLogon.ToString('dd/MM/yyyy HH:mm') } else { 'Nunca' }
            PasswordExpires = if($u.PasswordExpires){ $u.PasswordExpires.ToString('dd/MM/yyyy') } else { 'Nunca expira' }
            Groups          = ($g -join ', ')
            SID             = $u.SID.Value
        }
    } | ConvertTo-Json -Depth 2
} catch {
    Write-Error $_.Exception.Message
}
"""
    rc, out, err = _run_ps(ps, timeout=20)
    if rc == 0 and out.strip():
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            return [_parse_user(u) for u in data if u.get("Name")]
        except Exception as e:
            logger.warning(f"list_users JSON: {e} | err: {err}")

    return _list_users_fallback()

def _parse_user(u: dict) -> dict:
    return {
        "name":             str(u.get("Name", "")),
        "full_name":        str(u.get("FullName", "") or ""),
        "enabled":          bool(u.get("Enabled", True)),
        "status":           "Ativa" if u.get("Enabled") else "Desativada",
        "last_logon":       str(u.get("LastLogon", "Nunca")),
        "password_expires": str(u.get("PasswordExpires", "—")),
        "description":      str(u.get("Description", "") or ""),
        "groups":           str(u.get("Groups", "—")),
        "sid":              str(u.get("SID", "")),
    }

def _list_users_fallback() -> list:
    """Fallback via net user quando Get-LocalUser falha."""
    rc, out, _ = _run("net user")
    if rc != 0:
        return []
    names, capture = [], False
    for line in out.splitlines():
        if "---" in line:
            capture = not capture
            continue
        if capture and line.strip():
            names.extend(line.split())
    return [{"name": n, "full_name": "", "enabled": True, "status": "Ativa",
             "last_logon": "—", "password_expires": "—",
             "description": "", "groups": "—", "sid": ""}
            for n in names if n and "\\" not in n]


def get_admin_users() -> list:
    """Retorna usuarios locais que sao administradores."""
    ps = r"""
$result = @()
foreach ($g in @('Administrators','Administradores')) {
    try {
        Get-LocalGroupMember -Group $g -ErrorAction Stop | ForEach-Object {
            if ($_.ObjectClass -eq 'User') {
                $name = ($_.Name -split '\\')[-1]
                if (Get-LocalUser -Name $name -ErrorAction SilentlyContinue) {
                    $result += $name
                }
            }
        }
    } catch {}
}
($result | Sort-Object -Unique) | ConvertTo-Json -Compress
"""
    rc, out, _ = _run_ps(ps, timeout=15)
    if rc == 0 and out.strip() not in ("", "null"):
        try:
            data = json.loads(out)
            if isinstance(data, str):
                data = [data]
            admins = [str(x).strip() for x in data if x and str(x).strip()]
            if admins:
                return admins
        except Exception:
            pass

    # Fallback via net localgroup
    for group in ["Administradores", "Administrators"]:
        rc2, out2, _ = _run(f'net localgroup "{group}"')
        if rc2 != 0:
            continue
        admins, capture = [], False
        for line in out2.splitlines():
            s = line.strip()
            if "---" in s:
                capture = True; continue
            if not capture or not s:
                continue
            if any(x in s.lower() for x in ["o comando", "the command", "mais de um"]):
                break
            if "\\" not in s:
                admins.append(s)
        if admins:
            return admins
    return []


# ── Alterar senha ─────────────────────────────────────────────────────────────

def change_password(username: str, new_password: str,
                    callback=None, creds=None) -> bool:
    """
    Altera senha via net user (direto se admin) ou Set-LocalUser com
    credenciais (sem WinRM).
    """
    if not username or not new_password:
        if callback: callback("✘ Usuario e senha sao obrigatorios.")
        return False
    if callback: callback(f"Alterando senha de '{username}'...")

    # 1. net user direto (funciona se o processo e admin)
    rc, out, err = _run(f'net user "{username}" "{new_password}"')
    if rc == 0:
        if callback: callback(f"✔ Senha de '{username}' alterada com sucesso.")
        return True

    # 2. Set-LocalUser via PowerShell local
    safe = new_password.replace('"', '`"').replace("'", "`'")
    ps = (f'$s = ConvertTo-SecureString "{safe}" -AsPlainText -Force; '
          f'Set-LocalUser -Name "{username}" -Password $s')
    rc2, _, err2 = _run_ps(ps)
    if rc2 == 0:
        if callback: callback(f"✔ Senha de '{username}' alterada (PS).")
        return True

    # 3. ADSI — funciona mesmo sem admin em alguns cenarios
    adsi_ps = (
        f'$u = [adsi]"WinNT://./{username},user"; '
        f'$u.SetPassword("{safe}"); '
        f'$u.SetInfo()'
    )
    rc3, _, err3 = _run_ps(adsi_ps)
    if rc3 == 0:
        if callback: callback(f"✔ Senha de '{username}' alterada (ADSI).")
        return True

    msg = (err or err2 or err3 or out).strip()
    if callback: callback(f"✘ Erro: {msg}\n  Dica: Execute o programa como Administrador.")
    return False


def change_password_direct(username: str, new_password: str,
                           callback=None) -> bool:
    """Atalho direto via net user (processo ja e admin)."""
    return change_password(username, new_password, callback, creds=None)


# ── Expiracao de senha ────────────────────────────────────────────────────────

def set_password_never_expires(username: str, never: bool,
                                callback=None, creds=None) -> bool:
    """
    Define se a senha nunca expira.
    Estrategias: wmic -> Set-LocalUser -> net user -> ADSI
    Nenhuma usa WinRM.
    """
    label = "nunca expira" if never else "expira conforme politica"
    if callback: callback(f"Configurando senha de '{username}': {label}...")

    # 1. wmic — mais confiavel e nao precisa de WinRM
    wmic_val = "FALSE" if never else "TRUE"
    rc, out, err = _run(
        f'wmic useraccount where name="{username}" set PasswordExpires={wmic_val}'
    )
    # wmic retorna rc=0 mesmo quando atualiza, a saida contem "UpdateSuccessful"
    if rc == 0:
        if callback: callback(f"✔ Senha de '{username}': {label}.")
        return True

    # 2. Set-LocalUser PowerShell local
    ps = f'Set-LocalUser -Name "{username}" -PasswordNeverExpires ${str(never).lower()}'
    rc2, _, err2 = _run_ps(ps)
    if rc2 == 0:
        if callback: callback(f"✔ Senha de '{username}': {label} (PS).")
        return True

    # 3. net user /passwordchg — define se usuario pode mudar senha
    # Nota: nao e exatamente "nunca expira" mas e o mais que net user permite
    # Para expiracao real, usamos ADSI
    flag = 65536  # UF_DONT_EXPIRE_PASSWD
    adsi_ps = (
        f'$u = [adsi]"WinNT://./{username},user"; '
        f'$flags = $u.UserFlags.Value; '
        + (f'$u.UserFlags = $flags -bor {flag}; ' if never
           else f'$u.UserFlags = $flags -band (-bnot {flag}); ') +
        f'$u.SetInfo()'
    )
    rc3, _, err3 = _run_ps(adsi_ps)
    if rc3 == 0:
        if callback: callback(f"✔ Senha de '{username}': {label} (ADSI).")
        return True

    msg = (err or err2 or err3 or "").strip()
    if callback: callback(
        f"✘ Erro: {msg}\n  Dica: Execute como Administrador para alterar outro usuario.")
    return False


def force_password_change_on_next_logon(username: str,
                                         callback=None, creds=None) -> bool:
    """Forca troca de senha no proximo login."""
    if callback: callback(f"Forcando troca de senha no proximo login: '{username}'...")

    # net user com /logonpasswordchg:yes
    rc, _, err = _run(f'net user "{username}" /logonpasswordchg:yes')
    if rc == 0:
        if callback: callback(f"✔ '{username}' trocara senha no proximo login.")
        return True

    # ADSI: PasswordExpired = 1
    ps = (f'$u = [adsi]"WinNT://./{username},user"; '
          f'$u.PasswordExpired = 1; $u.SetInfo()')
    rc2, _, err2 = _run_ps(ps)
    if rc2 == 0:
        if callback: callback(f"✔ '{username}' trocara senha no proximo login (ADSI).")
        return True

    if callback: callback(f"✘ Erro: {(err or err2 or '').strip()}")
    return False


# ── Ativar / Desativar conta ──────────────────────────────────────────────────

def set_account_enabled(username: str, enabled: bool,
                         callback=None, creds=None) -> bool:
    action = "Ativando" if enabled else "Desativando"
    if callback: callback(f"{action} conta '{username}'...")

    flag = "/active:yes" if enabled else "/active:no"
    rc, _, err = _run(f'net user "{username}" {flag}')
    if rc == 0:
        verb = "ativada" if enabled else "desativada"
        if callback: callback(f"✔ Conta '{username}' {verb}.")
        return True

    ps_action = "Enable" if enabled else "Disable"
    rc2, _, err2 = _run_ps(f'{ps_action}-LocalUser -Name "{username}"')
    if rc2 == 0:
        verb = "ativada" if enabled else "desativada"
        if callback: callback(f"✔ Conta '{username}' {verb} (PS).")
        return True

    if callback: callback(f"✘ Erro: {(err or err2 or '').strip()}")
    return False


# ── Alterar nome completo ─────────────────────────────────────────────────────

def change_full_name(username: str, full_name: str,
                     callback=None, creds=None) -> bool:
    """Altera o nome completo (display name) do usuario."""
    if not username:
        if callback: callback("✘ Nome de usuario obrigatorio.")
        return False
    if callback: callback(f"Alterando nome completo de '{username}'...")

    safe = full_name.replace('"', "'")
    ps = f'Set-LocalUser -Name "{username}" -FullName "{safe}"'
    rc, _, err = _run_ps(ps)
    if rc == 0:
        if callback: callback(f"✔ Nome completo de '{username}' atualizado.")
        return True

    # Fallback ADSI
    adsi_ps = (f'$u = [adsi]"WinNT://./{username},user"; '
               f'$u.FullName = "{safe}"; $u.SetInfo()')
    rc2, _, err2 = _run_ps(adsi_ps)
    if rc2 == 0:
        if callback: callback(f"✔ Nome completo atualizado (ADSI).")
        return True

    if callback: callback(f"✘ Erro: {(err or err2 or '').strip()}")
    return False


# ── Utilitarios ───────────────────────────────────────────────────────────────

def get_current_user() -> str:
    return os.environ.get("USERNAME", "")

def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False
