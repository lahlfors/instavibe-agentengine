# instavibe-bootstrap

This repository contains the necessary scripts and configurations to deploy the Instavibe application and its associated agents and services.

## Central Deployment Script (`deploy_all.py`)

A central Python script `deploy_all.py` is provided in the root directory to orchestrate the deployment of all components.
For containerized services (Instavibe App, Platform MCP Client, MCP Tool Server), the script utilizes **Google Cloud Build** to build the container images, which are then deployed to Google Cloud Run.

### Prerequisites

Before running the central deployment script, ensure you have the following:

1.  **Google Cloud SDK (`gcloud`)**: Installed and authenticated. You can find installation instructions [here](https://cloud.google.com/sdk/docs/install).
    *   Ensure you have logged in (`gcloud auth login`) and set your project (`gcloud config set project [YOUR_PROJECT_ID]`).
    *   The Cloud Build API must be enabled in your GCP project. You can enable it by visiting the Google Cloud Console or by running `gcloud services enable cloudbuild.googleapis.com`.
2.  **Python 3**: Installed on your system.
3.  **Project ID**: Your Google Cloud Project ID.
4.  **Region**: The Google Cloud region where you want to deploy the services (e.g., `us-central1`).

*Note on Docker: While Docker was previously required for local image builds, `deploy_all.py` now uses Google Cloud Build, which builds your images in the cloud. Therefore, a local Docker installation is generally not required to run the script. However, Docker might still be useful for local development and testing.*

### Usage

Navigate to the root directory of this repository and run the script as follows:

```bash
python deploy_all.py --project_id [YOUR_PROJECT_ID] --region [YOUR_REGION]
```

**Optional Flags:**

You can skip deploying certain parts of the application using the following flags:

*   `--skip_agents`: Skips the deployment of the Planner, Social, and Orchestrate agents.
*   `--skip_app`: Skips the deployment of the Instavibe App.
*   `--skip_platform_mcp_client`: Skips the deployment of the Platform MCP Client.
*   `--skip_mcp_tool_server`: Skips the deployment of the MCP Tool Server.

**Example:**

To deploy only the Instavibe App and the MCP Tool Server:

```bash
python deploy_all.py --project_id my-gcp-project --region us-central1 --skip_agents --skip_platform_mcp_client
```

## Manual Deployment

If you prefer to deploy components individually, follow the instructions below.

### Agents (Planner, Social, Orchestrate)

These agents are designed for deployment to Google Cloud Vertex AI Agent Engine.

1.  **Planner Agent:**
    *   Navigate to the agent's directory: `cd agents/planner`
    *   Run the deployment script: `python deploy.py --project_id [YOUR_PROJECT_ID] --region [YOUR_REGION]`
    *   The script will guide you through the deployment process.

2.  **Social Agent:**
    *   Navigate to the agent's directory: `cd agents/social`
    *   Run the deployment script: `python deploy.py --project_id [YOUR_PROJECT_ID] --region [YOUR_REGION]`
    *   The script will guide you through the deployment process.

3.  **Orchestrate Agent:**
    *   Navigate to the agent's directory: `cd agents/orchestrate`
    *   Run the deployment script: `python deploy.py --project_id [YOUR_PROJECT_ID] --region [YOUR_REGION]`
    *   The script will guide you through the deployment process.

### Dockerized Services (Instavibe App, Platform MCP Client, MCP Tool Server)

These services are deployed as Docker containers to Google Cloud Run using Google Cloud Build.

**General Steps:**

For each service:

1.  **Build and push the Docker image using Google Cloud Build:**
    Navigate to the service's directory (e.g., `cd instavibe/`) and run:
    ```bash
    gcloud builds submit --tag gcr.io/[PROJECT_ID]/[SERVICE_NAME] . --project [PROJECT_ID]
    ```
    Replace `[PROJECT_ID]` with your Google Cloud Project ID and `[SERVICE_NAME]` with the specific service name (e.g., `instavibe-app`). The `.` indicates that the build context (including the Dockerfile) is the current directory.

2.  **Deploy the image to Cloud Run:**
    ```bash
    gcloud run deploy [SERVICE_NAME] \
      --image gcr.io/[PROJECT_ID]/[SERVICE_NAME] \
      --platform managed \
      --region [REGION] \
      --project [PROJECT_ID] \
      --allow-unauthenticated
    ```
    Replace `[PROJECT_ID]`, `[SERVICE_NAME]`, and `[REGION]` accordingly. The `--allow-unauthenticated` flag makes the service publicly accessible; adjust as needed for your security requirements.

**Service-Specific Information:**

1.  **Instavibe App:**
    *   Service Name: `instavibe-app` (or your preferred name)
    *   Directory for `gcloud builds submit`: `instavibe/`
    *   Dockerfile Location: `instavibe/Dockerfile`

2.  **Platform MCP Client:**
    *   Service Name: `platform-mcp-client` (or your preferred name)
    *   Directory for `gcloud builds submit`: `agents/platform_mcp_client/`
    *   Dockerfile Location: `agents/platform_mcp_client/Dockerfile`

3.  **MCP Tool Server:**
    *   Service Name: `mcp-tool-server` (or your preferred name)
    *   Directory for `gcloud builds submit`: `tools/instavibe/`
    *   Dockerfile Location: `tools/instavibe/Dockerfile`

## Original Agent Deployment Note

The Planner, Social, and Orchestrate agents are designed for deployment to Google Cloud Vertex AI Agent Engine. Each of these agents includes a `deploy.py` script in its respective directory (`agents/<agent_name>/deploy.py`) to facilitate this deployment.

For other components, such as Instavibe, Platform MCP Client, and the MCP Tool Server, refer to their specific Dockerfiles and configurations for deployment details (typically for Cloud Run).
