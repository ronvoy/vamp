"""Generate a project setup script via OpenRouter LLM."""
import os
import re
import time
import requests as _requests
from openai import OpenAI

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

DEFAULT_MODEL = "google/gemma-3-27b-it"

AGENT_MODELS = {
    "openai": "openai/gpt-4o-mini",
    "anthropic": "anthropic/claude-3-5-haiku",
}

_models_cache: dict = {"data": None, "ts": 0}
CACHE_TTL = 3600


def fetch_models() -> list[dict]:
    """Fetch all models from OpenRouter, cached for CACHE_TTL seconds."""
    now = time.time()
    if _models_cache["data"] and now - _models_cache["ts"] < CACHE_TTL:
        return _models_cache["data"]
    try:
        r = _requests.get(
            f"{OPENROUTER_BASE}/models",
            headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"},
            timeout=15,
        )
        r.raise_for_status()
        raw = r.json().get("data", [])
        models = []
        for m in raw:
            mid = m.get("id", "")
            if mid.endswith(":free"):
                continue
            pricing = m.get("pricing") or {}
            prompt_cost = float(pricing.get("prompt", "0") or "0")
            completion_cost = float(pricing.get("completion", "0") or "0")
            models.append({
                "id": mid,
                "name": m.get("name", mid),
                "context_length": m.get("context_length", 0),
                "prompt_cost": prompt_cost,
                "completion_cost": completion_cost,
            })
        models.sort(key=lambda x: (x["prompt_cost"], x["name"]))
        _models_cache["data"] = models
        _models_cache["ts"] = now
        return models
    except Exception:
        return _models_cache["data"] or []


SYSTEM_PROMPT = r"""You are an expert coding agent. Given a user task, you MUST produce a single bash shell script called `setup.sh` that fully creates the project.

The script must:
1. Create all necessary files using heredocs (cat << 'EOF' > filename)
2. Use the CORRECT language and file extensions for the platform the user asked for:
   - iOS/SwiftUI → .swift files
   - Android → .kt files
   - Web/frontend → .html, .css, .js files
   - Python → .py files
   - Go → .go files
   - Rust → .rs files
   - TypeScript/React → .ts/.tsx files
   - Java → .java files
   - Any other language → use the correct extension
3. NEVER default to Python unless the user explicitly asks for Python or doesn't specify a language.
4. Create a README.md with:
   - Project description
   - Project structure (file tree)
   - What each file does
   - How to install dependencies
   - How to build and run
   - Technologies used

Your response format MUST be:

1. Brief reasoning (2-4 sentences about your approach)
2. A SINGLE bash code block containing the complete setup.sh:

```bash
#!/bin/bash
# setup.sh - <project description>

# Create project files
cat << 'EOF' > filename.ext
<file content>
EOF

cat << 'EOF' > README.md
# Project Name
...
EOF

echo "Project setup complete!"
```

3. At the end (outside the code block):
FOLDER_NAME: <kebab-case-name>

CRITICAL RULES:
- Output ONLY ONE code block containing the bash script
- Use cat << 'EOF' > filename (with single-quoted EOF to prevent variable expansion)
- For subdirectories, use mkdir -p before writing files
- Do NOT use Python/pip unless the user asked for Python
- Match the language/platform to what the user asked for
- The script should be self-contained and runnable with `bash setup.sh`"""


def _client():
    return OpenAI(
        base_url=OPENROUTER_BASE,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )


def generate_openai(task: str, context: str | None = None, model_id: str | None = None) -> dict:
    return _generate(task, "openai", context, model_id)


def generate_anthropic(task: str, context: str | None = None, model_id: str | None = None) -> dict:
    return _generate(task, "anthropic", context, model_id)


def generate_with_model(task: str, model_id: str, context: str | None = None) -> dict:
    return _generate(task, "custom", context, model_id)


def _generate(task: str, agent: str, context: str | None = None, model_id: str | None = None) -> dict:
    model = model_id or AGENT_MODELS.get(agent, DEFAULT_MODEL)
    client = _client()
    user_content = f"Task: {task}"
    if context:
        user_content = f"Continue from previous work. Context:\n{context}\n\nNew request: {task}"
    r = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        max_tokens=8192,
    )
    content = r.choices[0].message.content
    usage = {}
    if getattr(r, "usage", None):
        u = r.usage
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens": getattr(u, "total_tokens", 0),
        }
    parsed = _parse_response(content)
    return {
        "script": parsed["script"],
        "folder_name": parsed["folder_name"],
        "reasoning": parsed["reasoning"],
        "raw_response": content,
        "usage": usage,
    }


def _parse_response(content: str) -> dict:
    """Extract the bash script, reasoning, and folder name from LLM response."""
    folder_name = "generated-app"
    reasoning = ""
    script = ""

    blocks = list(re.finditer(r"```(?:bash|sh|shell)?\n(.*?)```", content, re.DOTALL))

    if blocks:
        script = blocks[0].group(1).strip()
        first_block_start = blocks[0].start()
        reasoning = content[:first_block_start].strip()
        reasoning = re.sub(r"\n{3,}", "\n\n", reasoning)

    m = re.search(r"FOLDER_NAME:\s*([a-z0-9\-]+)", content, re.I)
    if m:
        folder_name = m.group(1).strip()

    if not script:
        script = f'#!/bin/bash\necho "Error: No script generated"\n# Raw LLM output saved to raw_response.txt\ncat << \'EOF\' > raw_response.txt\n{content}\nEOF'

    if not script.startswith("#!"):
        script = "#!/bin/bash\n" + script

    return {"script": script, "folder_name": folder_name, "reasoning": reasoning}
