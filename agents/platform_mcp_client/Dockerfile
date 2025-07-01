# /Users/linchr/Desktop/work/datecoach/agents/social/Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# --- Dependency Installation ---
# Copy only the requirements file first to leverage Docker cache
COPY ./platform_mcp_client/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- Install a2a_common wheel ---
# Assuming the Docker build context is the repository root,
# and deploy_all.py has already built a2a_common_wheel into agents/app/dist/
COPY agents/app/dist/a2a_common-0.1.0-py3-none-any.whl /tmp/a2a_common.whl
RUN pip install --no-cache-dir /tmp/a2a_common.whl && \
    rm /tmp/a2a_common.whl

# --- Application Code ---
# Ensure this path is correct relative to the Docker build context (repo root)
COPY agents/platform_mcp_client /app/agents/platform_mcp_client

# --- Environment ---
ENV PYTHONPATH=/app/agents 


# Make port 8080 available to the world outside this container
# Cloud Run uses the PORT env var, but EXPOSE is good practice.
EXPOSE 8080

# --- Run the application ---
# Run a2a_server.py when the container launches
# Use the module execution '-m' which works well with the PYTHONPATH setup
CMD ["python", "-m", "platform_mcp_client.a2a_server"]
