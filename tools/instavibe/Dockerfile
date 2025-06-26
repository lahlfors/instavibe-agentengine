# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Defensively remove app.py if it exists from a previous layer/build
RUN rm -f /app/app.py

# --- Dependency Installation ---
COPY tools/instavibe/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- Application Code ---
COPY tools/instavibe/mcp_server.py /app/mcp_server.py
COPY ./agents /app/agents

# --- Environment ---
ENV PYTHONPATH=/app

# Make port 8080 available to the world outside this container
# Cloud Run uses the PORT env var, but EXPOSE is good practice.
EXPOSE 8080

# --- Run the application ---
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread mcp_server:starlette_app"]
