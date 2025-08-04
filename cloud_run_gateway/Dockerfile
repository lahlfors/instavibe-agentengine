# Use the official Python slim image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy just the requirements file to leverage Docker cache
COPY requirements.txt .

# CRITICAL FIX: Upgrade pip and setuptools before installing packages.
# This ensures the build environment can handle modern package specifications.
RUN pip install --upgrade pip setuptools

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
