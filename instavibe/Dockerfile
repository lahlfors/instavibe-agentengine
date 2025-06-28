# instavibe/Dockerfile
FROM python:3.12-slim

# Define a build argument for the wheel file name
ARG A2A_WHL_FILE

WORKDIR /app

# Copy requirements.txt from the root of the build context (which is the 'instavibe' directory)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ARG A2A_WHL_FILE # No longer used

WORKDIR /app

# Copy requirements.txt from the root of the build context (which is the 'instavibe' directory)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the a2a_common wheel using the build argument. # This comment is now obsolete
# The build command must pass --build-arg A2A_WHL_FILE=<filename_in_build_context> # Obsolete
# The specified ${A2A_WHL_FILE} is expected to be at the root of the build context (e.g., 'instavibe/' directory). # Obsolete
# Copy the wheel preserving its original filename, as pip expects a valid wheel filename. # Obsolete
# COPY ${A2A_WHL_FILE} /app/${A2A_WHL_FILE} # Removed
# RUN pip install --no-cache-dir /app/${A2A_WHL_FILE} # Removed

# --- Verify a2a_common installation --- # This entire verification block is removed
# RUN set -e && \
#     echo "--- Running pip show a2a_common ---" && \
#     pip show a2a_common

# Copy the verification script from the build context (instavibe/verify_install.py) # Removed
# COPY verify_install.py /tmp/verify_install.py # Removed
# Optional: RUN chmod +x /tmp/verify_install.py # Removed

# Execute the verification script # Removed
# RUN set -e && \
#     python /tmp/verify_install.py && \
#     rm /tmp/verify_install.py # Removed
# --- End verification --- # Removed

# Copy the 'agents' source code prepared by deploy_all.py into instavibe/temp_agents_for_build
COPY temp_agents_for_build /app/agents

# Copy the rest of the application code and assets from the build context
# (which is the 'instavibe' directory, excluding temp_agents_for_build if not handled by .dockerignore)
# into /app/ in the image.
COPY . /app/

ENV PYTHONPATH=/app # This makes /app and /app/agents importable
EXPOSE 8080

# --- Debug file structure ---
RUN echo "--- INSTAVIBE-APP: Listing /app contents ---" && ls -R /app

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
