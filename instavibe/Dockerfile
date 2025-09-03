# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# --- Dependency Installation ---
# Copy only the requirements file first to leverage Docker cache
COPY ./requirements.txt /app/requirements.txt
COPY ./agents/a2a_common-0.1.0-py3-none-any.whl /app/a2a_common-0.1.0-py3-none-any.whl
RUN pip install --no-cache-dir -r /app/requirements.txt /app/a2a_common-0.1.0-py3-none-any.whl


# --- Application Code ---
# Copy application code from the context into the container
COPY ./instavibe/ /app/instavibe/
COPY ./agents/ /app/agents/
COPY ./common/ /app/common/

# --- Environment ---
ENV PYTHONPATH=/app


# Make port 8080 available to the world outside this container
# Cloud Run uses the PORT env var, but EXPOSE is good practice.
EXPOSE 8080

# --- Run the application ---
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread instavibe.app:app"]
