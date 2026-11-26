FROM python:3.11-slim

# Create non-root user (required by Hugging Face Spaces)
RUN useradd -m -u 1000 user

WORKDIR /app

# Install system dependencies for bcrypt/psycopg2 if needed
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY --chown=user:user requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /app/requirements.txt

# Copy application files
COPY --chown=user:user backend /app/backend
COPY --chown=user:user frontend /app/frontend
COPY --chown=user:user run.py /app/run.py

# Create writable upload directories
RUN mkdir -p /app/uploads/recordings /app/uploads/imports && chown -R user:user /app

USER user

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 7860

# Auto-seed database if empty, then start FastAPI on dynamic $PORT (Render/Railway/Koyeb) or 7860
CMD ["sh", "-c", "python backend/seed.py && uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
