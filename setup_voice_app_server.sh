#!/usr/bin/env bash
# Vamp — Voice-to-App Maker: Bootstrap script for Flask voice server
# Run: chmod +x setup_voice_app_server.sh && ./setup_voice_app_server.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_DIR="$SCRIPT_DIR/app"
CONV_DIR="$SCRIPT_DIR/conversation"
STATIC_DIR="$APP_DIR/static"
mkdir -p "$APP_DIR" "$CONV_DIR" "$STATIC_DIR"

echo "[Vamp] Creating Flask voice-to-app server..."

# --- requirements.txt ---
cat > "$APP_DIR/requirements.txt" << 'REQ'
flask>=3.0.0
flask-cors>=4.0.0
openai>=1.6.0
python-dotenv>=1.0.0
requests>=2.31.0
REQ

# --- .env.example ---
cat > "$APP_DIR/.env.example" << 'ENV'
# OpenRouter - all LLM calls (GPT, Claude, etc.)
OPENROUTER_API_KEY=sk-or-v1-your-openrouter-key

# OpenAI - for Whisper transcription only
OPENAI_API_KEY=sk-your-openai-key

# Default agent model: openai/gpt-4o-mini | anthropic/claude-3-5-haiku
DEFAULT_AGENT=openai

# Port
PORT=5000
ENV

# --- transcriber.py ---
cat > "$APP_DIR/transcriber.py" << 'TRANS'
"""Voice transcription and translation via OpenAI Whisper."""
import os
from openai import OpenAI

def transcribe(audio_path: str, language: str | None = None) -> str:
    """Transcribe audio file to text. Optional translation to English."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language,
            response_format="text",
        )
    return transcript.strip() if transcript else ""

def transcribe_bytes(audio_bytes: bytes, language: str | None = None) -> str:
    """Transcribe raw audio bytes."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        try:
            return transcribe(tmp.name, language)
        finally:
            os.unlink(tmp.name)
TRANS

# --- agent_registry.py ---
cat > "$APP_DIR/agent_registry.py" << 'AGENT'
"""Agent selection and routing from voice command excerpts."""
import os
import re

AGENTS = {
    "openai": {"name": "GPT", "keywords": ["gpt", "openai", "chatgpt"]},
    "anthropic": {"name": "Claude", "keywords": ["claude", "anthropic"]},
}

def select_agent(text: str) -> str:
    """Parse voice command, return agent id. Fallback to DEFAULT_AGENT."""
    text_lower = text.lower().strip()
    for agent_id, info in AGENTS.items():
        if any(kw in text_lower for kw in info["keywords"]):
            return agent_id
    return os.environ.get("DEFAULT_AGENT", "openai")

def extract_task(text: str) -> str:
    """Remove agent keywords to get the actual task."""
    text_lower = text.lower()
    for agent_id, info in AGENTS.items():
        for kw in info["keywords"]:
            text_lower = re.sub(rf"\b{re.escape(kw)}\b", "", text_lower, flags=re.I)
    return " ".join(text_lower.split()).strip()
AGENT

# --- code_generator.py ---
cat > "$APP_DIR/code_generator.py" << 'GEN'
"""Generate code and folder name via OpenRouter (unified LLM API)."""
import os
import re
from openai import OpenAI

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

MODELS = {
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-3-5-haiku",
}

SYSTEM_PROMPT = """You are an expert coding agent. Given a user task:
1. Produce runnable Python code.
2. Always output a main.py and requirements.txt.
3. Use triple-backtick code blocks with language (e.g. ```python).
4. At the end, output a single line: FOLDER_NAME: <kebab-case-name>
   Example: FOLDER_NAME: todo-cli
The folder name must be short, descriptive, alphanumeric with hyphens only."""

def _client():
    return OpenAI(
        base_url=OPENROUTER_BASE,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )

def generate_openai(task: str) -> tuple[str, str, str]:
    """Generate code via OpenRouter -> GPT."""
    return _generate(task, "openai")

def generate_anthropic(task: str) -> tuple[str, str, str]:
    """Generate code via OpenRouter -> Claude."""
    return _generate(task, "anthropic")

def _generate(task: str, agent: str) -> tuple[str, str, str]:
    model = MODELS.get(agent, MODELS["openai"])
    client = _client()
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task}"},
        ],
        max_tokens=4096,
    )
    content = r.choices[0].message.content
    return _parse_response(content)

def _parse_response(content: str) -> tuple[str, str, str]:
    """Extract main.py, requirements.txt, and FOLDER_NAME from LLM response."""
    folder_name = "generated-app"
    blocks = re.findall(r"```(\w*)\n(.*?)```", content, re.DOTALL)
    main_py, requirements = "", "flask>=3.0.0\nrequests>=2.31.0\n"
    for lang, code in blocks:
        code = code.strip()
        if "FOLDER_NAME:" in code:
            continue
        lang = (lang or "python").lower()
        if "req" in lang or "txt" in lang or "pip" in lang or "requirement" in lang:
            requirements = code if code else requirements
        else:
            main_py = code if not main_py else main_py  # first python block = main
    m = re.search(r"FOLDER_NAME:\s*([a-z0-9\-]+)", content, re.I)
    if m:
        folder_name = m.group(1).strip()
    if not main_py and blocks:
        main_py = blocks[0][1].strip()
    if not main_py:
        main_py = content
    return main_py, requirements, folder_name
GEN

# --- conversation_store.py ---
cat > "$APP_DIR/conversation_store.py" << 'STORE'
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
STORE

