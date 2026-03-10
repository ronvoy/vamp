# VAMP — Voice AI Multimodal Prompter

## Technical Report

**Course:** AI System Engineering  
**Date:** March 10, 2026  
**Project:** VAMP — A Voice-Driven AI Code Generation System  

---

## 1. Executive Summary

VAMP (Voice AI Multimodal Prompter) is a full-stack AI system that transforms natural language voice commands into fully scaffolded, executable software projects. The system captures audio directly in the browser, transcribes it through a multimodal large language model, intelligently routes the request to an appropriate AI agent, generates a complete project setup script, executes it in an isolated subprocess, and persists the result with full git version history. The entire pipeline is orchestrated through a lightweight Flask backend and accessed via a responsive single-page web interface, requiring no database or external infrastructure beyond an API key.

---

## 2. System Architecture

### 2.1 Architecture Overview

![System Architecture](diagrams/architecture.png)

VAMP follows a **layered architecture** with four distinct tiers, each with clearly defined responsibilities and clean interfaces between them:

| Layer | Components | Responsibility |
|-------|-----------|----------------|
| **Presentation** | Browser-based Single Page Application | Audio capture via Web APIs, real-time text editing, interactive model selection with pricing, result rendering with diff visualization |
| **Application** | Flask HTTP Server | RESTful API routing, request validation, cross-module orchestration, JSON response assembly |
| **Service** | Transcription, Agent Registry, Code Generation modules | Voice-to-text conversion, intelligent agent routing, structured LLM prompting and response parsing |
| **Persistence** | Conversation Store, File System, Git | Timestamped project storage, JSON metadata management, automated version control |

The architecture deliberately avoids tight coupling between layers. The presentation layer communicates exclusively through REST API calls, the service layer modules are independently testable, and the persistence layer operates through a single entry point that handles all file system and git operations.

### 2.2 External Dependencies

| Dependency | Version | Purpose |
|-----------|---------|---------|
| Flask | >= 3.0.0 | Lightweight WSGI HTTP server framework providing routing, request parsing, and static file serving |
| Flask-CORS | >= 4.0.0 | Cross-origin resource sharing middleware enabling browser-to-server communication during development |
| OpenAI (Python SDK) | >= 1.6.0 | OpenAI-compatible client library used to communicate with OpenRouter's unified API endpoint |
| python-dotenv | >= 1.0.0 | Environment variable loader that reads configuration from `.env` files at startup |
| pydub | >= 0.25.1 | Audio format conversion library that transforms browser-recorded WebM/OGG audio into WAV format |
| requests | >= 2.31.0 | HTTP client used for fetching the complete model catalog from the OpenRouter API |

---

## 3. Process Workflow

### 3.1 End-to-End Workflow Diagram

![Process Workflow](diagrams/workflow.png)

The workflow diagram above illustrates the complete data flow from voice input to rendered output. Each subgraph represents a distinct processing stage with its own module boundary. The system is designed so that each stage produces a well-defined output that feeds directly into the next stage, with no back-channel dependencies.

### 3.2 Detailed Sequence Diagram

![Sequence Diagram](diagrams/sequence.png)

The sequence diagram captures the precise inter-component message flow, including asynchronous API calls to external services, activation and deactivation bars for each participant, and the four distinct operational phases. It demonstrates how the system maintains a clean request-response pattern throughout the pipeline.

### 3.3 Workflow Phases

The application operates in **four distinct phases**, each managed by dedicated backend modules:

