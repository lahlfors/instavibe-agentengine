# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Add this line to declare the build argument
ARG CACHEBUSTER

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# --- NEW: Upgrade pip and setuptools ---
# Ensures the latest packaging standards are supported
RUN pip install --upgrade pip setuptools

# Install dependencies using the upgraded pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Make port 8080 available
# Cloud Run will set the PORT environment variable, which uvicorn will use.
EXPOSE 8080

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
