FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY requirements.txt .

RUN uv venv "$VIRTUAL_ENV" \
    && uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache -r requirements.txt

COPY . .

CMD ["sh", "-c", "python db_manager.py && python -c \"import qdrant_manager; qdrant_manager.ingest_knowledge_document('MEMORY.md')\" && tail -f /dev/null"]
