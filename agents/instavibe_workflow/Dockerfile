# Dockerfile for Instavibe Workflow Agent

# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Define environment variable
ENV PORT 8080
ENV GOOGLE_CLOUD_PROJECT default-project
ENV COMMON_GOOGLE_CLOUD_LOCATION us-central1
ENV AGENT_USER_ID instavibe-workflow-agent-user # Default user_id for agent's own operations if needed

# Run main.py when the container launches
# Use Gunicorn for a production-ready WSGI server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "main:app"]
