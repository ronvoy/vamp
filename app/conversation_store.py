"""Save setup script, execute it, and track with git."""
import json
import os
import re
import shutil
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONV_DIR = os.path.join(BASE_DIR, "conversation")


def _run_git(*args: str, cwd: str | None = None) -> str:
    """Run a git command in CONV_DIR (or override), return stdout."""
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
    """Ensure conversation/ has a git repo."""
    os.makedirs(CONV_DIR, exist_ok=True)
    if os.path.isdir(os.path.join(CONV_DIR, ".git")):
        return
    _run_git("init")
    _run_git("checkout", "-b", "main")
    with open(os.path.join(CONV_DIR, ".gitignore"), "w") as f:
        f.write("__pycache__/\n*.pyc\nnode_modules/\n.venv/\n")
    _run_git("add", "-A")
    _run_git("commit", "-m", "initial commit")


def _git_commit(message: str, folder: str = "."):
    """Stage files in folder and commit."""
    _run_git("add", "-A", "--", folder)
    _run_git("commit", "-m", message)


def _make_commit_msg(agent: str, reasoning: str, task: str) -> str:
    summary = ""
    if reasoning:
        first_line = reasoning.strip().split("\n")[0].strip()
        first_line = re.sub(r"^(I'll |I will |Let me |I'm going to )", "", first_line, flags=re.I)
        summary = first_line[:100]
    if not summary:
        summary = task[:100]
    return f"{agent}: {summary}"


def _run_setup_script(path: str) -> dict:
    """Execute setup.sh in the given directory, return result."""
    script_path = os.path.join(path, "setup.sh")
    if not os.path.isfile(script_path):
        return {"success": False, "output": "No setup.sh found", "exit_code": -1}
    try:
        r = subprocess.run(
            ["bash", script_path],
            cwd=path, capture_output=True, text=True, timeout=60,
        )
        return {
            "success": r.returncode == 0,
            "output": (r.stdout + "\n" + r.stderr).strip(),
            "exit_code": r.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "Script timed out (60s limit)", "exit_code": -2}
    except Exception as e:
        return {"success": False, "output": str(e), "exit_code": -3}


def _list_generated_files(path: str) -> list[str]:
    """List all files in directory (excluding metadata.json and setup.sh)."""
    files = []
    for fname in sorted(os.listdir(path)):
        if fname in ("metadata.json",) or fname.startswith("."):
            continue
        fpath = os.path.join(path, fname)
        if os.path.isfile(fpath):
            files.append(fname)
        elif os.path.isdir(fpath):
            for sub in sorted(os.listdir(fpath)):
                if os.path.isfile(os.path.join(fpath, sub)):
                    files.append(f"{fname}/{sub}")
    return files


def sanitize_folder_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", name.lower())[:50] or "generated-app"


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


def save_conversation(script: str, folder_name: str, task: str, agent: str,
                      reasoning: str = "", raw_response: str = "",
                      usage: dict = None, continue_from: str = "") -> dict:
    """Save script, execute it, git commit. Returns full result dict."""
    _ensure_conv_git()

    if continue_from:
        existing_path = os.path.join(CONV_DIR, continue_from)
        if os.path.isdir(existing_path):
            return _update_conversation(existing_path, continue_from, script, task, agent,
                                        reasoning, raw_response, usage)

    name = sanitize_folder_name(folder_name)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    dir_name = f"{timestamp}_{name}"
    path = os.path.join(CONV_DIR, dir_name)
    os.makedirs(path, exist_ok=True)

    with open(os.path.join(path, "setup.sh"), "w", encoding="utf-8", newline="\n") as f:
        f.write(script)

    exec_result = _run_setup_script(path)

    file_list = _list_generated_files(path)

    meta = {
        "task": task,
        "agent": agent,
        "created": datetime.now().isoformat(),
        "files": file_list,
        "reasoning": reasoning or "",
        "raw_response": raw_response or "",
        "usage": usage or {},
        "script_output": exec_result.get("output", ""),
        "script_success": exec_result.get("success", False),
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

    return {
        "path": path,
        "folder": dir_name,
        "files": file_list,
        "script_output": exec_result.get("output", ""),
        "script_success": exec_result.get("success", False),
        "script_exit_code": exec_result.get("exit_code", -1),
    }


def _update_conversation(path: str, folder: str, script: str, task: str, agent: str,
                         reasoning: str = "", raw_response: str = "",
                         usage: dict = None) -> dict:
    """Update an existing folder: save new script, execute, git commit."""
    with open(os.path.join(path, "setup.sh"), "w", encoding="utf-8", newline="\n") as f:
        f.write(script)

    exec_result = _run_setup_script(path)

    file_list = _list_generated_files(path)
    meta = _read_meta(path)

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
        "files": file_list,
        "reasoning": reasoning or "",
        "raw_response": raw_response or "",
        "usage": usage or {},
        "script_output": exec_result.get("output", ""),
        "script_success": exec_result.get("success", False),
        "history": history,
    })
    with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    commit_msg = _make_commit_msg(agent, reasoning, task)
    _git_commit(commit_msg, folder)

    return {
        "path": path,
        "folder": folder,
        "files": file_list,
        "script_output": exec_result.get("output", ""),
        "script_success": exec_result.get("success", False),
        "script_exit_code": exec_result.get("exit_code", -1),
    }


def get_git_log(folder: str) -> list[dict]:
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