| Phase | Name | Description |
|-------|------|-------------|
| 1 | **Voice Recording and Transcription** | The browser's MediaRecorder API captures audio in WebM format. The audio blob is transmitted to the server, where it undergoes format conversion from WebM to WAV using the pydub library, followed by Base64 encoding. The encoded audio is then sent to a multimodal LLM capable of native audio understanding, which returns a plain text transcript. The transcript is presented to the user in an editable preview area. |
| 2 | **Agent Selection and Task Extraction** | The transcript text is analyzed by the agent registry module, which scans for predefined keywords to determine which LLM provider the user intends to use. Simultaneously, the module strips these routing keywords from the text to produce a clean task description. If no keywords are detected, the system falls back to a configurable default agent. The user may also manually override the model selection through the UI dropdown. |
| 3 | **Code Generation** | The cleaned task is combined with a carefully engineered system prompt that instructs the LLM to produce a self-contained bash script. The system prompt specifies the output format, language-matching rules for the target platform, and documentation requirements. The LLM's response is parsed using regex to extract the bash script, a folder name directive, and the model's reasoning. Token usage statistics are captured for cost tracking. |
| 4 | **Persistence and Execution** | A timestamped project folder is created following a consistent naming convention. The generated bash script is written to disk and executed in a subprocess with a 60-second safety timeout. All generated files are cataloged, comprehensive metadata is saved as JSON, and the entire folder is committed to a local git repository. If the request is a continuation of a previous project, the existing folder is updated and a new commit is appended to its history. |

---

## 4. Component Detail

### 4.1 Transcription Module

The transcription module serves as the entry point for voice input processing. It receives raw audio bytes from the browser's MediaRecorder API, which typically produces WebM or OGG encoded streams. Since the target LLM requires WAV format for audio understanding, the module first performs format conversion using the pydub library's `AudioSegment` class, which internally leverages ffmpeg for codec handling. The converted WAV bytes are then Base64-encoded and packaged into a multimodal chat completion request.

The transcription request is structured as a multi-part message containing both a text instruction and the audio data as an `input_audio` content block. This approach leverages the model's native audio understanding capabilities rather than relying on a separate speech-to-text API, keeping the system's external dependency count to a single API gateway. The transcription prompt is deliberately minimal — it instructs the model to transcribe the audio exactly and output only the transcribed text — ensuring clean output without hallucinated additions.

The transcription model is configurable through an environment variable, defaulting to Google's Gemini 2.5 Flash. This model was chosen for its strong multimodal performance, low latency, and cost efficiency. The module includes graceful error handling: if the audio format conversion fails (for example, due to a missing ffmpeg installation), it falls back to passing the raw bytes directly to the API.

| Attribute | Detail |
|-----------|--------|
| Default Model | Google Gemini 2.5 Flash |
| Input Formats | WebM, OGG (auto-detected and converted to WAV) |
| Output | Clean plain text transcript |
| API Protocol | OpenAI-compatible chat completions with multimodal content |
| Error Handling | Graceful fallback if audio format conversion fails |

### 4.2 Agent Registry

The agent registry module implements a lightweight, keyword-driven routing mechanism that determines which LLM should handle the code generation task. It operates in two distinct stages.

**Stage 1 — Agent Selection:** The `select_agent()` function performs a case-insensitive scan of the transcript for provider-specific keywords. The keyword-to-agent mapping is stored in a dictionary structure where each agent has a list of trigger words. For example, the words "gpt," "openai," and "chatgpt" all route to the OpenAI agent, while "claude" and "anthropic" route to the Anthropic agent. If no keywords match, the function returns a configurable default (set via environment variable).

**Stage 2 — Task Extraction:** The `extract_task()` function uses compiled regular expressions with word boundary matching to remove all routing keywords from the transcript. This ensures the LLM receives a clean task description without provider names polluting the prompt. Whitespace normalization is applied after keyword removal to produce a properly formatted string.

This keyword-based approach was chosen over more complex NLP-based routing because it provides predictable, transparent behavior that users can control through explicit voice commands. The web interface additionally provides a manual model selector that bypasses keyword routing entirely, giving users full control.

