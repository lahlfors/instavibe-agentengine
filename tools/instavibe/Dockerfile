# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Defensively remove app.py if it exists from a previous layer/build
RUN rm -f /app/app.py

# --- Dependency Installation ---
# Paths are now relative to the project root build context
COPY tools/instavibe/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- Application Code ---
# Paths are now relative to the project root build context
COPY tools/instavibe/mcp_server.py /app/mcp_server.py
COPY tools/instavibe/instavibe.py /app/instavibe.py
COPY agents /app/agents/ # This now correctly copies the main 'agents' directory

# --- Environment ---
ENV PYTHONPATH=/app

# --- Debugging: Check file structure and PYTHONPATH ---
# These debug lines can be re-enabled if needed, but paths inside are relative to WORKDIR /app
RUN echo "--- MCP-TOOL: Listing /app contents (after COPY, before CMD) ---" && ls -R /app
RUN echo "--- MCP-TOOL: Finding Python files in /app (after COPY, before CMD) ---" && find /app -name "*.py"
RUN echo "--- MCP-TOOL: PYTHONPATH IS $PYTHONPATH (after COPY, before CMD) ---"

# Make port 8080 available to the world outside this container
# Cloud Run uses the PORT env var, but EXPOSE is good practice.
EXPOSE 8080

# --- Run the application ---
CMD ["sh", "-c", "echo 'Attempting to run Gunicorn with mcp_server:starlette_app' && gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 2 --worker-class gthread mcp_server:starlette_app"]
