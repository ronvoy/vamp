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

1. First, briefly reason step-by-step about the approach (2-4 sentences).
2. Then produce runnable Python code.
3. Always output a main.py and requirements.txt.
4. Use triple-backtick code blocks with language (e.g. ```python).
5. At the end, output a single line: FOLDER_NAME: <kebab-case-name>

Example format:
I'll create a Flask app that... [brief reasoning]

```python
# main.py
...
```
```requirements.txt
...
```
FOLDER_NAME: todo-cli"""

def _client():
    return OpenAI(
        base_url=OPENROUTER_BASE,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )

def generate_openai(task: str, context: str | None = None) -> dict:
    """Generate code via OpenRouter -> GPT."""
    return _generate(task, "openai", context)

def generate_anthropic(task: str, context: str | None = None) -> dict:
    """Generate code via OpenRouter -> Claude."""
    return _generate(task, "anthropic", context)

def _generate(task: str, agent: str, context: str | None = None) -> dict:
    model = MODELS.get(agent, MODELS["openai"])
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
        max_tokens=4096,
    )
    content = r.choices[0].message.content
    usage = {}
    if getattr(r, "usage", None):
        u = r.usage
        usage = {"prompt_tokens": getattr(u, "prompt_tokens", 0), "completion_tokens": getattr(u, "completion_tokens", 0), "total_tokens": getattr(u, "total_tokens", 0)}
    parsed = _parse_response(content)
    return {"main_py": parsed["main_py"], "requirements": parsed["requirements"], "folder_name": parsed["folder_name"], "reasoning": parsed["reasoning"], "raw_response": content, "usage": usage}

def _parse_response(content: str) -> dict:
    """Extract reasoning, main.py, requirements.txt, FOLDER_NAME from LLM response."""
    folder_name = "generated-app"
    reasoning = ""
    blocks = list(re.finditer(r"```(\w*)\n(.*?)```", content, re.DOTALL))
    if blocks:
        first_block_start = blocks[0].start()
        reasoning = content[:first_block_start].strip()
        reasoning = re.sub(r"\n{3,}", "\n\n", reasoning)
    main_py, requirements = "", "flask>=3.0.0\nrequests>=2.31.0\n"
    for m in blocks:
        lang = (m.group(1) or "python").lower()
        code = m.group(2).strip()
        if "FOLDER_NAME:" in code:
            continue
        if "req" in lang or "txt" in lang or "pip" in lang or "requirement" in lang:
            requirements = code if code else requirements
        else:
            main_py = code if not main_py else main_py
    m = re.search(r"FOLDER_NAME:\s*([a-z0-9\-]+)", content, re.I)
    if m:
        folder_name = m.group(1).strip()
    if not main_py and blocks:
        main_py = blocks[0].group(2).strip()
    if not main_py:
        main_py = content
    return {"main_py": main_py, "requirements": requirements, "folder_name": folder_name, "reasoning": reasoning}
