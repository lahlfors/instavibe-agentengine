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

# Create the diagnostic script using multiple echo commands
# This is verbose, but aims to be absolutely safe from Docker parser errors.
RUN set -e && \
    echo '#!/usr/bin/env python' > /tmp/verify_install.py && \
    echo 'import sys' >> /tmp/verify_install.py && \
    echo 'import os' >> /tmp/verify_install.py && \
    echo 'import site' >> /tmp/verify_install.py && \
    echo '' >> /tmp/verify_install.py && \
    echo 'print("'"'--- Python sys.path during build: ---'"'")' >> /tmp/verify_install.py && \
    echo 'for p in sys.path:' >> /tmp/verify_install.py && \
    echo '    print(p)' >> /tmp/verify_install.py && \
    echo 'sys.stdout.flush()' >> /tmp/verify_install.py && \
    echo '' >> /tmp/verify_install.py && \
    echo 'print("'"'--- Attempting to import a2a_common and submodules ---'"'")' >> /tmp/verify_install.py && \
    echo 'try:' >> /tmp/verify_install.py && \
    echo '    import a2a_common' >> /tmp/verify_install.py && \
    echo '    print("'"'Successfully imported a2a_common, location: '"'"' + str(a2a_common.__file__))' >> /tmp/verify_install.py && \
    echo '    sys.stdout.flush()' >> /tmp/verify_install.py && \
    echo '    import a2a_common.utils.logging_setup' >> /tmp/verify_install.py && \
    echo '    print("'"'Successfully imported a2a_common.utils.logging_setup, location: '"'"' + str(a2a_common.utils.logging_setup.__file__))' >> /tmp/verify_install.py && \
    echo '    sys.stdout.flush()' >> /tmp/verify_install.py && \
    echo '    print("'"'--- a2a_common import verification successful ---'"'")' >> /tmp/verify_install.py && \
    echo '    sys.stdout.flush()' >> /tmp/verify_install.py && \
    echo '    sys.exit(0)' >> /tmp/verify_install.py && \
    echo 'except ImportError as e_import:' >> /tmp/verify_install.py && \
    echo '    print("'"'!!! Python import verification FAILED (ImportError): {}'"'".format(e_import))' >> /tmp/verify_install.py && \
    echo '    sys.stderr.flush()' >> /tmp/verify_install.py && \
    echo 'except Exception as e_general:' >> /tmp/verify_install.py && \
    echo '    print("'"'!!! Python import verification FAILED (General Exception): {}'"'".format(e_general))' >> /tmp/verify_install.py && \
    echo '    sys.stderr.flush()' >> /tmp/verify_install.py && \
    echo '' >> /tmp/verify_install.py && \
    echo '# This part is reached only if an exception occurred in the try block (and sys.exit(0) was not called)' >> /tmp/verify_install.py && \
    echo 'print("'"'--- Diagnostics on failure ---'"'")' >> /tmp/verify_install.py && \
    echo 'print("'"'Python sys.path on failure (re-printing):'"'")' >> /tmp/verify_install.py && \
    echo 'for p_fail in sys.path: print(p_fail)' >> /tmp/verify_install.py && \
    echo 'sys.stdout.flush()' >> /tmp/verify_install.py && \
    echo '' >> /tmp/verify_install.py && \
    echo 'print("'"'Site packages:'"'")' >> /tmp/verify_install.py && \
    echo 'site_pkgs = []' >> /tmp/verify_install.py && \
    echo 'try:' >> /tmp/verify_install.py && \
    echo '    site_pkgs = site.getsitepackages()' >> /tmp/verify_install.py && \
    echo '    print(site_pkgs)' >> /tmp/verify_install.py && \
    echo '    if site_pkgs and len(site_pkgs) > 0 and os.path.exists(site_pkgs[0]):' >> /tmp/verify_install.py && \
    echo '        print("'"'Contents of first site-package dir ({}):'"'".format(site_pkgs[0]))' >> /tmp/verify_install.py && \
    echo '        try:' >> /tmp/verify_install.py && \
    echo '            print(os.listdir(site_pkgs[0]))' >> /tmp/verify_install.py && \
    echo '        except Exception as e_listdir:' >> /tmp/verify_install.py && \
    echo '            print("'"'Error listing site-packages contents: {}'"'".format(e_listdir))' >> /tmp/verify_install.py && \
    echo '    else:' >> /tmp/verify_install.py && \
    echo '        print("'"'No site-packages found by site.getsitepackages() or first one is invalid/inaccessible'"'")' >> /tmp/verify_install.py && \
    echo 'except Exception as e_site:' >> /tmp/verify_install.py && \
    echo '    print("'"'Error getting site packages: {}'"'".format(e_site))' >> /tmp/verify_install.py && \
    echo 'sys.stdout.flush()' >> /tmp/verify_install.py && \
    echo 'sys.stderr.flush()' >> /tmp/verify_install.py && \
    echo 'sys.exit(1)' >> /tmp/verify_install.py

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
