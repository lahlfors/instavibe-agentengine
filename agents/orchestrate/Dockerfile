# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by Python packages
# Example: RUN apt-get update && apt-get install -y --no-install-recommends some-lib && rm -rf /var/lib/apt/lists/*

# --- Dependency Installation ---
# Copy common library wheel first if it exists (after a2a_common refactor)
# COPY libs/instavibe_common_lib/dist/instavibe_common_lib-0.1.0-py3-none-any.whl /tmp/instavibe_common_lib.whl
# RUN pip install --no-cache-dir /tmp/instavibe_common_lib.whl && rm /tmp/instavibe_common_lib.whl
# Or, if a2a_common is still used and built:
COPY agents/app/dist/a2a_common-0.1.0-py3-none-any.whl /tmp/a2a_common.whl
RUN pip install --no-cache-dir /tmp/a2a_common.whl && rm /tmp/a2a_common.whl

# Copy only the requirements file next to leverage Docker cache for agent-specific dependencies
COPY agents/orchestrate/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# --- Application Code ---
# Copy the orchestrate agent's source code
# It needs access to its own code, and potentially other agents' code if there are direct imports (less ideal)
# For an A2A server, it primarily needs its own logic and the ADK agent it wraps.
COPY agents/orchestrate /app/agents/orchestrate
# If OrchestrateServiceAgent or HostAgent imports from other agent dirs directly (e.g. agents.social.some_utility),
# those would need to be copied too. Prefer installing dependencies or using A2A for inter-agent comms.
# For now, assuming OrchestrateServiceAgent is self-contained or its dependencies are via installed packages.

# If the ADK agent within OrchestrateServiceAgent (HostAgent) uses tools from other local modules
# not installed by pip (e.g. from `agents.planner` directly), those would also need to be copied.
# This is why `extra_packages` in ADK deployments often includes the whole `agents` directory.
# For a cleaner Dockerfile, it's better if these are proper packages or tool definitions are self-contained.
# For now, to mirror potential complexity of ADK deployment, let's copy the broader agents dir
# but set PYTHONPATH carefully.
COPY agents/planner /app/agents/planner
COPY agents/social /app/agents/social
# COPY agents/platform_mcp_client /app/agents/platform_mcp_client # If needed by orchestrator's tools

# --- Environment ---
# Set PYTHONPATH to allow imports from the /app directory where agents are structured.
# This helps find modules like agents.orchestrate.a2a_server
ENV PYTHONPATH=/app
# AGENT_SERVICE_NAME is used by the logging setup (potentially from a2a_common or replicated)
ENV AGENT_SERVICE_NAME="orchestrate-agent"
# AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES needs to be provided at runtime by Cloud Run
# A2A_PUBLIC_BASE_URL also needs to be provided at runtime (e.g. Cloud Run's $SERVICE_URL)

# Make port available (Cloud Run uses PORT env var, this is for documentation)
EXPOSE 8080

# --- Run the application ---
# Run the A2A server using Uvicorn.
# The PORT environment variable will be set by Cloud Run (defaults to 8080 locally).
CMD ["uvicorn", "agents.orchestrate.a2a_server:serve_app_factory()", "--host", "0.0.0.0", "--port", "$PORT", "--factory"]
# Note: The CMD needs a way to run the async serve() or get the app instance.
# A common way for uvicorn with an async factory is to use the --factory flag.
# This requires `a2a_server.py` to have a loadable factory function.

# Alternative CMD if a2a_server.py's `if __name__ == "__main__":` is the entry point:
# CMD ["python", "-m", "agents.orchestrate.a2a_server"]
# This is simpler if direct python module execution is preferred.
# Let's modify a2a_server.py to better support uvicorn factory loading for clarity.
