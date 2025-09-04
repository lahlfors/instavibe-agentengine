FROM python:3.12-slim
WORKDIR /app

# COPY path is relative to the project root
COPY instavibe/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY instavibe/app.py .
COPY instavibe/db.py .
COPY instavibe/ally_routes.py .
COPY instavibe/introvertally.py .
COPY instavibe/static ./static
COPY instavibe/templates ./templates

ENV PYTHONPATH="/app"
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
