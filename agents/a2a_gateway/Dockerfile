# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the requirements file and the wheel file into the container
COPY requirements.txt ./
COPY a2a_common-0.1.0-py3-none-any.whl ./

# Install the wheel file and the other requirements
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir a2a_common-0.1.0-py3-none-any.whl
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /usr/src/app
COPY . .

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Run a2a_server.py when the container launches
CMD ["uvicorn", "a2a_server:app", "--host", "0.0.0.0", "--port", "8080"]
