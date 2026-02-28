"""Save generated code to conversation folder with metadata."""
import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONV_DIR = os.path.join(BASE_DIR, "conversation")

def sanitize_folder_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\-]", "", name.lower())[:50] or "generated-app"

def save_conversation(main_py: str, requirements: str, folder_name: str, task: str, agent: str) -> str:
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
    meta = {"task": task, "agent": agent, "created": datetime.now().isoformat()}
    import json
    with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return path
