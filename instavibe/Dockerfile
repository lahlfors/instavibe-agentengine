# instavibe/Dockerfile
FROM python:3.12-slim
WORKDIR /app

# Copy requirements.txt from the root of the build context (which is the 'instavibe' directory)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the a2a_common wheel (expected to be copied into the build context by deploy_all.py)
COPY a2a_common-0.1.0-py3-none-any.whl /app/
RUN pip install --no-cache-dir /app/a2a_common-0.1.0-py3-none-any.whl

# Copy the rest of the application code and assets from the build context
# (which is the 'instavibe' directory) into /app/ in the image.
COPY . /app/

ENV PYTHONPATH=/app
EXPOSE 8080

# --- Debug file structure ---
RUN echo "--- INSTAVIBE-APP: Listing /app contents ---" && ls -R /app

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
