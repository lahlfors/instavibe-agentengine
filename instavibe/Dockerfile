FROM python:3.12-slim
WORKDIR /app

# Standard paths relative to the build context (the instavibe/ directory)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# The 'common' directory is now copied into the build context by cloudbuild.yaml
COPY common ./common

ENV PYTHONPATH="/app"
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
