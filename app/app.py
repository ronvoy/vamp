"""Flask voice-to-app server: transcribe voice -> select agent -> generate script -> execute -> save."""
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, redirect, send_from_directory, url_for
from flask_cors import CORS

from transcriber import transcribe_bytes
from agent_registry import select_agent, extract_task
from code_generator import generate_openai, generate_anthropic, generate_with_model, fetch_models, AGENT_MODELS, DEFAULT_MODEL
from conversation_store import (save_conversation, list_conversations, get_conversation,
    get_git_diff, rename_conversation, delete_conversation,
    detect_runnable, run_project, get_run_output, stop_project, send_input,
    git_reset_to_commit, git_branch_from_commit, run_at_commit, cleanup_temp_run, CONV_DIR)

app = Flask(__name__)
CORS(app)

GENERATORS = {
    "openai": generate_openai,
    "anthropic": generate_anthropic,
}

@app.route("/")
def index():
    return redirect(url_for('static', filename='voice.html'))

@app.route("/api/voice", methods=["POST"])
def handle_voice():
    """Receive audio, transcribe, select agent, generate script, execute, save."""
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

    save_result = save_conversation(
        result["script"], result["folder_name"],
        task, agent,
        reasoning=result.get("reasoning", ""),
        raw_response=result.get("raw_response", ""),
        usage=result.get("usage", {}),
    )
    return jsonify({
        "text": text, "task": task, "agent": agent,
        "path": save_result["path"],
        "folder": save_result["folder"],
        "files": save_result["files"],
        "reasoning": result.get("reasoning", ""),
        "usage": result.get("usage", {}),
        "script_output": save_result.get("script_output", ""),
        "script_success": save_result.get("script_success", False),
    })

@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    """Transcribe only."""
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    audio_bytes = request.files["audio"].read()
    try:
        text = transcribe_bytes(audio_bytes)
    except Exception as e:
        return jsonify({"error": f"Transcription failed: {e}"}), 500
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
    """Get full conversation details with git diffs and history."""
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
    """Generate script from text, execute it, save results."""
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
                    parts.append(f"\n--- {name} ---\n{content}")
            context = "\n".join(parts)

    llm_params = data.get("llm_params")
    selected_model = data.get("model")
    if selected_model:
        try:
            result = generate_with_model(task, selected_model, context=context, params=llm_params)
        except Exception as e:
            return jsonify({"error": f"[model={selected_model}] {e}"}), 500
        agent = selected_model
    else:
        gen = GENERATORS.get(agent, generate_openai)
        model_name = AGENT_MODELS.get(agent, DEFAULT_MODEL)
        try:
            result = gen(task, context=context, params=llm_params)
        except Exception as e:
            return jsonify({"error": f"[model={model_name}] {e}"}), 500

    save_result = save_conversation(
        result["script"], result["folder_name"],
        task, agent,
        reasoning=result.get("reasoning", ""),
        raw_response=result.get("raw_response", ""),
        usage=result.get("usage", {}),
        continue_from=continue_from or "",
    )

    folder = save_result["folder"]
    resp = {
        "path": save_result["path"],
        "folder": folder,
        "files": save_result["files"],
        "reasoning": result.get("reasoning", ""),
        "raw_response": result.get("raw_response", ""),
        "usage": result.get("usage", {}),
        "task": task,
        "agent": agent,
        "is_continuation": bool(continue_from),
        "script_output": save_result.get("script_output", ""),
        "script_success": save_result.get("script_success", False),
    }
    if continue_from:
        resp["git_diff"] = get_git_diff(folder)
    return jsonify(resp)

@app.route("/api/run/<path:folder>/input", methods=["POST"])
def api_send_input(folder):
    """Send stdin input to a running process."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    text = request.json.get("text", "")
    result = send_input(folder, text)
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/run/<path:folder>/output", methods=["GET"])
def api_run_output(folder):
    """Poll console output from a running project."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    offset = request.args.get("offset", 0, type=int)
    return jsonify(get_run_output(folder, offset))

@app.route("/api/run/<path:folder>/stop", methods=["POST"])
def api_stop_project(folder):
    """Stop a running project."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    return jsonify(stop_project(folder))

@app.route("/api/run/<path:folder>/detect", methods=["GET"])
def api_detect_runnable(folder):
    """Detect what can be run in a project folder."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    result = detect_runnable(folder)
    if not result:
        return jsonify({"error": "No runnable file found"}), 404
    return jsonify(result)

@app.route("/api/run/<path:folder>/at/<commit_hash>", methods=["POST"])
def api_run_at_commit(folder, commit_hash):
    """Run a project at a specific commit using a temp directory."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    result = run_at_commit(folder, commit_hash)
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/run/cleanup/<path:temp_key>", methods=["POST"])
def api_cleanup_temp(temp_key):
    """Stop and clean up a temp-branch run."""
    if ".." in temp_key:
        return jsonify({"error": "Invalid key"}), 400
    return jsonify(cleanup_temp_run(temp_key))

@app.route("/api/run/<path:folder>", methods=["POST"])
def api_run_project(folder):
    """Start running a generated project."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    result = run_project(folder)
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/conversation/<path:folder>/reset", methods=["POST"])
def api_git_reset(folder):
    """Reset a project to a specific commit."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    data = request.json or {}
    commit_hash = data.get("hash", "")
    mode = data.get("mode", "soft")
    result = git_reset_to_commit(folder, commit_hash, mode)
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/conversation/<path:folder>/branch", methods=["POST"])
def api_git_branch(folder):
    """Create a branch copy of a project at a specific commit."""
    if ".." in folder:
        return jsonify({"error": "Invalid folder"}), 400
    data = request.json or {}
    commit_hash = data.get("hash", "")
    result = git_branch_from_commit(folder, commit_hash)
    if result.get("error"):
        return jsonify(result), 400
    return jsonify(result)

@app.route("/conversation/<path:filepath>")
def serve_conversation_file(filepath):
    """Serve static files from conversation folders (for HTML previews)."""
    if ".." in filepath:
        return jsonify({"error": "Invalid path"}), 400
    return send_from_directory(CONV_DIR, filepath)

application = app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
