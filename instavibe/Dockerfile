# instavibe/Dockerfile
FROM python:3.12-slim

# Define a build argument for the wheel file name
ARG A2A_WHL_FILE

WORKDIR /app

# Copy requirements.txt from the root of the build context (which is the 'instavibe' directory)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the a2a_common wheel using the build argument.
# The build command must pass --build-arg A2A_WHL_FILE=<filename_in_build_context>
# The specified ${A2A_WHL_FILE} is expected to be at the root of the build context (e.g., 'instavibe/' directory).
# Copy the wheel preserving its original filename, as pip expects a valid wheel filename.
COPY ${A2A_WHL_FILE} /app/${A2A_WHL_FILE}
RUN pip install --no-cache-dir /app/${A2A_WHL_FILE}

# --- Verify a2a_common installation ---
RUN set -e && \
    echo "--- Running pip show a2a_common ---" && \
    pip show a2a_common

# Copy the verification script from the build context (instavibe/verify_install.py)
COPY verify_install.py /tmp/verify_install.py
# Optional: RUN chmod +x /tmp/verify_install.py

# Execute the verification script
RUN set -e && \
    python /tmp/verify_install.py && \
    rm /tmp/verify_install.py
# --- End verification ---

# Copy the rest of the application code and assets from the build context
# (which is the 'instavibe' directory) into /app/ in the image.
COPY . /app/

ENV PYTHONPATH=/app
EXPOSE 8080

# --- Debug file structure ---
RUN echo "--- INSTAVIBE-APP: Listing /app contents ---" && ls -R /app

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
