"""Save generated code to conversation folder with metadata."""
import json
import os
import re
import shutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONV_DIR = os.path.join(BASE_DIR, "conversation")


def list_conversations():
    """List all conversation folders with metadata, newest first."""
    if not os.path.isdir(CONV_DIR):
        return []
    items = []
    for name in sorted(os.listdir(CONV_DIR), reverse=True):
        path = os.path.join(CONV_DIR, name)
        if not os.path.isdir(path):
            continue
        meta = _read_meta(path)
        items.append({
            "folder": name,
            "task": meta.get("task", ""),
            "agent": meta.get("agent", ""),
            "created": meta.get("created", ""),
        })
    return items


def get_conversation(folder: str) -> dict | None:
    """Get full conversation details including files and content."""
    path = os.path.join(CONV_DIR, folder)
    if not os.path.isdir(path) or ".." in folder or "/" in folder or "\\" in folder:
        return None
    meta = _read_meta(path)
    files = {}
    for fname in os.listdir(path):
        fpath = os.path.join(path, fname)
        if os.path.isfile(fpath) and fname != "metadata.json":
            try:
                with open(fpath, encoding="utf-8") as f:
                    files[fname] = f.read()
            except (IOError, UnicodeDecodeError):
                files[fname] = "(binary or unreadable)"
    return {"folder": folder, "metadata": meta, "files": files}


def _read_meta(path: str) -> dict:
    meta_path = os.path.join(path, "metadata.json")
    if not os.path.isfile(meta_path):
        return {}
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def sanitize_folder_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", name.lower())[:50] or "generated-app"


def save_conversation(main_py: str, requirements: str, folder_name: str, task: str, agent: str, reasoning: str = "", raw_response: str = "", usage: dict = None) -> str:
    """Create conversation subfolder, write files, return path."""
    name = sanitize_folder_name(folder_name)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dir_name = f"{timestamp}_{name}"
    path = os.path.join(CONV_DIR, dir_name)
    os.makedirs(path, exist_ok=True)
    reqs = requirements.strip() or "flask>=3.0.0\nrequests>=2.31.0\n"
    with open(os.path.join(path, "main.py"), "w", encoding="utf-8") as f:
        f.write(main_py)
    with open(os.path.join(path, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write(reqs)
    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"# {name}\n\n{task}\n\n## Run\n\n```bash\npip install -r requirements.txt\npython main.py\n```\n")
    meta = {
        "task": task,
        "agent": agent,
        "created": datetime.now().isoformat(),
        "files": ["main.py", "requirements.txt", "README.md"],
        "reasoning": reasoning or "",
        "raw_response": raw_response or "",
        "usage": usage or {},
    }
    with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return path


def rename_conversation(folder: str, new_name: str) -> str | None:
    """Rename conversation folder. Returns new folder name or None on error."""
    if ".." in folder or "/" in folder or "\\" in folder or ".." in new_name:
        return None
    safe_new = sanitize_folder_name(new_name)
    if not safe_new:
        return None
    old_path = os.path.join(CONV_DIR, folder)
    if not os.path.isdir(old_path):
        return None
    # Keep timestamp, change name part
    parts = folder.split("_", 2)
    ts = parts[0] + "_" + parts[1] if len(parts) >= 2 else datetime.now().strftime("%Y-%m-%d_%H%M")
    new_folder = f"{ts}_{safe_new}"
    new_path = os.path.join(CONV_DIR, new_folder)
    if os.path.exists(new_path) and new_path != old_path:
        return None
    try:
        os.rename(old_path, new_path)
        return new_folder
    except OSError:
        return None


def delete_conversation(folder: str) -> bool:
    """Delete conversation folder and all contents."""
    if ".." in folder or "/" in folder or "\\" in folder:
        return False
    path = os.path.join(CONV_DIR, folder)
    if not os.path.isdir(path):
        return False
    try:
        shutil.rmtree(path)
        return True
    except OSError:
        return False
