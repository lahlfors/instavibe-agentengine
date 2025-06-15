# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
# Ensures Python output is sent straight to terminal without being buffered
ENV PYTHONUNBUFFERED 1
# Recommended for K_SERVICE, K_REVISION, PORT with Cloud Run
ENV K_SERVICE=langgraph-orchestrator
ENV K_REVISION=1.0.0
ENV PORT=8080

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
# Assuming requirements.txt is at the root of the 'agents' directory (context of Docker build)
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Ensure langgraph, fastapi, uvicorn, pydantic, python-dotenv, langchain-google-genai are in requirements.txt
# Also, google-cloud-aiplatform (for ADK/Vertex AI specific parts if any are still used or for langgraph interactions with Vertex)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
# This will copy the entire 'agents' directory content into /app in the container if build context is parent of 'agents'.
# If build context is 'agents/' directory itself, then '.' refers to 'agents/'.
# Assuming the Docker build command is run from the parent directory of 'agents/' (e.g., the repo root),
# and we want to copy the 'agents' directory content into /app.
COPY ./agents /app

# If the Docker build command is run from within the 'agents' directory itself:
# COPY . .

# Make port from ENV PORT available to the world outside this container
EXPOSE ${PORT}

# Define environment variable for the application (example)
# ENV GOOGLE_APPLICATION_CREDENTIALS="/app/path/to/your/service-account-key.json" # If needed and not using workload identity

# Run main.py when the container launches
# main.py is now at /app/main.py because we copied 'agents' content into '/app'
CMD ["python", "main.py"]
