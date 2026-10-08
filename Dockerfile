FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DATA_ROOT=/app/storage
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV MCP_URL=http://mcp:8765/mcp
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8765

EXPOSE 8501 8765
