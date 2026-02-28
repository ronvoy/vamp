"""Flask voice-to-app server: transcribe voice -> select agent -> generate code -> save."""
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, redirect
from flask_cors import CORS

from transcriber import transcribe_bytes
from agent_registry import select_agent, extract_task
from code_generator import generate_openai, generate_anthropic, generate_with_model, fetch_models
from conversation_store import save_conversation, list_conversations, get_conversation, rename_conversation, delete_conversation

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
        result = gen(task)
    except Exception as e:
        return jsonify({"error": str(e), "text": text}), 500

    path = save_conversation(
        result["files"], result["folder_name"],
        task, agent,
        reasoning=result.get("reasoning", ""),
        raw_response=result.get("raw_response", ""),
        usage=result.get("usage", {}),
    )
    folder = os.path.basename(path)
    file_list = list(result.get("files", {}).keys()) or ["main.py", "requirements.txt", "README.md"]
    return jsonify({
        "text": text, "task": task, "agent": agent,
        "path": path, "folder": folder,
        "files": file_list,
        "reasoning": result.get("reasoning", ""),
        "usage": result.get("usage", {}),
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

@app.route("/api/models", methods=["GET"])
def api_models():
    """Return all available OpenRouter models with pricing."""
    return jsonify(fetch_models())

@app.route("/api/history", methods=["GET"])
def api_history():
    """List all past conversation sessions."""
    return jsonify(list_conversations())

@app.route("/api/conversation/<path:folder>", methods=["GET"])
def api_get_conversation(folder):
    """Get full conversation details."""
    data = get_conversation(folder)
    if data is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(data)

@app.route("/api/conversation/<path:folder>/rename", methods=["PUT"])
def api_rename_conversation(folder):
    """Rename conversation folder."""
    data = request.get_json() or {}
    new_name = data.get("name", "").strip()
    if not new_name:
        return jsonify({"error": "Name required"}), 400
    result = rename_conversation(folder, new_name)
    if result is None:
        return jsonify({"error": "Rename failed"}), 400
    return jsonify({"folder": result})

@app.route("/api/conversation/<path:folder>", methods=["DELETE"])
def api_delete_conversation(folder):
    """Delete conversation folder."""
    if delete_conversation(folder):
        return jsonify({"ok": True})
    return jsonify({"error": "Delete failed"}), 400

@app.route("/api/generate", methods=["POST"])
def api_generate():
    """Generate from text (no audio). Optional continue_from=folder for context."""
    data = request.get_json() or {}
    task = data.get("task") or data.get("text", "")
    agent = data.get("agent") or select_agent(task)
    continue_from = data.get("continue_from")
    if not task:
        return jsonify({"error": "No task"}), 400
    context = None
    if continue_from:
        conv = get_conversation(continue_from)
        if conv:
            meta = conv.get("metadata", {})
            files = conv.get("files", {})
            parts = [f"Previous task: {meta.get('task', '')}"]
            for name, content in files.items():
                if content and "(binary" not in str(content):
                    parts.append(f"\n{name}:\n```\n{content}\n```")
            context = "\n".join(parts)
    selected_model = data.get("model")
    if selected_model:
        try:
            result = generate_with_model(task, selected_model, context=context)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        agent = selected_model
    else:
        gen = GENERATORS.get(agent, generate_openai)
        try:
            result = gen(task, context=context)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    path = save_conversation(
        result["files"], result["folder_name"],
        task, agent,
        reasoning=result.get("reasoning", ""),
        raw_response=result.get("raw_response", ""),
        usage=result.get("usage", {}),
    )
    folder = os.path.basename(path)
    file_list = list(result.get("files", {}).keys()) or ["main.py", "requirements.txt", "README.md"]
    return jsonify({
        "path": path, "folder": folder,
        "files": file_list,
        "reasoning": result.get("reasoning", ""),
        "raw_response": result.get("raw_response", ""),
        "usage": result.get("usage", {}),
        "task": task, "agent": agent,
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
