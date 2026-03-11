"""Save setup script, execute it, and track with git."""
import json
import os
import re
import shutil
import signal
import subprocess
import threading
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONV_DIR = os.path.join(BASE_DIR, "conversation")

# Track running processes: folder -> {"proc": Popen, "output": list, "done": bool}
_running: dict[str, dict] = {}


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

    # Check if this folder was branched from another — prepend ancestor history
    ancestor_commits = []
    meta_path = os.path.join(CONV_DIR, folder, "metadata.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            bf = meta.get("branched_from")
            if bf and bf.get("folder") and bf.get("full_hash"):
                parent_folder = bf["folder"]
                branch_hash = bf["full_hash"]
                # Get parent's full log (recursive — handles chained branches)
                parent_log = get_git_log(parent_folder)
                # Keep only commits up to and including the branch point
                for pc in parent_log:
                    ancestor_commits.append(pc)
                    if pc["full_hash"] == branch_hash:
                        break
        except Exception:
            pass

    raw = _run_git("log", "--pretty=format:%H||%ai||%s", "--reverse", "--", f"{folder}/")
    commits = []
    if raw:
        for line in raw.strip().split("\n"):
            parts = line.split("||", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0][:8], "full_hash": parts[0], "date": parts[1], "message": parts[2]})

    if ancestor_commits:
        return ancestor_commits + commits
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


def detect_runnable(folder: str) -> dict | None:
    """Detect the main runnable file and how to execute it."""
    if ".." in folder or "/" in folder or "\\" in folder:
        return None
    path = os.path.join(CONV_DIR, folder)
    if not os.path.isdir(path):
        return None

    # Walk into subdirectories too (setup.sh often creates a subfolder)
    candidates = []
    for root, dirs, fnames in os.walk(path):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".venv", "__pycache__", ".git")]
        for f in fnames:
            candidates.append(os.path.relpath(os.path.join(root, f), path).replace("\\", "/"))

    # Priority order for detection
    # 1. index.html (static web — serve directly)
    for c in candidates:
        if os.path.basename(c) == "index.html":
            return {"type": "html", "file": c, "cwd": path}

    # 2. Python files with common entry-point names
    py_entries = ["main.py", "app.py", "server.py", "run.py"]
    for c in candidates:
        if os.path.basename(c) in py_entries:
            return {"type": "python", "file": c, "cwd": path}

    # 3. Any .py file (pick the first one that's not setup-related)
    for c in candidates:
        if c.endswith(".py") and os.path.basename(c) not in ("setup.py",) and c != "setup.sh":
            return {"type": "python", "file": c, "cwd": path}

    # 4. Node.js
    for c in candidates:
        if os.path.basename(c) in ("index.js", "server.js", "app.js"):
            return {"type": "node", "file": c, "cwd": path}

    return None


def run_project(folder: str) -> dict:
    """Start running a project. Returns info about the run."""
    if folder in _running and not _running[folder].get("done"):
        return {"error": "Already running", "running": True}

    runnable = detect_runnable(folder)
    if not runnable:
        return {"error": "No runnable file found"}

    path = os.path.join(CONV_DIR, folder)
    run_type = runnable["type"]
    run_file = runnable["file"]
    cwd = path

    if run_type == "html":
        # For HTML files, no process needed — frontend opens it directly
        return {"type": "html", "file": run_file, "folder": folder, "running": False}

    # Build command
    if run_type == "python":
        cmd = ["python", run_file]
    elif run_type == "node":
        cmd = ["node", run_file]
    else:
        return {"error": f"Unknown run type: {run_type}"}

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except Exception as e:
        return {"error": str(e)}

    entry = {"proc": proc, "output": [], "done": False, "type": run_type, "file": run_file}
    _running[folder] = entry

    def reader():
        try:
            for line in proc.stdout:
                entry["output"].append(line)
            proc.wait()
        finally:
            entry["done"] = True

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    return {"type": run_type, "file": run_file, "folder": folder, "pid": proc.pid, "running": True}


def send_input(folder: str, text: str) -> dict:
    """Send text input to a running process's stdin."""
    entry = _running.get(folder)
    if not entry or entry["done"]:
        return {"error": "No running process"}
    try:
        entry["proc"].stdin.write(text + "\n")
        entry["proc"].stdin.flush()
        return {"sent": True}
    except Exception as e:
        return {"error": str(e)}


def get_run_output(folder: str, offset: int = 0) -> dict:
    """Get buffered output from a running process starting at offset."""
    entry = _running.get(folder)
    if not entry:
        return {"lines": [], "offset": 0, "done": True, "running": False}
    lines = entry["output"][offset:]
    return {
        "lines": lines,
        "offset": offset + len(lines),
        "done": entry["done"],
        "running": not entry["done"],
        "exit_code": entry["proc"].returncode if entry["done"] else None,
    }