| Agent ID | Trigger Keywords | Routed Model | Use Case |
|----------|-----------------|--------------|----------|
| openai | gpt, openai, chatgpt | GPT-4o-mini | General-purpose code generation with strong instruction following |
| anthropic | claude, anthropic | Claude 3.5 Haiku | Code generation with detailed reasoning and safety awareness |
| (custom) | N/A (manual selection) | Any OpenRouter model | Experimentation with specialized or open-source models |

### 4.3 Code Generator

The code generator is the core intelligence module of the system. It constructs a structured conversation between a system prompt and the user's task, then sends it to the selected LLM via OpenRouter's OpenAI-compatible API.

**System Prompt Engineering:** The system prompt is the most critical design element in the pipeline. It instructs the LLM to behave as an expert coding agent that produces a single self-contained bash script called `setup.sh`. The prompt specifies precise formatting rules: all files must be created using heredocs with single-quoted EOF delimiters to prevent shell variable expansion. It includes a comprehensive language-matching table so the LLM selects appropriate file extensions and frameworks based on the user's platform target — for instance, requests mentioning iOS produce Swift files, Android requests produce Kotlin, and web requests produce HTML/CSS/JS. The prompt mandates that every project includes a README with build instructions, and terminates with a `FOLDER_NAME:` directive in kebab-case for automated folder naming.

**Response Parsing:** The `_parse_response()` function implements a multi-stage extraction pipeline. First, it uses a regex pattern to locate the first fenced code block tagged as bash, sh, or shell — the content of this block becomes the setup script. Text preceding the code block is captured as the model's reasoning. A separate regex scan extracts the `FOLDER_NAME:` directive. If no code block is found (indicating the model failed to follow the expected format), the entire response is wrapped in a diagnostic error script that preserves the raw output for debugging. This fallback ensures the system never silently fails — there is always a traceable output.

**Continuation Context:** When a user continues from a previous project, the generator prefixes the task with the previous project's files and metadata as context. This allows the LLM to understand the existing codebase and produce incremental updates rather than starting from scratch.

**Model Catalog and Caching:** The module provides a `fetch_models()` function that retrieves the complete list of available models from OpenRouter's API. This catalog is cached in memory with a one-hour TTL to avoid redundant network calls. The cached data includes model identifiers, display names, context window sizes, and per-token pricing for both prompt and completion tokens — all rendered in the UI's model selector dropdown.

| Attribute | Detail |
|-----------|--------|
| API Gateway | OpenRouter (openrouter.ai/api/v1) |
| Default Model | Google Gemma 3 27B Instruct |
| Max Output Tokens | 8,192 per generation request |
| Model Catalog Cache | In-memory with 3,600-second TTL |
| Supported Platforms | iOS/Swift, Android/Kotlin, Web/HTML/CSS/JS, Python, Go, Rust, TypeScript/React, Java |
| Output Format | Bash setup.sh with heredoc file creation, folder name directive, reasoning text |

### 4.4 Conversation Store

The conversation store module manages the complete lifecycle of generated projects — from initial creation through iterative updates to eventual deletion. It unifies file system operations, script execution, metadata management, and git version control behind a clean functional API.

**Project Creation:** When a new project is generated, the module creates a timestamped folder under the `conversation/` directory following the format `YYYY-MM-DD_HHmm_<kebab-case-name>`. The folder name is sanitized through a dedicated function that strips all characters except lowercase alphanumerics and hyphens, with a 50-character length limit to prevent excessively long paths. The generated bash script is written as `setup.sh` and executed via Python's `subprocess.run()` with a strict 60-second timeout. This timeout serves as a critical safety boundary — since the scripts are LLM-generated and could theoretically contain infinite loops or resource-intensive operations, the timeout prevents runaway processes from consuming system resources.

**Metadata Tracking:** After script execution, the module catalogs all generated files (excluding internal metadata) and writes a comprehensive JSON metadata document. This document captures the original task description, the agent or model used, an ISO 8601 creation timestamp, the complete file list, the LLM's reasoning text, the full raw response, token usage statistics (prompt tokens, completion tokens, total tokens), script execution output (both stdout and stderr), the execution success status, and a history array that tracks every iteration of the project.

