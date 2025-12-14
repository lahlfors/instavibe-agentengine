# Platform MCP Client Agent - Cloud Run Dockerfile
# Optimized for A2A protocol support with to_a2a

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY agents/platform_mcp_client/requirements.txt ./agents/platform_mcp_client/
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r agents/platform_mcp_client/requirements.txt

# Copy application code
COPY agents/ ./agents/
COPY tools/ ./tools/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/.well-known/agent.json')"

# Run the application
CMD ["/usr/local/bin/python", "-m", "agents.platform_mcp_client.main"]
