"""Agent selection and routing from voice command excerpts."""
import os
import re

AGENTS = {
    "openai": {"name": "GPT", "keywords": ["gpt", "openai", "chatgpt"]},
    "anthropic": {"name": "Claude", "keywords": ["claude", "anthropic"]},
}

def select_agent(text: str) -> str:
    """Parse voice command, return agent id. Fallback to DEFAULT_AGENT."""
    text_lower = text.lower().strip()
    for agent_id, info in AGENTS.items():
        if any(kw in text_lower for kw in info["keywords"]):
            return agent_id
    return os.environ.get("DEFAULT_AGENT", "openai")

def extract_task(text: str) -> str:
    """Remove agent keywords to get the actual task."""
    text_lower = text.lower()
    for agent_id, info in AGENTS.items():
        for kw in info["keywords"]:
            text_lower = re.sub(rf"\b{re.escape(kw)}\b", "", text_lower, flags=re.I)
    return " ".join(text_lower.split()).strip()