**Git Integration:** The module initializes and maintains a git repository within the `conversation/` directory. Every project creation or update triggers an automatic staging of all changes followed by a commit. The commit message is constructed from the agent name and a summary derived from the LLM's reasoning — specifically, the first line of reasoning with common filler phrases stripped. The git author is set to "vamp" to distinguish automated commits from manual ones. This integration enables the UI to display file-level diffs between iterations and a complete commit timeline for each project, providing a built-in audit trail that would otherwise require significant custom development.

**Continuation Support:** When a user requests to continue from a previous project, the module loads the existing project's files and metadata as context for the next LLM call. The updated script overwrites the existing `setup.sh`, is re-executed, and a new entry is appended to the history array. This creates a chain of iterations within a single project folder, each tracked by a separate git commit with its own diff.

**Deletion and Renaming:** The module supports safe deletion (via `shutil.rmtree()` with a post-deletion git commit) and renaming (preserving the timestamp prefix while replacing the descriptive suffix). Both operations include path traversal validation to prevent malicious folder references.

### 4.5 Web Interface

The presentation layer is implemented as a single HTML file containing embedded CSS and JavaScript — approximately 1,500 lines of vanilla code with no build toolchain required. This architectural choice prioritizes deployment simplicity: the file is served directly by Flask's static file handler with zero compilation or bundling steps.

**Voice Capture:** The interface uses the browser's MediaRecorder API to capture audio when the user holds the record button. Visual feedback is provided through CSS animations and dynamic state transitions. Upon release, the recorded WebM blob is packaged as a multipart form upload and sent to the transcription endpoint. The recording button provides clear affordance with color and text changes to indicate active recording state.

**Transcript Preview and Editing:** After transcription, the result is displayed in an editable text area that allows the user to refine wording, fix transcription errors, or completely rewrite the task before sending it for code generation. This human-in-the-loop step ensures the LLM receives a well-formed prompt even if the voice transcription is imperfect.

**Model Selection:** The UI fetches the complete model catalog from the backend and renders it as a searchable, keyboard-navigable dropdown. Each model entry displays the model name, context window size, and per-token pricing for both prompt and completion usage. Users can filter models in real-time by typing, navigate with arrow keys, and select with Enter. Cost-efficient models are visually highlighted to help users make informed decisions.

**History Management:** A collapsible sidebar lists all previously generated projects, sorted newest-first, with real-time search filtering. Each entry can be clicked to load full project details including all generated file contents, git commit history, and file-level diffs between iterations. Projects can be renamed or permanently deleted directly from the sidebar context actions.

**Result Rendering:** Generated projects are displayed with structured file listings, expandable sections for script execution output, LLM reasoning, and raw response text. Git diff visualizations show exactly what changed between iterations. The interface supports dark and light themes (persisted in localStorage) and uses the GSAP animation library for smooth UI transitions.

### 4.6 REST API

The Flask server exposes nine RESTful endpoints that form the contract between the frontend and backend:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Redirects to the web interface |
| `/api/transcribe` | POST | Accepts audio as multipart form data; returns the transcript with detected agent and cleaned task text |
| `/api/generate` | POST | Accepts a JSON body with task, optional model ID, and optional continuation folder; returns generated project details |
| `/api/voice` | POST | Combined pipeline that performs transcription and generation in a single request |
| `/api/models` | GET | Returns the complete OpenRouter model catalog with pricing information (cached) |
| `/api/history` | GET | Returns a chronologically sorted list of all generated projects with summary metadata |
| `/api/conversation/:folder` | GET | Returns full project details including file contents, git commit log, and file-level diffs |
| `/api/conversation/:folder/rename` | PUT | Renames a project folder while preserving its timestamp prefix |
| `/api/conversation/:folder` | DELETE | Permanently removes a project folder and commits the deletion to git |

