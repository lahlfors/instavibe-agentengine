# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# --- Dependency Installation ---
COPY tools/instavibe/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN ls -lR /usr/local/lib/python3.12/site-packages/mcp

# --- Application Code ---
COPY ./tools /app/tools
COPY ./agents /app/agents
COPY ./common /app/common
COPY ./instavibe /app/instavibe

# --- Environment ---
ENV PYTHONPATH=/app

# Make port 8080 available to the world outside this container
# Cloud Run uses the PORT env var, but EXPOSE is good practice.
EXPOSE 8080

# --- Run the application ---
CMD ["sh", "-c", "opentelemetry-instrument uvicorn tools.instavibe.mcp_server:starlette_app --host 0.0.0.0 --port $PORT"]
