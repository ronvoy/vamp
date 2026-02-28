"""Voice transcription via OpenRouter (audio-capable models like Gemini Flash)."""
import base64
import io
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Ensure .env is loaded (works even when run from parent dir)
load_dotenv(Path(__file__).resolve().parent / ".env")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
TRANSCRIBE_MODEL = os.environ.get("TRANSCRIBE_MODEL", "google/gemini-2.5-flash")


def _webm_to_wav(audio_bytes: bytes) -> bytes:
    """Convert webm/ogg to wav for OpenRouter audio models."""
    try:
        from pydub import AudioSegment
    except ImportError:
        return audio_bytes  # fallback: try raw bytes as-is
    try:
        # Try webm first (Chrome/Firefox MediaRecorder)
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
    except Exception:
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="ogg")
        except Exception:
            return audio_bytes
    buf = io.BytesIO()
    audio.export(buf, format="wav")
    return buf.getvalue()


def transcribe_bytes(audio_bytes: bytes, language: str | None = None) -> str:
    """Transcribe raw audio bytes via OpenRouter (Gemini Flash etc.)."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY not set. Add it to app/.env (copy from .env.example)."
        )

    wav_bytes = _webm_to_wav(audio_bytes)
    b64 = base64.b64encode(wav_bytes).decode("utf-8")

    client = OpenAI(base_url=OPENROUTER_BASE, api_key=api_key)
    r = client.chat.completions.create(
        model=TRANSCRIBE_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Transcribe this audio exactly. Output only the transcribed text, nothing else.",
                    },
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": b64,
                            "format": "wav",
                        },
                    },
                ],
            }
        ],
        max_tokens=1024,
    )
    content = r.choices[0].message.content or ""
    return content.strip()