All endpoints return JSON responses with consistent error handling. Input validation is performed at the API boundary, including path traversal checks on folder parameters, empty input guards on audio uploads, and model name inclusion in error messages for debugging.

---

## 5. Data Flow Summary

The following table traces a single request through the complete system pipeline, from voice input to visual output:

| Step | Component | Input | Processing | Output |
|------|-----------|-------|-----------|--------|
| 1 | Browser (MediaRecorder) | User's spoken voice | Audio stream capture and WebM encoding | Raw audio blob |
| 2 | Transcriber Module | WebM audio bytes | Format conversion to WAV, Base64 encoding, multimodal LLM inference | Plain text transcript |
| 3 | Agent Registry | Transcript text | Case-insensitive keyword scan, regex-based keyword removal | Agent ID + cleaned task string |
| 4 | Code Generator | Task + selected model | System prompt construction, LLM API call, regex-based response parsing | Bash script + folder name + reasoning + usage stats |
| 5 | Conversation Store | Generated script | Folder creation, subprocess execution with timeout, metadata serialization, git commit | Versioned project folder with all generated files |
| 6 | Browser (SPA) | JSON API response | DOM rendering of files, diffs, output logs, and reasoning | Interactive visual results |

---

## 6. Technology Stack

| Category | Technology | Role in System |
|----------|-----------|---------------|
| **Backend Runtime** | Python 3.10+ | Primary server-side language leveraging type hints and modern syntax |
| **Web Framework** | Flask 3.x | Lightweight HTTP server providing routing, request parsing, and static file serving |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript | Single-page application with no build toolchain; directly served as a static file |
| **UI Animation** | GSAP (loaded via CDN) | Smooth transitions for recording state, panel expansion, and result rendering |
| **AI Gateway** | OpenRouter API | Unified LLM access point supporting 80+ models from multiple providers through a single API key |
| **Transcription Model** | Google Gemini 2.5 Flash | Multimodal model with native audio understanding for voice-to-text conversion |
| **Code Generation Models** | GPT-4o-mini, Claude 3.5 Haiku, Gemma 3 27B, and others | Selectable LLMs for structured code generation via system prompt engineering |
| **Audio Processing** | pydub + ffmpeg | Format conversion from browser-native WebM/OGG to WAV for LLM consumption |
| **Version Control** | Git (via subprocess) | Automated commit tracking for every project generation and update |
| **Configuration** | python-dotenv | Secure environment variable management for API keys and runtime settings |

---

## 7. Project Structure

```
vamp/
├── app/
│   ├── app.py                  # Flask server with REST API endpoints
│   ├── transcriber.py          # Voice-to-text via multimodal LLM
│   ├── agent_registry.py       # Keyword-based agent routing
│   ├── code_generator.py       # Structured LLM prompting and response parsing
│   ├── conversation_store.py   # Project lifecycle management with git integration
│   ├── requirements.txt        # Python package dependencies
│   ├── .env                    # Runtime configuration (not committed)
│   ├── .env.example            # Configuration template with documentation
│   └── static/
│       └── voice.html          # Complete single-page web interface
├── conversation/               # Generated projects directory (git-tracked)
├── Dockerfile                  # Container image definition
├── .dockerignore               # Build context exclusion rules
├── _report/
│   ├── report.md               # This technical report
│   ├── slide.md                # Presentation slide notes
│   └── diagrams/               # Rendered diagram assets (PNG)
└── README.md                   # Project overview and quick start guide
```

---

