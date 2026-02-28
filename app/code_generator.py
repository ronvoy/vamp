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
