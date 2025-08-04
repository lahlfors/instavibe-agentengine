# Use the official genai-toolbox image as the base
# Using a specific, recent version for stability.
FROM us-central1-docker.pkg.dev/database-toolbox/toolbox/toolbox:0.10.0

# Copy the custom tools.yaml configuration file into the container
# This file defines our Spanner source and our custom tools.
COPY tools.yaml /app/tools.yaml

# Set the working directory
WORKDIR /app

# Expose the default port for the toolbox service
EXPOSE 5000

# Set the command to run the toolbox, pointing to our custom configuration.
# The environment variables referenced inside tools.yaml (like ${COMMON_GOOGLE_CLOUD_PROJECT})
# will be injected into the Cloud Run service environment by the deploy_all.py script.
CMD ["./toolbox", "--tools-file", "/app/tools.yaml"]