## 8. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Single OpenRouter API key** | Rather than managing separate API keys for each LLM provider, all models are accessed through OpenRouter's unified gateway. This reduces configuration complexity and enables instant access to 80+ models without additional vendor setup. |
| **Bash heredocs as output format** | The LLM generates a single `setup.sh` script that creates all project files using heredoc syntax. This approach is language-agnostic, self-contained, and immediately executable — the same pipeline produces Python, Swift, TypeScript, PHP, or any other language without format changes. |
| **Git-based version control** | Every project creation or update is automatically committed to a local git repository. This provides change tracking, file-level diffs between iterations, rollback capability, and a complete audit trail — without requiring any custom versioning logic. |
| **File system over database** | Projects are stored as regular files with JSON metadata. This eliminates database infrastructure overhead, makes projects easily browsable and portable, and leverages git for history rather than building custom temporal queries. |
| **Vanilla JavaScript frontend** | The web interface is a single HTML file with no build step, no framework dependencies, and no compilation. This enables instant deployment, trivial debugging, and eliminates an entire category of toolchain complexity. |
| **60-second execution timeout** | Since the generated bash scripts are LLM-produced and could theoretically contain infinite loops or resource-intensive operations, a strict timeout provides a safety boundary that prevents runaway processes. |
| **Keyword-based agent selection** | The routing mechanism uses explicit keyword matching rather than NLP-based intent classification. This provides deterministic, transparent behavior that users can reliably control through their voice commands. |

---

## 9. Security Considerations

| Concern | Mitigation Strategy |
|---------|-------------------|
| **API Key Protection** | Keys are stored in a `.env` file excluded from version control. They are loaded at runtime through python-dotenv rather than being hardcoded in source files. |
| **Generated Script Execution** | Scripts run in an isolated subprocess with captured output streams and a 60-second timeout. This prevents both information leakage and resource exhaustion. |
| **Path Traversal Prevention** | All folder name inputs are validated against directory traversal characters before any file system operations are performed. |
| **Input Sanitization** | Folder names are stripped to lowercase alphanumerics and hyphens only, with a 50-character length limit, preventing injection of special characters into file paths. |
| **CORS Configuration** | Cross-origin sharing is configured for local development. Production deployment would restrict this to specific allowed origins. |
| **No Database Surface** | The absence of a database eliminates SQL injection as an attack vector entirely. All data is stored in flat files with controlled serialization. |

---

## 10. Docker Containerization

### 10.1 Overview

VAMP is fully containerized using Docker, enabling consistent deployment across any environment without manual dependency management. The Docker image packages the Python runtime, Flask application, system-level dependencies (ffmpeg, git), and all Python packages into a single portable artifact published to Docker Hub.

### 10.2 Dockerfile Breakdown

The Dockerfile follows a structured multi-stage approach optimized for layer caching and minimal image size:

| Layer | Instruction | Purpose |
|-------|-------------|----------|
| **Base Image** | `FROM python:3.10-slim` | Minimal Debian-based Python 3.10 runtime (185 MB). The slim variant excludes development headers and documentation, reducing the attack surface and image size. |
| **System Dependencies** | `RUN apt-get install ffmpeg git` | Installs ffmpeg (required by pydub for WebM-to-WAV audio conversion) and git (required by conversation_store.py for automated version control). The `--no-install-recommends` flag and cache cleanup minimize layer size. |
| **Working Directory** | `WORKDIR /vamp` | Sets the project root to `/vamp`, mirroring the local project structure so that relative path resolution in conversation_store.py works correctly. |
| **Python Dependencies** | `COPY requirements.txt` then `RUN pip install` | Copies only the requirements file first, leveraging Docker's layer cache — dependencies are only reinstalled when `requirements.txt` changes, not on every code edit. |
| **Application Code** | `COPY app/ app/` | Copies the complete application source including the Flask server, all service modules, and the static web interface. |
| **Conversation Directory** | `RUN mkdir -p /vamp/conversation` | Pre-creates the project output directory inside the container. This directory is intended to be mounted as an external volume for data persistence. |
| **Port Configuration** | `ENV PORT=5000` and `EXPOSE 5000` | Sets the default server port via environment variable and documents the exposed port for container orchestration tools. |
| **Entrypoint** | `CMD ["python", "app.py"]` | Starts the Flask server using the exec form, ensuring proper signal handling for graceful container shutdown. |

