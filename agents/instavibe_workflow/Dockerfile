# Dockerfile for Instavibe Workflow Agent (Flask App based)

FROM python:3.12-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code for this agent
# This includes main.py (Flask app) and agent.py (logic)
COPY main.py /app/main.py
COPY agent.py /app/agent.py
# If there are any other local modules/utils specifically for this agent, copy them too.
# For example, if agent.py used helpers from a subdirectory:
# COPY utils/ /app/utils/

ENV PYTHONPATH=/app
ENV PORT=8080

# Gunicorn entry point
CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "--workers", "1", "main:app"]
