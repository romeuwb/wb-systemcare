# -*- coding: utf-8 -*-
"""
file_scanner.py — Varredura de arquivos do perfil do usuário.
Versão 1.5

Mudanças:
  - scan_profile_folders() retorna APENAS o primeiro nível (pastas raiz)
  - scan_folder_children(): expande UMA pasta sob demanda (lazy loading)
  - Cada pasta raiz traz: count de itens dentro, tamanho total
  - Opera exclusivamente no perfil do usuário atual
"""

import os
import stat
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Pastas do perfil ──────────────────────────────────────────────────────────
PROFILE_FOLDERS = [
    ("Desktop",              "Área de Trabalho"),
    ("Documents",            "Documentos"),
    ("Downloads",            "Downloads"),
    ("Music",                "Músicas"),
    ("Videos",               "Vídeos"),
    ("Pictures",             "Imagens"),
    ("3D Objects",           "Objetos 3D"),
    ("Saved Games",          "Jogos Salvos"),
    ("Searches",             "Pesquisas"),
    ("Links",                "Links"),
    ("Favorites",            "Favoritos"),
    ("AppData\\Local\\Temp", "Temp (Local)"),
]


# ── Utilitários ───────────────────────────────────────────────────────────────

def _get_size_str(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024**2:.1f} MB"
    else:
        return f"{size_bytes / 1024**3:.1f} GB"


def _get_folder_size(folder_path: str) -> int:
    total = 0
    try:
        for dirpath, _, filenames in os.walk(folder_path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return total


def _count_children(folder_path: str) -> int:
    """Conta quantos itens existem diretamente dentro de uma pasta."""
    try:
        return len(os.listdir(folder_path))
    except Exception:
        return 0


def _make_item(full_path: str, root_folder_path: str,
               folder_label: str, folder_key: str,
               depth: int = 0) -> dict:
    try:
        st     = os.stat(full_path)
        is_dir = os.path.isdir(full_path)
        sz     = _get_folder_size(full_path) if is_dir else st.st_size
        mod    = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")
        try:
            rel = os.path.relpath(full_path, root_folder_path)
        except ValueError:
            rel = os.path.basename(full_path)
    except Exception:
        is_dir = os.path.isdir(full_path)
        sz, mod, rel = 0, "—", os.path.basename(full_path)

    children = _count_children(full_path) if is_dir else 0

    return {
        "path":         full_path,
        "name":         os.path.basename(full_path),
        "rel_path":     rel,
        "full_path":    full_path,
        "type":         "Pasta" if is_dir else "Arquivo",
        "size_bytes":   sz,
        "size_str":     _get_size_str(sz),
        "modified":     mod,
        "ext":          "" if is_dir else Path(full_path).suffix.lower(),
        "is_dir":       is_dir,
        "has_children": children > 0,
        "children_count": children,
        "folder_label": folder_label,
        "folder_key":   folder_key,
        "depth":        depth,
        "selected":     False,
        "expanded":     False,
    }


# ── Resolução de pastas especiais ─────────────────────────────────────────────

def get_user_profile_path() -> str:
    return os.path.expanduser("~")


def get_current_username() -> str:
    return os.environ.get("USERNAME", os.path.basename(get_user_profile_path()))


def resolve_special_folder(folder_name: str) -> str:
    profile = get_user_profile_path()
    env_map = {
        "Desktop":              os.environ.get("USERPROFILE", profile) + "\\Desktop",
        "Documents":            os.environ.get("USERPROFILE", profile) + "\\Documents",
        "Downloads":            os.environ.get("USERPROFILE", profile) + "\\Downloads",
        "Music":                os.environ.get("USERPROFILE", profile) + "\\Music",
        "Videos":               os.environ.get("USERPROFILE", profile) + "\\Videos",
        "Pictures":             os.environ.get("USERPROFILE", profile) + "\\Pictures",
        "3D Objects":           os.environ.get("USERPROFILE", profile) + "\\3D Objects",
        "Saved Games":          os.environ.get("USERPROFILE", profile) + "\\Saved Games",
        "Searches":             os.environ.get("USERPROFILE", profile) + "\\Searches",
        "Links":                os.environ.get("USERPROFILE", profile) + "\\Links",
        "Favorites":            os.environ.get("USERPROFILE", profile) + "\\Favorites",
        "AppData\\Local\\Temp": os.environ.get("LOCALAPPDATA",
                                profile + "\\AppData\\Local") + "\\Temp",
    }
    try:
        import winreg
        _REG = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
        _MAP = {"Desktop":"Desktop","Documents":"Personal",
                "Music":"My Music","Videos":"My Video","Pictures":"My Pictures"}
        if folder_name in _MAP:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG) as k:
                val, _ = winreg.QueryValueEx(k, _MAP[folder_name])
                if os.path.exists(val):
                    return val
    except Exception:
        pass
    return env_map.get(folder_name, os.path.join(profile, folder_name))