# --- app.py ---
cat > "$APP_DIR/app.py" << 'APP'
"""Flask voice-to-app server: transcribe voice -> select agent -> generate code -> save."""
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, redirect
from flask_cors import CORS

from transcriber import transcribe_bytes
from agent_registry import select_agent, extract_task
from code_generator import generate_openai, generate_anthropic
from conversation_store import save_conversation

app = Flask(__name__)
CORS(app)

GENERATORS = {
    "openai": generate_openai,
    "anthropic": generate_anthropic,
}

@app.route("/")
def index():
    return redirect("/static/voice.html")

@app.route("/api/voice", methods=["POST"])
def handle_voice():
    """Receive audio, transcribe, select agent, generate code, save to conversation/."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    f = request.files["audio"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    audio_bytes = f.read()
    if not audio_bytes:
        return jsonify({"error": "Empty audio"}), 400

    text = transcribe_bytes(audio_bytes)
    if not text:
        return jsonify({"error": "Transcription failed", "text": ""}), 500

    agent = select_agent(text)
    task = extract_task(text) or text
    gen = GENERATORS.get(agent, generate_openai)
    try:
        main_py, requirements, folder_name = gen(task)
    except Exception as e:
        return jsonify({"error": str(e), "text": text}), 500

    path = save_conversation(main_py, requirements, folder_name, task, agent)
    return jsonify({
        "text": text,
        "task": task,
        "agent": agent,
        "path": path,
        "folder": os.path.basename(path),
    })

@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    """Transcribe only."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    audio_bytes = request.files["audio"].read()
    text = transcribe_bytes(audio_bytes)
    agent = select_agent(text)
    task = extract_task(text) or text
    return jsonify({"text": text, "agent": agent, "task": task})

@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate from text (no audio)."""
    data = request.get_json() or {}
    task = data.get("task") or data.get("text", "")
    agent = data.get("agent") or select_agent(task)
    if not task:
        return jsonify({"error": "No task"}), 400
    gen = GENERATORS.get(agent, generate_openai)
    try:
        main_py, requirements, folder_name = gen(task)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    path = save_conversation(main_py, requirements, folder_name, task, agent)
    return jsonify({"path": path, "folder": os.path.basename(path)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
APP

# --- static/voice.html ---
cat > "$STATIC_DIR/voice.html" << 'HTML'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Vamp — Voice to App</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui; max-width: 600px; margin: 2rem auto; padding: 1rem; }
    h1 { color: #333; }
    button { padding: 0.75rem 1.5rem; font-size: 1rem; cursor: pointer; border-radius: 8px; border: none; }
    #record { background: #e74c3c; color: white; }
    #record.recording { background: #c0392b; animation: pulse 1s infinite; }
    @keyframes pulse { 50% { opacity: 0.8; } }
    #output { margin-top: 1rem; padding: 1rem; background: #f5f5f5; border-radius: 8px; white-space: pre-wrap; font-size: 0.9rem; }
    .path { color: #27ae60; font-weight: bold; }
  </style>
</head>
<body>
  <h1>Vamp — Voice to App</h1>
  <p>Say your task. Include agent: &quot;use GPT&quot;, &quot;Claude build&quot;, etc.</p>
  <button id="record">Hold to record</button>
  <div id="output"></div>
  <script>
    const API = window.location.origin;
    const rec = document.getElementById('record');
    const out = document.getElementById('output');
    let mediaRecorder, chunks;
    rec.addEventListener('mousedown', start);
    rec.addEventListener('mouseup', stop);
    rec.addEventListener('mouseleave', stop);
    function start() {
      navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        mediaRecorder = new MediaRecorder(stream);
        chunks = [];
        mediaRecorder.ondataavailable = e => e.data.size && chunks.push(e.data);
        mediaRecorder.onstop = send;
        mediaRecorder.start();
        rec.classList.add('recording');
        rec.textContent = 'Recording... release to send';
      }).catch(e => { out.textContent = 'Mic error: ' + e.message; });
    }
    function stop() {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(t => t.stop());
      }
      rec.classList.remove('recording');
      rec.textContent = 'Hold to record';
    }
    async function send() {
      if (!chunks.length) return;
      const blob = new Blob(chunks, { type: 'audio/webm' });
      const fd = new FormData();
      fd.append('audio', blob, 'recording.webm');
      out.textContent = 'Sending...';
      try {
        const r = await fetch(API + '/api/voice', { method: 'POST', body: fd });
        const data = await r.json();
        if (data.error) out.textContent = 'Error: ' + data.error;
        else out.innerHTML = 'Task: ' + data.task + '\nAgent: ' + data.agent + '\n<span class="path">Saved: ' + data.path + '</span>';
      } catch (e) { out.textContent = 'Error: ' + e.message; }
    }
  </script>
</body>
</html>
HTML

echo "[Vamp] Created $APP_DIR/"
echo "[Vamp] Conversation output: $CONV_DIR/"
echo ""
echo "Next steps:"
echo "  1. cd app"
echo "  2. cp .env.example .env"
echo "  3. Edit .env with OPENROUTER_API_KEY (LLM) and OPENAI_API_KEY (Whisper transcription)"
echo "  4. pip install -r requirements.txt"
echo "  5. python app.py"
echo ""
echo "Usage: POST audio to http://localhost:5000/api/voice"
echo "       Or POST JSON {task, agent} to http://localhost:5000/api/generate"
