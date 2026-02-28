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
