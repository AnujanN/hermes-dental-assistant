FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager inside the container
RUN pip install --no-cache-dir uv

# Copy requirements
COPY requirements.txt .

# Install dependencies using uv
RUN uv pip install --system --no-cache -r requirements.txt

# Copy database administration scripts
COPY . .

# Run SQLite schema initialization and ingest MEMORY.md into Qdrant, then idle
CMD python db_manager.py && \
    python -c "import qdrant_manager; qdrant_manager.ingest_knowledge_document('MEMORY.md')" && \
    tail -f /dev/null