### 10.3 Docker Ignore Configuration

The `.dockerignore` file excludes unnecessary files from the build context to reduce image size and prevent sensitive data from being baked into the image:

| Excluded Pattern | Reason |
|-----------------|--------|
| `.git/` | Version control history is not needed at runtime |
| `.env`, `app/.env` | API keys and secrets must never be embedded in an image |
| `conversation/` | Generated projects are runtime data, mounted as a volume |
| `_report/`, `_rsc/` | Documentation and resource files are not part of the application |
| `__pycache__/`, `*.pyc` | Compiled bytecode is regenerated at runtime |
| `app/.venv/` | Local virtual environment is replaced by container-level packages |

### 10.4 Image Specifications

| Attribute | Value |
|-----------|-------|
| **Base** | `python:3.10-slim` (Debian Trixie) |
| **Final Image Size** | ~256 MB |
| **System Packages** | ffmpeg, git |
| **Python Packages** | Flask, Flask-CORS, OpenAI SDK, pydub, python-dotenv, requests |
| **Exposed Port** | 5000 |
| **Registry** | Docker Hub — `ronvoy/vamp:latest` |

### 10.5 Deployment Commands

**Pull the image from Docker Hub:**

```bash
docker pull ronvoy/vamp:latest
```

**Run with environment variables and persistent storage:**

```bash
docker run -d \
  --name vamp \
  -p 5000:5000 \
  -e OPENROUTER_API_KEY=your_api_key_here \
  -e TRANSCRIBE_MODEL=google/gemini-2.5-flash \
  -e DEFAULT_AGENT=openai \
  -v ./conversation:/vamp/conversation \
  ronvoy/vamp:latest
```

**Build locally from source:**

```bash
docker build -t vamp .
```

**Run the locally built image:**

```bash
docker run -d \
  --name vamp \
  -p 5000:5000 \
  -e OPENROUTER_API_KEY=your_api_key_here \
  -v ./conversation:/vamp/conversation \
  vamp
```

**View container logs:**

```bash
docker logs -f vamp
```

**Stop and remove the container:**

```bash
docker stop vamp && docker rm vamp
```

### 10.6 Environment Variables

All configuration is passed at runtime through environment variables, following the twelve-factor app methodology. No secrets are baked into the image.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | — | API key for accessing OpenRouter's LLM gateway |
| `TRANSCRIBE_MODEL` | No | `google/gemini-2.5-flash` | Model used for voice-to-text transcription |
| `DEFAULT_AGENT` | No | `openai` | Fallback LLM agent when no keyword is detected |
| `PORT` | No | `5000` | HTTP server listening port |

### 10.7 Volume Mounts

The `conversation/` directory stores all generated projects and their git history. Mounting this as a Docker volume ensures data persists across container restarts, upgrades, and redeployments:

```bash
-v /path/on/host/conversation:/vamp/conversation
```

Without this mount, all generated projects are lost when the container is removed.

---

## 11. Conclusion

VAMP demonstrates a practical AI system engineering pipeline that bridges the gap between natural language voice input and executable software output. The architecture cleanly separates concerns across transcription, routing, generation, and persistence layers, while maintaining simplicity through file-based storage and a single external API gateway.

The system's modular design allows each component to be independently tested, replaced, or extended. The transcription model, code generation models, and agent routing logic can all be modified without affecting other components. Git-based persistence provides a built-in audit trail and iteration history that would otherwise require significant custom development.

As a prototype for voice-driven AI-assisted software engineering, VAMP validates the feasibility of a complete voice-to-code pipeline using current multimodal LLM capabilities, structured prompting techniques, and lightweight web technologies.

**Future directions** include streaming LLM responses for real-time generation feedback, multi-turn conversational refinement of generated projects, automated testing and validation of generated code, container-based execution sandboxing for stronger security isolation, and collaborative multi-user project sharing through a shared git remote.
