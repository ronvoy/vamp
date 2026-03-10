# VAMP — Voice AI Multimodal Prompter

## Presentation Slide Notes

---

### Slide 1: Title

**Title:** VAMP — Voice AI Multimodal Prompter  
**Subtitle:** A Voice-Driven AI Code Generation System  
**Description:** VAMP is an AI system engineering project that transforms spoken natural language into fully scaffolded, executable software projects. It integrates multimodal speech recognition, intelligent LLM orchestration, structured code generation, automated script execution, and git-based version control into a unified pipeline accessible through a browser-based interface.

---

### Slide 2: Problem Statement

**Title:** The Problem  
**Description:** Software project initialization is a repetitive, time-consuming process. Developers must create directory structures, write boilerplate code, configure dependencies, and produce documentation — often before writing any meaningful logic. This manual scaffolding introduces context-switching overhead and delays the start of productive work. VAMP addresses this by allowing developers to describe what they want to build using their voice, and receiving a complete, runnable project in seconds. The system abstracts away the scaffolding process entirely, letting the developer focus on intent rather than setup.

---

### Slide 3: System Architecture

**Title:** System Architecture — Layered Design  
**Description:** VAMP employs a four-tier layered architecture with strict separation of concerns. The **Presentation Layer** is a browser-based single-page application that handles audio capture, text editing, model selection, and result rendering. The **Application Layer** is a Flask HTTP server that provides RESTful routing and orchestrates requests across service modules. The **Service Layer** contains three specialized modules: a transcription engine for voice-to-text, an agent registry for intelligent LLM routing, and a code generator for structured prompting and response parsing. The **Persistence Layer** manages timestamped project folders, JSON metadata, and automated git version control. All LLM interactions flow through a single OpenRouter API gateway, providing unified access to over 80 models from multiple providers.

![System Architecture](diagrams/architecture.png)

---

### Slide 4: Process Workflow

**Title:** End-to-End Process Workflow  
**Description:** The system operates in four sequential phases. In **Phase 1**, the browser captures audio via the MediaRecorder API and transmits it to the server, where it is converted from WebM to WAV format and sent to Google Gemini Flash for multimodal transcription. In **Phase 2**, the transcript is analyzed for provider-specific keywords (such as "GPT" or "Claude") to determine which LLM agent to use, while routing keywords are stripped to produce a clean task description. In **Phase 3**, the task is combined with a carefully engineered system prompt and sent to the selected LLM, which generates a self-contained bash script that creates all project files using heredoc syntax. In **Phase 4**, the script is saved to a timestamped folder, executed in an isolated subprocess with a 60-second safety timeout, and the result — including all generated files, execution output, and metadata — is committed to a local git repository.

![Process Workflow](diagrams/workflow.png)

---

### Slide 5: Sequence Diagram

**Title:** Inter-Component Message Flow  
**Description:** The sequence diagram illustrates the precise message exchange between all system participants across the four operational phases. It shows how audio flows from the browser to the Flask server, is delegated to the transcription module, and returns as text. The agent registry then classifies and cleans the input before the code generator constructs a system prompt, queries the LLM via OpenRouter, and parses the structured response. The conversation store handles file creation, script execution, metadata persistence, and git operations before the final JSON response is assembled and rendered in the browser. The diagram highlights the system's clean request-response pattern and the activation boundaries of each component.

![Sequence Diagram](diagrams/sequence.png)

---

### Slide 6: Transcription Module

**Title:** Voice-to-Text via Multimodal LLM  
**Description:** The transcription module converts browser-recorded audio into text using a multimodal large language model rather than a dedicated speech-to-text service. Audio captured by the MediaRecorder API in WebM format is first converted to WAV using the pydub library (backed by ffmpeg), then Base64-encoded and sent as an `input_audio` content block within an OpenAI-compatible chat completion request. The model (Google Gemini 2.5 Flash by default) receives both a text instruction and the audio data, enabling it to leverage native audio understanding. This design choice keeps the system's external dependencies to a single API gateway — the same OpenRouter endpoint used for code generation also handles transcription.

---

### Slide 7: Agent Registry and Routing

**Title:** Intelligent Agent Selection  
**Description:** The agent registry implements a two-stage routing mechanism. First, `select_agent()` performs a case-insensitive keyword scan of the transcript against a configurable dictionary of trigger words — for example, "GPT," "OpenAI," and "ChatGPT" all route to the GPT-4o-mini model, while "Claude" routes to Claude 3.5 Haiku. Second, `extract_task()` removes all detected keywords using word-boundary-aware regular expressions, producing a clean task description free of routing metadata. This keyword-based approach was chosen for its deterministic, transparent behavior — users always know which model they will get based on what they say. Additionally, the web interface provides a searchable model dropdown that bypasses keyword routing entirely, allowing direct selection from over 80 available models with real-time pricing information.

---

### Slide 8: Code Generation Strategy

**Title:** Structured Prompting and Response Parsing  
**Description:** The code generator is the core intelligence module. It uses a carefully engineered system prompt that instructs the LLM to produce a single bash `setup.sh` script using heredoc file creation syntax. The prompt includes platform-specific language matching rules (iOS generates Swift, Android generates Kotlin, web requests generate HTML/CSS/JS), documentation requirements (every project must include a README), and a `FOLDER_NAME:` directive for automated naming. The response parser extracts the first fenced bash code block via regex, captures preceding text as reasoning, and extracts the folder name. A fallback mechanism ensures the system never silently fails — if no code block is found, the raw response is preserved in a diagnostic script. For continuation requests, the generator prefixes the prompt with the previous project's file contents as context, enabling incremental updates.

