FROM python:3.10-slim

# Install system dependencies: ffmpeg (pydub) and git (conversation_store)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /vamp

# Install Python dependencies
COPY app/requirements.txt app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

# Copy application code
COPY app/ app/

# Create conversation directory (mount as volume for persistence)
RUN mkdir -p /vamp/conversation

ENV PORT=5000

EXPOSE 5000

WORKDIR /vamp/app

CMD ["python", "app.py"]
