FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app



# Install uv package manager inside the container
RUN pip install --no-cache-dir uv

# Copy dependencies list
COPY server/requirements.txt .

# Install dependencies directly into system python using uv
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application directories
COPY db_server /app/db_server
COPY server /app/server
COPY tests /app/tests

# Expose port
EXPOSE 8000

# Start server
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8000"]
