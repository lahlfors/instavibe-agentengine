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
    echo -e "\
import sys \n\
import os \n\
import site \n\
print('--- Python sys.path during build: ---') \n\
for p in sys.path: print(p) \n\
print('--- Attempting to import a2a_common and submodules ---') \n\
try: \n\
    import a2a_common \n\
    print('Successfully imported a2a_common, location: ' + str(a2a_common.__file__)) \n\
    import a2a_common.utils.logging_setup \n\
    print('Successfully imported a2a_common.utils.logging_setup, location: ' + str(a2a_common.utils.logging_setup.__file__)) \n\
    print('--- a2a_common import verification successful ---') \n\
except ImportError as e_import: \n\
    print('!!! Python import verification FAILED (ImportError): {}'.format(e_import)) \n\
    print('Python sys.path on failure:') \n\
    for p_fail in sys.path: print(p_fail) \n\
    print('Site packages:') \n\
    site_pkgs = site.getsitepackages() \n\
    print(site_pkgs) \n\
    if site_pkgs and len(site_pkgs) > 0 and os.path.exists(site_pkgs[0]): \n\
        print('Contents of first site-package dir ({}):'.format(site_pkgs[0])) \n\
        try: \n\
            print(os.listdir(site_pkgs[0])) \n\
        except Exception as e_listdir: \n\
            print('Error listing site-packages: {}'.format(e_listdir)) \n\
    else: \n\
        print('No site-packages found or first one is invalid/inaccessible') \n\
    sys.exit(1) \n\
except Exception as e_general: \n\
    print('!!! Python import verification FAILED (General Exception): {}'.format(e_general)) \n\
    sys.exit(1) \n\
" > /tmp/verify_install.py && \
    python /tmp/verify_install.py
# --- End verification ---

# Copy the rest of the application code and assets from the build context
# (which is the 'instavibe' directory) into /app/ in the image.
COPY . /app/

ENV PYTHONPATH=/app
EXPOSE 8080

# --- Debug file structure ---
RUN echo "--- INSTAVIBE-APP: Listing /app contents ---" && ls -R /app

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
