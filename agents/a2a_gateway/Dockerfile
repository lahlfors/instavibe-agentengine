FROM python:3.12-slim

ENV PYTHONUNBUFFERED True
ENV PIP_NO_CACHE_DIR True

WORKDIR /usr/src/app

# --- Install the local a2a_common wheel ---
COPY a2a_common-0.1.0-py3-none-any.whl ./
RUN echo "--- Attempting to install a2a_common wheel ---" && \
    pip install ./a2a_common-0.1.0-py3-none-any.whl

# --- Verification steps ---
RUN echo "--- PIP FREEZE after wheel install ---" && pip freeze | grep a2a
RUN echo "--- PIP SHOW a2a-common ---" && pip show a2a-common
RUN echo "--- Contents of site-packages ---" && ls -l $(python -c 'import site; print(site.getsitepackages()[0])')
RUN echo "--- Contents of a2a in site-packages ---" && ls -l $(python -c 'import site; print(site.getsitepackages()[0])')/a2a


# --- CRITICAL TEST: Try importing the module ---
RUN echo "--- Testing 'import a2a' ---" && \
    python -c "import a2a; print('SUCCESS: a2a module imported')"

# --- Install other dependencies ---
COPY requirements.txt ./
RUN pip install -r requirements.txt


# --- Copy Application Code ---
COPY . .

RUN echo "--- Final contents of /usr/src/app ---" && ls -lR /usr/src/app

ENV PORT 8080
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 a2a_server:app
