FROM python:3.12-slim

WORKDIR /app

# Copy the specific requirements file for this service
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# The 'agents' and 'common' directories are now copied into the build context by cloudbuild.yaml
COPY agents ./agents
COPY agents/common ./common

# Copy the server script itself
COPY mcp_server.py .

ENV PYTHONPATH="/app"
EXPOSE 8080

# Run the server from the root of the WORKDIR
CMD ["python", "mcp_server.py"]
