# Use an official Python runtime as a parent image
FROM python:3.12-slim

# List the contents of the workspace to debug COPY paths
RUN ls -lR /workspace

# Set the working directory in the container
WORKDIR /app

# Defensively remove app.py if it exists from a previous layer/build
RUN rm -f /app/app.py

# --- Dependency Installation ---
COPY requirements.txt . # Copy to current WORKDIR (/app)
RUN pip install --no-cache-dir -r requirements.txt

# --- Application Code ---
# COPY mcp_server.py /app/mcp_server.py
# COPY instavibe.py /app/instavibe.py
# COPY ./agents /app/agents/ # This path is relative to the build context (tools/instavibe), added trailing slash

# --- Environment ---
ENV PYTHONPATH=/app

# --- Debugging: Check file structure and PYTHONPATH ---
RUN echo "--- MCP-TOOL: Listing /app contents (before CMD) ---" && ls -R /app
RUN echo "--- MCP-TOOL: Finding Python files in /app (before CMD) ---" && find /app -name "*.py"
RUN echo "--- MCP-TOOL: PYTHONPATH IS $PYTHONPATH (before CMD) ---"

# Make port 8080 available to the world outside this container
# Cloud Run uses the PORT env var, but EXPOSE is good practice.
EXPOSE 8080

# --- Run the application ---
CMD ["sh", "-c", "echo 'Attempting to run Gunicorn with mcp_server:starlette_app' && gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --worker-class gthread mcp_server:starlette_app"]
