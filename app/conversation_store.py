"""Save generated code to conversation folder with git tracking at conversation/ level."""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONV_DIR = os.path.join(BASE_DIR, "conversation")


def _run_git(*args: str, cwd: str | None = None) -> str:
    """Run a git command in CONV_DIR (or override with cwd), return stdout."""
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=cwd or CONV_DIR, capture_output=True, text=True, timeout=10,
            env={**os.environ, "GIT_AUTHOR_NAME": "vamp", "GIT_AUTHOR_EMAIL": "vamp@local",
                 "GIT_COMMITTER_NAME": "vamp", "GIT_COMMITTER_EMAIL": "vamp@local"},
        )
        return r.stdout.strip()
    except Exception:
        return ""


def _ensure_conv_git():
    """Ensure conversation/ has a git repo. Init + initial commit if not."""
    os.makedirs(CONV_DIR, exist_ok=True)
    if os.path.isdir(os.path.join(CONV_DIR, ".git")):
        return
    _run_git("init")
    _run_git("checkout", "-b", "main")
    gitignore_path = os.path.join(CONV_DIR, ".gitignore")
    if not os.path.isfile(gitignore_path):
        with open(gitignore_path, "w") as f:
            f.write("")
    _run_git("add", "-A")
    _run_git("commit", "-m", "initial commit")


def _git_commit(message: str, folder: str = "."):
    """Stage files in folder and commit."""
    _run_git("add", "-A", "--", folder)
    _run_git("commit", "-m", message)


def _make_commit_msg(agent: str, reasoning: str, task: str) -> str:
    """Build a commit message from the LLM reasoning or task."""
    summary = ""
    if reasoning:
        first_line = reasoning.strip().split("\n")[0].strip()
        first_line = re.sub(r"^(I'll |I will |Let me |I'm going to )", "", first_line, flags=re.I)
        summary = first_line[:100]
    if not summary:
        summary = task[:100]
    return f"{agent}: {summary}"


def list_conversations():
    """List all conversation folders with metadata, newest first."""
    if not os.path.isdir(CONV_DIR):
        return []
    items = []
    for name in sorted(os.listdir(CONV_DIR), reverse=True):
        path = os.path.join(CONV_DIR, name)
        if not os.path.isdir(path) or name.startswith("."):
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
    """Get full conversation details including files, git diffs and history."""
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
    result = {"folder": folder, "metadata": meta, "files": files}
    if os.path.isdir(os.path.join(CONV_DIR, ".git")):
        result["git_log"] = get_git_log(folder)
        result["git_diff"] = get_git_diff(folder)
    return result


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


def save_conversation(files: dict[str, str], folder_name: str, task: str, agent: str,
                      reasoning: str = "", raw_response: str = "",
                      usage: dict = None, continue_from: str = "") -> str:
    """Save files to conversation folder. If continue_from is set, update existing folder."""
    _ensure_conv_git()

    if continue_from:
        existing_path = os.path.join(CONV_DIR, continue_from)
        if os.path.isdir(existing_path):
            return _update_conversation(existing_path, continue_from, files, task, agent,
                                        reasoning, raw_response, usage)

    name = sanitize_folder_name(folder_name)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dir_name = f"{timestamp}_{name}"
    path = os.path.join(CONV_DIR, dir_name)
    os.makedirs(path, exist_ok=True)

    file_names = _write_files(path, files)
    _write_readme_if_missing(path, files, name, task)
    if "README.md" not in files:
        file_names.append("README.md")

    meta = {
        "task": task,
        "agent": agent,
        "created": datetime.now().isoformat(),
        "files": file_names,
        "reasoning": reasoning or "",
        "raw_response": raw_response or "",
        "usage": usage or {},
        "history": [{
            "task": task,
            "agent": agent,
            "timestamp": datetime.now().isoformat(),
        }],
    }
    with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    commit_msg = _make_commit_msg(agent, reasoning, task)
    _git_commit(commit_msg, dir_name)
    return path


