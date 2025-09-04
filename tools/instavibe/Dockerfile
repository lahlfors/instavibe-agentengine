FROM python:3.12-slim
WORKDIR /app

# COPY paths are relative to the project root
COPY tools/instavibe/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agents ./agents
COPY common ./common
COPY tools/instavibe/mcp_server.py ./mcp_server.py

ENV PYTHONPATH="/app"
EXPOSE 8080
CMD ["python", "mcp_server.py"]
