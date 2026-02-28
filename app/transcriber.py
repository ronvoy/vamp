"""Voice transcription and translation via OpenAI Whisper."""
import os
from openai import OpenAI

def transcribe(audio_path: str, language: str | None = None) -> str:
    """Transcribe audio file to text. Optional translation to English."""
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language,
            response_format="text",
        )
    return transcript.strip() if transcript else ""

def transcribe_bytes(audio_bytes: bytes, language: str | None = None) -> str:
    """Transcribe raw audio bytes."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp.flush()
        try:
            return transcribe(tmp.name, language)
        finally:
            os.unlink(tmp.name)
