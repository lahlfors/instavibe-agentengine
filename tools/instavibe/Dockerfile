FROM python:3.12-slim

WORKDIR /app

# Copy the specific requirements file for this service
COPY tools/instavibe/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the shared agents directory
COPY agents ./agents

# Copy the server script itself
COPY tools/instavibe/mcp_server.py .

ENV PYTHONPATH="/app"
EXPOSE 8080

# Run the server from the root of the WORKDIR
CMD ["python", "mcp_server.py"]
