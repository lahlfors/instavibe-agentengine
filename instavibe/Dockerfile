# instavibe/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy and install requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- Verify OpenTelemetry SDK installation (as propagator is removed) ---
# Copy the verification script from the build context (instavibe/verify_otel_sdk.py)
COPY verify_otel_sdk.py /tmp/verify_otel_sdk.py

# Execute the verification script
RUN set -e && \
    python /tmp/verify_otel_sdk.py && \
    rm /tmp/verify_otel_sdk.py
# --- End OpenTelemetry SDK Verification ---

# Copy the 'agents' source code
COPY temp_agents_for_build /app/agents

# Copy the rest of the application code and assets
COPY . /app/

# Set the Python path to make modules importable
ENV PYTHONPATH=/app
EXPOSE 8080

# --- Debug file structure ---
RUN echo "--- INSTAVIBE-APP: Listing /app contents ---" && ls -R /app

# Run the application
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
