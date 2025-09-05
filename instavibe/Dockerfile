FROM python:3.12-slim
WORKDIR /app

# Corrected paths relative to the build context (PROJECT_ROOT)
COPY ./instavibe/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY ./instavibe/ ./
COPY ./common ./common

ENV PYTHONPATH="/app"
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
