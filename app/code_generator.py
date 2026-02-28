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
2. Infer the output format from the user's request:
   - If they ask for HTML, a webpage, web page, or frontend: produce HTML (index.html), optionally with CSS and JS
   - If they ask for CSS or styles: produce CSS (style.css or styles.css)
   - If they ask for JavaScript, JS, or client-side script: produce JavaScript (script.js or app.js)
   - If they ask for Markdown, MD, or documentation: produce Markdown (README.md or document.md)
   - Otherwise (or if unclear): default to Python with main.py and requirements.txt
3. Use triple-backtick code blocks with language and optional filename, e.g. ```html, ```css, ```javascript, ```markdown, ```python.
4. At the end, output two lines:
   OUTPUT_FORMAT: <html|python|css|javascript|markdown>
   FOLDER_NAME: <kebab-case-name>

Example (Python, default):
I'll create a Flask app that... [brief reasoning]
```python
# main.py
...
```
```requirements.txt
...
```
OUTPUT_FORMAT: python
FOLDER_NAME: todo-cli

Example (HTML):
I'll build a simple landing page... [brief reasoning]
```html
<!-- index.html -->
...
```
```css
/* style.css */
...
```
OUTPUT_FORMAT: html
FOLDER_NAME: landing-page"""

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
    return {"files": parsed["files"], "folder_name": parsed["folder_name"], "reasoning": parsed["reasoning"], "raw_response": content, "usage": usage}

def _parse_response(content: str) -> dict:
    """Extract reasoning, files (by format), FOLDER_NAME from LLM response."""
    folder_name = "generated-app"
    reasoning = ""
    output_format = "python"
    blocks = list(re.finditer(r"```(\w*)\n(.*?)```", content, re.DOTALL))
    if blocks:
        first_block_start = blocks[0].start()
        reasoning = content[:first_block_start].strip()
        reasoning = re.sub(r"\n{3,}", "\n\n", reasoning)
    m_fmt = re.search(r"OUTPUT_FORMAT:\s*(\w+)", content, re.I)
    if m_fmt:
        output_format = m_fmt.group(1).strip().lower()
    m = re.search(r"FOLDER_NAME:\s*([a-z0-9\-]+)", content, re.I)
    if m:
        folder_name = m.group(1).strip()
    files: dict[str, str] = {}
    py_blocks: list[str] = []
    for m in blocks:
        lang = (m.group(1) or "python").lower()
        code = m.group(2).strip()
        if "FOLDER_NAME:" in code or "OUTPUT_FORMAT:" in code:
            continue
        if "req" in lang or lang == "txt" or "pip" in lang or "requirement" in lang:
            files["requirements.txt"] = code or "flask>=3.0.0\nrequests>=2.31.0\n"
        elif "html" in lang:
            files["index.html"] = code
        elif "css" in lang:
            files["style.css"] = code
        elif "javascript" in lang or "js" in lang:
            files["script.js"] = code
        elif "markdown" in lang or "md" in lang:
            files["README.md"] = code
        elif "python" in lang or lang == "py":
            py_blocks.append(code)
        else:
            if output_format == "python":
                py_blocks.append(code)
            elif output_format in ("html", "htm"):
                files.setdefault("index.html", code)
            elif output_format in ("markdown", "md"):
                files.setdefault("README.md", code)
            elif output_format == "css":
                files.setdefault("style.css", code)
            elif output_format in ("javascript", "js"):
                files.setdefault("script.js", code)
            else:
                py_blocks.append(code)
    if output_format == "python":
        if py_blocks:
            files["main.py"] = py_blocks[0]
        if "requirements.txt" not in files:
            files["requirements.txt"] = "flask>=3.0.0\nrequests>=2.31.0\n"
        if "main.py" not in files and blocks:
            files["main.py"] = blocks[0].group(2).strip()
        if "main.py" not in files:
            files["main.py"] = content
    elif not files and blocks:
        files["output.txt"] = blocks[0].group(2).strip()
    return {"files": files, "folder_name": folder_name, "reasoning": reasoning}
