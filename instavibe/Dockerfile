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
RUN echo "--- Verifying a2a_common installation post pip install ---" && \
    pip show a2a_common && \
    python -c "\
import sys; \
import os; \
print('--- Python sys.path during build: ---'); \
for p in sys.path: print(p); \
print('--- Attempting to import a2a_common and submodules ---'); \
import a2a_common; \
print(f'Successfully imported a2a_common, location: {a2a_common.__file__}'); \
import a2a_common.utils.logging_setup; \
print(f'Successfully imported a2a_common.utils.logging_setup, location: {a2a_common.utils.logging_setup.__file__}'); \
print('--- a2a_common import verification successful ---')" || \
    (echo "!!! Python import verification FAILED. Listing site-packages and sys.path again. !!!" && \
     python -c "import site; import os; import sys; print('Python sys.path on failure:'); for p in sys.path: print(p); print('Site packages:'); print(site.getsitepackages()); print('Contents of first site-package dir:'); print(os.listdir(site.getsitepackages()[0])) if site.getsitepackages() and os.path.exists(site.getsitepackages()[0]) else print('No site-packages found or first one is invalid')" && \
     exit 1)
# --- End verification ---

# Copy the rest of the application code and assets from the build context
# (which is the 'instavibe' directory) into /app/ in the image.
COPY . /app/

ENV PYTHONPATH=/app
EXPOSE 8080

# --- Debug file structure ---
RUN echo "--- INSTAVIBE-APP: Listing /app contents ---" && ls -R /app

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