def stop_project(folder: str) -> dict:
    """Stop a running project process."""
    entry = _running.get(folder)
    if not entry or entry["done"]:
        return {"stopped": True}
    proc = entry["proc"]
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception:
        proc.kill()
    entry["done"] = True
    return {"stopped": True}


def git_reset_to_commit(folder: str, commit_hash: str, mode: str = "soft") -> dict:
    """Reset a project folder to a specific commit."""
    if "." in commit_hash.replace(".", "", 1) or not re.match(r'^[a-f0-9]+$', commit_hash):
        return {"error": "Invalid commit hash"}
    if mode not in ("soft", "hard"):
        return {"error": "Mode must be soft or hard"}
    _ensure_conv_git()
    # First commit everything currently staged
    _run_git("add", "-A")
    _run_git("commit", "-m", f"pre-reset snapshot of {folder}")
    # Perform the reset: checkout files from that commit for this folder
    result = _run_git("checkout", commit_hash, "--", f"{folder}/")
    _run_git("add", "-A", "--", f"{folder}/")
    _run_git("commit", "-m", f"reset {folder} to {commit_hash[:8]} ({mode})")
    return {"ok": True, "commit": commit_hash[:8], "mode": mode}


def git_branch_from_commit(folder: str, commit_hash: str) -> dict:
    """Create a copy of the project at a specific commit as a new conversation entry."""
    if not re.match(r'^[a-f0-9]+$', commit_hash):
        return {"error": "Invalid commit hash"}
    _ensure_conv_git()
    path = os.path.join(CONV_DIR, folder)
    if not os.path.isdir(path):
        return {"error": "Folder not found"}

    # Create new folder name
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base_name = re.sub(r'^\d{4}-\d{2}-\d{2}_\d{4}_', '', folder)
    new_folder = f"{timestamp}_{base_name}-at-{commit_hash[:8]}"
    new_path = os.path.join(CONV_DIR, new_folder)
    os.makedirs(new_path, exist_ok=True)

    # Use git show to extract files at that commit
    file_list = _run_git("ls-tree", "--name-only", "-r", commit_hash, "--", f"{folder}/")
    if not file_list:
        shutil.rmtree(new_path, ignore_errors=True)
        return {"error": "No files found at that commit"}

    for fline in file_list.strip().split("\n"):
        # fline is like "folder_name/subdir/file.py"
        rel = fline[len(folder) + 1:]  # strip the original folder prefix
        if not rel:
            continue
        dest = os.path.join(new_path, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        content = _run_git("show", f"{commit_hash}:{fline}")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)

    # Update metadata to note this is a branch
    meta_path = os.path.join(new_path, "metadata.json")
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            meta["branched_from"] = {"folder": folder, "commit": commit_hash[:8], "full_hash": commit_hash}
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
        except Exception:
            pass

    _run_git("add", "-A", "--", new_folder)
    _run_git("commit", "-m", f"branch {folder} at {commit_hash[:8]} -> {new_folder}")
    return {"ok": True, "new_folder": new_folder}


def run_at_commit(folder: str, commit_hash: str) -> dict:
    """Create a temp branch at a commit and run the project from there."""
    if not re.match(r'^[a-f0-9]+$', commit_hash):
        return {"error": "Invalid commit hash"}
    _ensure_conv_git()

    # Create a temporary directory with files from that commit
    temp_key = f"_temp_{folder}_{commit_hash[:8]}"
    temp_path = os.path.join(CONV_DIR, temp_key)
    if os.path.isdir(temp_path):
        shutil.rmtree(temp_path)
    os.makedirs(temp_path)

    file_list = _run_git("ls-tree", "--name-only", "-r", commit_hash, "--", f"{folder}/")
    if not file_list:
        shutil.rmtree(temp_path, ignore_errors=True)
        return {"error": "No files found at that commit"}

    for fline in file_list.strip().split("\n"):
        rel = fline[len(folder) + 1:]
        if not rel:
            continue
        dest = os.path.join(temp_path, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        content = _run_git("show", f"{commit_hash}:{fline}")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(content)

    # Now run using the temp key as folder
    result = run_project(temp_key)
    result["temp_key"] = temp_key
    result["commit"] = commit_hash[:8]
    return result


def cleanup_temp_run(temp_key: str) -> dict:
    """Stop a temp-branch run and clean up."""
    stop_project(temp_key)
    temp_path = os.path.join(CONV_DIR, temp_key)
    if os.path.isdir(temp_path):
        shutil.rmtree(temp_path, ignore_errors=True)
    return {"cleaned": True}
