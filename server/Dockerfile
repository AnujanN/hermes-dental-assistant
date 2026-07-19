FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY server/requirements.txt .

# Keep dependencies in an explicit venv so runtime behavior is stable without pyproject.toml.
RUN uv venv "$VIRTUAL_ENV" \
    && uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache -r requirements.txt

COPY db_server /app/db_server
COPY server /app/server
COPY tests /app/tests

EXPOSE 8000

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
