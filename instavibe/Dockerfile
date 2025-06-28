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
    (cat <<'EOF' > /tmp/verify_install.py
import sys
import os
import site

print('--- Python sys.path during build: ---')
for p in sys.path:
    print(p)
print('--- Attempting to import a2a_common and submodules ---')
try:
    import a2a_common
    print('Successfully imported a2a_common, location: ' + str(a2a_common.__file__))
    import a2a_common.utils.logging_setup
    print('Successfully imported a2a_common.utils.logging_setup, location: ' + str(a2a_common.utils.logging_setup.__file__))
    print('--- a2a_common import verification successful ---')
    sys.stdout.flush() # Ensure all output is written
    sys.exit(0) # Explicitly exit with 0 on success
except ImportError as e_import:
    print('!!! Python import verification FAILED (ImportError): {}'.format(e_import))
    # The following diagnostic info will be printed before exiting with 1
except Exception as e_general:
    print('!!! Python import verification FAILED (General Exception): {}'.format(e_general))
    # The following diagnostic info will be printed before exiting with 1
# Common exit path for failures to print diagnostics
# This code will only be reached if an exception occurred in the try block,
# because successful try block calls sys.exit(0).
print('Python sys.path on failure:')
for p_fail in sys.path: print(p_fail)
print('Site packages:')
site_pkgs = site.getsitepackages()
print(site_pkgs)
if site_pkgs and len(site_pkgs) > 0 and os.path.exists(site_pkgs[0]):
    print('Contents of first site-package dir ({}):'.format(site_pkgs[0]))
    try:
        print(os.listdir(site_pkgs[0]))
    except Exception as e_listdir:
        print('Error listing site-packages: {}'.format(e_listdir))
else:
    print('No site-packages found or first one is invalid/inaccessible')
sys.stdout.flush() # Ensure all diagnostic output is written
sys.stderr.flush()
sys.exit(1) # Exit with 1 if we reached here (meaning an exception occurred)
EOF
    ) && \
    python /tmp/verify_install.py && \
    rm /tmp/verify_install.py # Clean up the temporary script
# --- End verification ---

# Copy the rest of the application code and assets from the build context
# (which is the 'instavibe' directory) into /app/ in the image.
COPY . /app/

ENV PYTHONPATH=/app
EXPOSE 8080

# --- Debug file structure ---
RUN echo "--- INSTAVIBE-APP: Listing /app contents ---" && ls -R /app

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