# ── Varredura: primeiro nível de cada pasta do perfil ────────────────────────

def scan_profile_folders(callback=None, recursive: bool = False) -> list:
    """
    Retorna apenas o primeiro nível (conteúdo direto) de cada pasta do perfil.
    Cada item inclui has_children e children_count para suporte a expansão lazy.
    """
    all_items = []
    username  = get_current_username()

    for folder_name, display_name in PROFILE_FOLDERS:
        folder_path = resolve_special_folder(folder_name)
        if not os.path.exists(folder_path):
            continue
        if callback:
            callback(f"Escaneando {display_name}...")
        try:
            entries = sorted(os.listdir(folder_path),
                             key=lambda e: (not os.path.isdir(
                                 os.path.join(folder_path, e)), e.lower()))
            for entry in entries:
                full = os.path.join(folder_path, entry)
                item = _make_item(full, folder_path, display_name, folder_name, depth=0)
                all_items.append(item)
            if callback:
                callback(f"✔ {display_name}: {len(entries)} item(ns).")
        except PermissionError:
            if callback:
                callback(f"⚠ Sem permissão: {display_name}")
        except Exception as e:
            if callback:
                callback(f"✘ Erro em {display_name}: {e}")

    return all_items


def scan_folder_children(folder_path: str, folder_label: str,
                         folder_key: str, depth: int,
                         callback=None) -> list:
    """
    Expande UMA pasta: retorna o conteúdo do primeiro nível de folder_path.
    Usado para lazy loading quando o usuário expande uma pasta na Treeview.
    """
    items = []
    # Raiz para calcular rel_path é a própria pasta expandida
    root = folder_path
    try:
        entries = sorted(os.listdir(folder_path),
                         key=lambda e: (not os.path.isdir(
                             os.path.join(folder_path, e)), e.lower()))
        for entry in entries:
            full = os.path.join(folder_path, entry)
            item = _make_item(full, root, folder_label, folder_key, depth=depth)
            items.append(item)
    except PermissionError:
        if callback:
            callback(f"⚠ Sem permissão para expandir: {os.path.basename(folder_path)}")
    except Exception as e:
        if callback:
            callback(f"✘ Erro ao expandir: {e}")
    return items


def scan_single_folder(folder_path: str, callback=None) -> list:
    """Escaneia uma pasta personalizada (primeiro nível)."""
    if not os.path.exists(folder_path):
        if callback:
            callback(f"✘ Não existe: {folder_path}")
        return []
    label = os.path.basename(folder_path)
    items = []
    try:
        entries = sorted(os.listdir(folder_path),
                         key=lambda e: (not os.path.isdir(
                             os.path.join(folder_path, e)), e.lower()))
        for entry in entries:
            full = os.path.join(folder_path, entry)
            item = _make_item(full, folder_path, label, folder_path, depth=0)
            items.append(item)
        if callback:
            callback(f"✔ {label}: {len(items)} item(ns).")
    except Exception as e:
        if callback:
            callback(f"✘ {e}")
    return items


# ── Exclusão ──────────────────────────────────────────────────────────────────

def delete_items(items: list, callback=None) -> dict:
    import shutil
    results      = {"deleted": 0, "failed": 0, "errors": []}
    deleted_dirs = set()

    sorted_items = sorted(items, key=lambda i: -i.get("depth", 0))

    for item in sorted_items:
        path = item["path"]
        skip = False
        for d in deleted_dirs:
            try:
                if Path(path).is_relative_to(Path(d)):
                    skip = True; break
            except Exception:
                pass
        if skip:
            continue
        try:
            if item["is_dir"]:
                shutil.rmtree(path, ignore_errors=False)
                deleted_dirs.add(path)
            else:
                try:
                    os.chmod(path, stat.S_IWRITE)
                except Exception:
                    pass
                os.remove(path)
            results["deleted"] += 1
            if callback:
                callback(f"✔ Excluído: {item['name']}")
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{item['name']}: {e}")
            if callback:
                callback(f"✘ Falha: {item['name']}: {e}")
    return results


# ── Resumo ────────────────────────────────────────────────────────────────────

def get_summary(items: list) -> dict:
    total_size = sum(i["size_bytes"] for i in items)
    files      = sum(1 for i in items if not i["is_dir"])
    folders    = sum(1 for i in items if i["is_dir"])
    by_folder  = {}
    for item in items:
        lbl = item.get("folder_label", "Outros")
        by_folder.setdefault(lbl, {"count": 0, "size": 0})
        by_folder[lbl]["count"] += 1
        by_folder[lbl]["size"]  += item["size_bytes"]
    return {
        "total_items":   len(items),
        "total_files":   files,
        "total_folders": folders,
        "total_size":    _get_size_str(total_size),
        "total_bytes":   total_size,
        "by_folder":     by_folder,
        "username":      get_current_username(),
    }