def _update_conversation(path: str, folder: str, files: dict[str, str], task: str, agent: str,
                         reasoning: str = "", raw_response: str = "",
                         usage: dict = None) -> str:
    """Update an existing conversation folder with new files and git commit."""
    file_names = _write_files(path, files)
    meta = _read_meta(path)
    existing_files = set(meta.get("files", []))
    all_files = sorted(existing_files | set(file_names))

    history = meta.get("history", [])
    if not history and meta.get("task"):
        history = [{"task": meta["task"], "agent": meta.get("agent", ""), "timestamp": meta.get("created", "")}]
    history.append({
        "task": task,
        "agent": agent,
        "timestamp": datetime.now().isoformat(),
    })

    meta.update({
        "task": task,
        "agent": agent,
        "files": list(all_files),
        "reasoning": reasoning or "",
        "raw_response": raw_response or "",
        "usage": usage or {},
        "history": history,
    })
    with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    commit_msg = _make_commit_msg(agent, reasoning, task)
    _git_commit(commit_msg, folder)
    return path


def _write_files(path: str, files: dict[str, str]) -> list[str]:
    """Write files dict to path, return list of written filenames."""
    written = []
    for fname, content in files.items():
        if not fname or ".." in fname or "/" in fname or "\\" in fname:
            continue
        safe_name = os.path.basename(fname) or "output.txt"
        fpath = os.path.join(path, safe_name)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content or "")
        written.append(safe_name)
    return written


def _write_readme_if_missing(path: str, files: dict, name: str, task: str):
    """Auto-generate README.md if not in files."""
    if "README.md" in files:
        return
    if "main.py" in files:
        readme = f"# {name}\n\n{task}\n\n## Run\n\n```bash\npip install -r requirements.txt\npython main.py\n```\n"
    elif "index.html" in files:
        readme = f"# {name}\n\n{task}\n\n## Run\n\nOpen `index.html` in a browser.\n"
    else:
        readme = f"# {name}\n\n{task}\n"
    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)


def get_git_log(folder: str) -> list[dict]:
    """Get git commit history filtered to a specific conversation folder."""
    if not os.path.isdir(os.path.join(CONV_DIR, ".git")):
        return []
    raw = _run_git("log", "--pretty=format:%H||%ai||%s", "--reverse", "--", f"{folder}/")
    if not raw:
        return []
    commits = []
    for line in raw.strip().split("\n"):
        parts = line.split("||", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0][:8], "date": parts[1], "message": parts[2]})
    return commits


def get_git_diff(folder: str, commit: str = "HEAD~1..HEAD") -> dict[str, list[str]]:
    """Get git diff for a conversation folder. Returns {filename: [diff_lines]}."""
    if not os.path.isdir(os.path.join(CONV_DIR, ".git")):
        return {}
    raw = _run_git("diff", commit, "--", f"{folder}/", f":(exclude){folder}/metadata.json")
    if not raw:
        return {}
    file_diffs: dict[str, list[str]] = {}
    current_file = None
    for line in raw.split("\n"):
        if line.startswith("diff --git"):
            m = re.search(r"b/" + re.escape(folder) + r"/(.+)$", line)
            current_file = m.group(1) if m else None
            if not m:
                m2 = re.search(r"b/(.+)$", line)
                current_file = m2.group(1) if m2 else "unknown"
            if current_file:
                file_diffs[current_file] = []
        elif current_file is not None:
            if line.startswith("index "):
                continue
            file_diffs[current_file].append(line)
    return file_diffs


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
    parts = folder.split("_", 2)
    ts = parts[0] + "_" + parts[1] if len(parts) >= 2 else datetime.now().strftime("%Y-%m-%d_%H%M")
    new_folder = f"{ts}_{safe_new}"
    new_path = os.path.join(CONV_DIR, new_folder)
    if os.path.exists(new_path) and new_path != old_path:
        return None
    try:
        os.rename(old_path, new_path)
        _ensure_conv_git()
        _run_git("add", "-A")
        _run_git("commit", "-m", f"rename: {folder} -> {new_folder}")
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
        _ensure_conv_git()
        _run_git("add", "-A")
        _run_git("commit", "-m", f"delete: {folder}")
        return True
    except OSError:
        return False