---

### Slide 9: Conversation Store and Persistence

**Title:** Git-Integrated Project Lifecycle Management  
**Description:** The conversation store manages the full lifecycle of generated projects. Each project is created in a timestamped folder (`YYYY-MM-DD_HHmm_<name>`) with sanitized naming that strips all characters except lowercase alphanumerics and hyphens. The generated bash script is written to disk and executed via `subprocess.run()` with a 60-second timeout — a critical safety boundary for LLM-generated code. After execution, a comprehensive JSON metadata file is created containing the task, agent, timestamp, file list, reasoning, raw response, token usage, execution output, success status, and an iteration history array. The entire folder is then committed to a local git repository with the agent name and task summary as the commit message. This git integration provides file-level diffs between iterations, a complete commit timeline, and rollback capability — all without custom versioning code.

---

### Slide 10: Web Interface

**Title:** Browser-Based Single-Page Application  
**Description:** The frontend is a single HTML file (approximately 1,500 lines of vanilla JavaScript, CSS, and HTML) served directly by Flask with zero build toolchain. It provides hold-to-record voice capture with visual feedback, an editable transcript preview for human-in-the-loop refinement, a searchable model selector with per-token pricing display, a history sidebar with search, rename, and delete capabilities, and structured result rendering with file listings, git diffs, execution logs, and LLM reasoning. The interface supports dark and light themes (persisted in localStorage) and uses the GSAP animation library for smooth transitions. The no-framework approach was chosen to eliminate build complexity and enable instant deployment.

---

### Slide 11: Technology Stack

**Title:** Technology Stack  
**Description:** The backend runs on **Python 3.10+** with **Flask** as the HTTP framework. The frontend is **vanilla HTML/CSS/JS** with **GSAP** for animations. All LLM interactions — both transcription and code generation — route through the **OpenRouter API**, providing unified access to models from OpenAI, Anthropic, Google, and others via a single API key. Voice transcription uses **Google Gemini 2.5 Flash** for its multimodal audio understanding. Code generation defaults to **Gemma 3 27B** but supports any of the 80+ available models. Audio format conversion is handled by **pydub** with **ffmpeg**. Project versioning uses **Git** invoked via subprocess. Configuration is managed through **python-dotenv** for secure API key handling.

---

### Slide 12: Design Decisions

**Title:** Key Design Decisions and Trade-offs  
**Description:** Several deliberate architectural choices define the system. **Single API gateway:** OpenRouter eliminates per-provider key management and enables instant model switching. **Bash heredocs as output format:** A universal, language-agnostic, self-contained script that works identically for Python, Swift, TypeScript, or any language. **File system over database:** JSON metadata with git history provides sufficient persistence with zero infrastructure overhead. **Vanilla JS frontend:** No build step, no framework lock-in, single-file deployment. **60-second execution timeout:** A necessary safety boundary for running LLM-generated code. **Keyword-based routing:** Deterministic and transparent — users always know which model they will get based on explicit voice commands.

---

### Slide 13: Security Considerations

**Title:** Security and Safety Measures  
**Description:** The system addresses multiple security concerns. API keys are stored in `.env` files excluded from version control and loaded at runtime. Generated scripts execute in isolated subprocesses with captured output streams and strict timeouts, preventing both information leakage and resource exhaustion. Path traversal is prevented by validating all folder inputs against directory traversal characters before file system access. Folder names are sanitized to lowercase alphanumerics and hyphens with a 50-character limit. The absence of a database eliminates SQL injection entirely. CORS is configured for development and would be restricted in production.

---

### Slide 14: Docker Containerization

**Title:** Docker Containerization and Deployment  
**Description:** VAMP is fully containerized and published to Docker Hub at `ronvoy/vamp:latest` (~256 MB). The Docker image is built on `python:3.10-slim` and packages all runtime dependencies — ffmpeg for audio conversion, git for version control, and all Python packages — into a single portable artifact. The Dockerfile is optimized for layer caching: requirements are installed before application code is copied, so dependency layers are reused across builds unless `requirements.txt` changes. Sensitive configuration (API keys) is never baked into the image; instead, all settings are passed at runtime via environment variables following the twelve-factor app methodology. The `conversation/` directory is designed to be mounted as an external volume, ensuring generated projects persist across container restarts and upgrades. Deployment requires only two commands:

```bash
docker pull ronvoy/vamp:latest
```

```bash
docker run -d -p 5000:5000 \
  -e OPENROUTER_API_KEY=your_key \
  -v ./conversation:/vamp/conversation \
  ronvoy/vamp:latest
```

The `.dockerignore` file excludes `.git/`, `.env`, `conversation/`, `_report/`, `__pycache__/`, and virtual environments from the build context to minimize image size and prevent sensitive data leakage.

---

### Slide 15: Conclusion and Future Work

**Title:** Conclusion and Future Directions  
**Description:** VAMP demonstrates that a complete voice-to-code pipeline is feasible using current multimodal LLM capabilities, structured prompting techniques, and lightweight web technologies. The system cleanly separates transcription, routing, generation, and persistence into independent, replaceable modules. Git-based versioning provides iteration tracking without custom infrastructure. Docker containerization enables portable, reproducible deployment with a single command. The prototype validates voice as a viable input modality for AI-assisted software engineering. **Future work** includes streaming LLM responses for real-time generation feedback, multi-turn conversational project refinement, automated testing of generated code, container-based execution sandboxing for stronger isolation, and collaborative multi-user sharing through a shared git remote.
