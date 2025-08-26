FROM python:3.12-slim

WORKDIR /app

# Copy requirements file
COPY ./requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# --- START DEBUGGING COMMANDS ---
RUN echo "--- PIP SHOW MCP ---"
RUN pip show mcp || echo "mcp not found by pip"

RUN echo "--- CHECKING FOR starlette_app_factory.py ---"
RUN FILE_PATH=/usr/local/lib/python3.12/site-packages/mcp/server/fastmcp/starlette_app_factory.py && \
    if [ -f "$FILE_PATH" ]; then \
        echo "SUCCESS: $FILE_PATH EXISTS"; \
    else \
        echo "FAILURE: $FILE_PATH DOES NOT EXIST"; \
    fi

RUN echo "--- LISTING mcp/server/fastmcp ---"
RUN ls -lR /usr/local/lib/python3.12/site-packages/mcp/server/fastmcp/ || echo "Failed to list mcp/server/fastmcp"
# --- END DEBUGGING COMMANDS ---

# Copy the rest of your application code
COPY . .

ENV PYTHONPATH="/app"
EXPOSE 8080
CMD ["python", "tools/instavibe/mcp_server.py"]
