# === Symbiote Lite - Dockerfile ===
# Multi-stage build for smaller final image

# --- Build Stage ---
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY pyproject.toml .
COPY README.md .

# Install dependencies (including gradio for web UI)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir build && \
    pip install --no-cache-dir pandas numpy python-dotenv mcp openai pytest gradio tabulate

# --- Runtime Stage ---
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY symbiote_lite/ ./symbiote_lite/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Set ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app

# Expose port for Gradio UI
EXPOSE 7860

# Default command - run the interactive agent
CMD ["python", "-m", "scripts.run_agent"]

# --- Alternative entry points ---
# CLI Agent:   docker run -it symbiote-lite
# Gradio UI:   docker run -p 7860:7860 symbiote-lite python -m scripts.gradio_app
# MCP Server:  docker run -p 8000:8000 symbiote-lite python -m scripts.mcp_server
# Tests:       docker run symbiote-lite python -m pytest
