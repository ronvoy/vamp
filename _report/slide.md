# VAMP — Voice AI Multimodal Prompter

## Presentation Slide Notes

---

### Slide 1: Title

**Title:** VAMP — Voice AI Multimodal Prompter  
**Subtitle:** A Voice-Driven Code Generation System  
**Description:** VAMP takes spoken commands and turns them into runnable software projects. It handles transcription, LLM agent selection, code generation, script execution, and git-based versioning — all from a browser interface.

---

### Slide 2: Problem Statement

**Title:** The Problem  
**Description:** Setting up a new project is tedious. You create folders, write boilerplate, configure dependencies, add docs — all before writing real logic. VAMP skips that: say what you want to build, and get a complete project back in seconds.

---

### Slide 3: System Architecture

**Title:** System Architecture  
**Description:** Four layers: **Presentation** (browser SPA for recording, editing, model picking, displaying results), **Application** (Flask server handling REST routes), **Service** (transcription, agent routing, code generation — three separate modules), **Persistence** (file storage, JSON metadata, git). All LLM calls go through OpenRouter, so one API key covers 80+ models.

![System Architecture](diagrams/architecture.png)

---

### Slide 4: Process Workflow

**Title:** Workflow  
**Description:** Four phases. **Phase 1:** Browser records audio (WebM), server converts to WAV, sends to Gemini Flash for transcription. **Phase 2:** Agent registry scans for keywords ("GPT", "Claude") to pick a model, strips them from the task text. **Phase 3:** Task + system prompt go to the selected LLM, which returns a bash `setup.sh` that creates all project files via heredocs. The response is parsed with regex. **Phase 4:** Script runs in a subprocess (60-second timeout), files are cataloged in JSON metadata, everything is committed to git.

![Process Workflow](diagrams/workflow.png)

---

### Slide 5: Sequence Diagram

**Title:** Message Flow  
**Description:** Shows how a request moves through the system: browser → Flask → transcriber → agent registry → code generator → OpenRouter API → conversation store → git → back to the browser as JSON. Each component handles one step and passes its output to the next.

![Sequence Diagram](diagrams/sequence.png)

---

### Slide 6: Transcription Module

**Title:** Voice-to-Text  
**Description:** Audio from the browser (WebM) gets converted to WAV via pydub/ffmpeg, Base64-encoded, and sent as an `input_audio` block in a chat completion request to Gemini 2.5 Flash. The prompt just says "transcribe this." Using a multimodal LLM instead of a separate speech API means transcription and code generation both go through the same OpenRouter endpoint. If WAV conversion fails, raw bytes are sent as a fallback.

---

### Slide 7: Agent Registry

**Title:** Agent Selection  
**Description:** `select_agent()` does a case-insensitive keyword scan — "gpt" or "openai" → GPT-4o-mini, "claude" or "anthropic" → Claude 3.5 Haiku. `extract_task()` strips those keywords out with regex so the LLM gets a clean task. Default agent kicks in when no keywords match. Users can also just pick a model from the UI dropdown, which skips keyword routing entirely.

---

### Slide 8: Code Generation

**Title:** Code Generation  
**Description:** The system prompt tells the LLM to produce a single `setup.sh` bash script that creates all files using heredocs (single-quoted EOF to avoid shell expansion). Includes a language table (iOS → Swift, web → HTML/CSS/JS, etc.) and requires a README and a `FOLDER_NAME:` directive. Response parsing: regex grabs the first bash code block as the script, text before it as reasoning, and the folder name. If no code block is found, the raw output is saved in a diagnostic script. For follow-ups, the previous project's files are included as context.

---

### Slide 9: Conversation Store

**Title:** Project Storage & Git  
**Description:** Projects go into `conversation/YYYY-MM-DD_HHmm_<name>/`. Folder names: lowercase alphanumeric + hyphens, max 50 chars. The script runs via `subprocess.run()` with a 60-second timeout. After execution, a `metadata.json` is written with the task, model, files, reasoning, token usage, stdout/stderr, and iteration history. Everything gets committed to a git repo in the `conversation/` directory. Continuations update the existing folder and add a new commit. Delete and rename operations also trigger git commits and include path traversal checks.

---

### Slide 10: Web Interface

**Title:** Frontend  
**Description:** One HTML file (~1,500 lines), vanilla JS/CSS, no build step. Hold-to-record button with visual feedback. Editable transcript textarea for fixing errors before generating. Searchable model dropdown showing names, context sizes, and per-token pricing. History sidebar with search, rename, delete. Result view with file contents, git diffs, execution output, and reasoning. Dark/light theme saved to localStorage. GSAP for animations.

---

### Slide 11: Technology Stack

**Title:** Stack  
**Description:** **Python 3.10+** / **Flask** backend. **Vanilla HTML/CSS/JS** + **GSAP** frontend. **OpenRouter** as the single LLM gateway — handles both transcription (Gemini 2.5 Flash) and code generation (Gemma 3 27B default, 80+ models available). **pydub** + **ffmpeg** for audio conversion. **Git** via subprocess for versioning. **python-dotenv** for config.

---

### Slide 12: Design Decisions

**Title:** Design Decisions  
**Description:** **One API key** — OpenRouter handles all models, no per-provider setup. **Bash heredocs** — one script creates any project regardless of language. **Git over custom versioning** — free diffs, history, rollback. **Files over a database** — just folders and JSON, no infrastructure. **Single HTML file** — no build tools, no npm, just drop it in. **60-second timeout** — prevents scripts from running forever. **Keyword routing** — say "use GPT" and you get GPT, simple as that.

---

### Slide 13: Security

**Title:** Security  
**Description:** API keys in `.env`, excluded from git. Scripts run in subprocesses with captured output and a timeout. Folder names validated against path traversal. Names sanitized to `[a-z0-9-]`, max 50 chars. No database means no SQL injection. CORS is open for dev, would be restricted in production.

---

### Slide 14: Docker

**Title:** Docker Deployment  
**Description:** Published to Docker Hub as `ronvoy/vamp:latest` (~256 MB). Built on `python:3.10-slim` with ffmpeg and git. Requirements are installed in a separate layer so they're cached across rebuilds. No secrets in the image — API key and config passed as env vars at runtime. The `conversation/` directory should be mounted as a volume so projects survive restarts.

```bash
docker pull ronvoy/vamp:latest
```

```bash
docker run -d -p 5000:5000 \
  -e OPENROUTER_API_KEY=your_key \
  -v ./conversation:/vamp/conversation \
  ronvoy/vamp:latest
```

---

### Slide 15: Conclusion

**Title:** Conclusion  
**Description:** VAMP shows that a voice-to-code pipeline works with current multimodal LLMs and basic web tech. Each module does one thing and can be swapped out. Git handles versioning. Docker handles deployment. **Next steps:** streaming responses, multi-turn conversations, auto-testing generated code, sandboxed execution, multi-user support.
