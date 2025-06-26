# instavibe/Dockerfile
FROM python:3.12-slim
WORKDIR /app

# Copy application specific files from the 'instavibe' directory
COPY instavibe/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the 'instavibe' application code and assets
# This will put app.py, static/, templates/, etc. into /app/
COPY instavibe/ /app/

# Copy the shared 'agents' directory from the repo root
COPY ./agents /app/agents

ENV PYTHONPATH=/app
EXPOSE 8080
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --worker-class gthread app:app"]
