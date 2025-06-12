# instavibe-bootstrap

This repository contains the necessary scripts and configurations to deploy the Instavibe application and its associated agents and services.

## Initial Environment Setup

Before deploying any components, you need to configure your environment. This project uses a central `.env` file in the project root to manage all necessary configurations, such as your Google Cloud Project ID, region, Spanner instance details, API keys, etc.

1.  **Create the `.env` file:**
    *   In the root directory of the project, make a copy of the example environment file:
        ```bash
        cp .env.example .env
        ```
2.  **Populate `.env`:**
    *   Open the newly created `.env` file with a text editor.
    *   Fill in the values for each variable. Pay close attention to key variables like `COMMON_GOOGLE_CLOUD_PROJECT`, `COMMON_GOOGLE_CLOUD_LOCATION`, `COMMON_VERTEX_STAGING_BUCKET`, Spanner IDs, and any necessary API keys or secrets as outlined in `.env.example`.
    *   For detailed guidance on how to obtain or define each of these values, please refer to the [Environment Variable Setup Guide](./ENVIRONMENT_SETUP_GUIDE.md).
    *   **Important:** Do not commit the `.env` file to version control. It should be listed in your `.gitignore` file.

3.  **Source Environment Variables and Configure `gcloud`:**
    *   A script `set_env.sh` is provided to source the variables from your `.env` file into your current shell session and configure the `gcloud` CLI to use your specified project.
    *   Run this script by sourcing it:
        ```bash
        source ./set_env.sh
        ```
    *   This script will:
        *   Load variables from your `.env` file, making them available in your shell.
        *   Check your `gcloud` authentication status.
        *   Set your active `gcloud` project to the `COMMON_GOOGLE_CLOUD_PROJECT` defined in your `.env` file.

With these steps completed, your environment is ready for deploying the application components.

## Central Deployment Script (`deploy_all.py`)

A central Python script `deploy_all.py` is provided in the root directory to orchestrate the deployment of all components.
The script deploys:
- Google Cloud Spanner instance and database (if they don't already exist, using `COMMON_SPANNER_INSTANCE_ID` and `COMMON_SPANNER_DATABASE_ID` from your `.env` file). Subsequently, it runs `instavibe/setup.py` to initialize the schema and populate data.
- Planner Agent (Vertex AI Agent Engine)
- Social Agent (Vertex AI Agent Engine)
- Orchestrate Agent (Vertex AI Agent Engine)
- Platform MCP Client Agent (Vertex AI Agent Engine)
- Instavibe App (Cloud Run, built via Google Cloud Build)
- MCP Tool Server (Cloud Run, built via Google Cloud Build)

### Prerequisites

Before running the central deployment script, ensure you have the following:

1.  **Completed Initial Environment Setup**: You must have created and populated the `.env` file and sourced it using `source ./set_env.sh` as described in the "Initial Environment Setup" section. This step loads necessary configurations like project ID, region, and staging bucket into your environment.
2.  **Google Cloud SDK (`gcloud`)**: Installed. Ensure you have authenticated at least once via `gcloud auth login`. The `set_env.sh` script handles setting the active project.
3.  **Enabled APIs**: The Cloud Build API (`cloudbuild.googleapis.com`), Vertex AI API (`aiplatform.googleapis.com`), and the Cloud Spanner API (`spanner.googleapis.com`) must be enabled in your GCP project. You can enable them by visiting the Google Cloud Console or by running `gcloud services enable cloudbuild.googleapis.com aiplatform.googleapis.com spanner.googleapis.com`.
4.  **Python 3**: Installed on your system.

*Note on Docker: While Docker was previously required for local image builds for some services, `deploy_all.py` now uses Google Cloud Build for containerized services, which builds your images in the cloud. Therefore, a local Docker installation is generally not required to run the script. However, Docker might still be useful for local development and testing of containerized components.*

### Usage

Navigate to the root directory of this repository and run the script as follows:

```bash
python deploy_all.py
```
The script utilizes configurations (like Project ID, Region, Staging Bucket) defined in your root `.env` file, which should have been sourced via `set_env.sh`.

**Optional Flags:**

You can skip deploying certain parts of the application using the following flags:

*   `--skip_agents`: Skips the deployment of the Planner, Social, Orchestrate, and Platform MCP Client agents.
*   `--skip_app`: Skips the deployment of the Instavibe App.
*   `--skip_platform_mcp_client`: Skips the deployment of the Platform MCP Client Agent. (Note: If `--skip_agents` is used, this agent is also skipped).
*   `--skip_mcp_tool_server`: Skips the deployment of the MCP Tool Server.

**Example:**

To deploy only the Instavibe App and the MCP Tool Server:

```bash
# Example: To deploy only the Instavibe App and the MCP Tool Server:
python deploy_all.py --skip_agents
```

## Manual Deployment

If you prefer to deploy components individually, follow the instructions below.

When deploying manually, it's crucial to first complete the "Initial Environment Setup" and source the `set_env.sh` script. This ensures that necessary environment variables (like `COMMON_GOOGLE_CLOUD_PROJECT`, `COMMON_GOOGLE_CLOUD_LOCATION`) are loaded into your shell and are available for the individual deployment scripts and `gcloud` commands.

### Agents (Planner, Social, Orchestrate, Platform MCP Client)

These agents are designed for deployment to Google Cloud Vertex AI Agent Engine. Each uses a `deploy.py` script and a `requirements.txt` file located in its respective directory.

1.  **Planner Agent:**
    *   Navigate to the agent's directory: `cd agents/planner`
    *   Run the deployment script: `python deploy.py`
    *   This script uses configurations from your sourced `.env` file.
    *   Requirements: `agents/planner/requirements.txt`

2.  **Social Agent:**
    *   Navigate to the agent's directory: `cd agents/social`
    *   Run the deployment script: `python deploy.py`
    *   This script uses configurations from your sourced `.env` file.
    *   Requirements: `agents/social/requirements.txt`

3.  **Orchestrate Agent:**
    *   Navigate to the agent's directory: `cd agents/orchestrate`
    *   Run the deployment script: `python deploy.py`
    *   This script uses configurations from your sourced `.env` file.
    *   Requirements: `agents/orchestrate/requirements.txt`

4.  **Platform MCP Client Agent:**
    *   Navigate to the agent's directory: `cd agents/platform_mcp_client`
    *   Run the deployment script: `python deploy.py`
    *   This script uses configurations from your sourced `.env` file.
    *   Requirements: `agents/platform_mcp_client/requirements.txt`

### Dockerized Services (Instavibe App, MCP Tool Server)

These services are deployed as Docker containers to Google Cloud Run using Google Cloud Build.

**General Steps:**

For each service:

1.  **Build and push the Docker image using Google Cloud Build:**
    Navigate to the service's directory (e.g., `cd instavibe/`) and run:
    ```bash
    gcloud builds submit --tag gcr.io/$COMMON_GOOGLE_CLOUD_PROJECT/[SERVICE_NAME] . --project $COMMON_GOOGLE_CLOUD_PROJECT
    ```
    (Ensure `COMMON_GOOGLE_CLOUD_PROJECT` is set in your shell by sourcing `set_env.sh`.)
    Replace `[SERVICE_NAME]` with the specific service name (e.g., `instavibe-app`). The `.` indicates that the build context (including the Dockerfile) is the current directory.

2.  **Deploy the image to Cloud Run:**
    ```bash
    gcloud run deploy [SERVICE_NAME] \
      --image gcr.io/$COMMON_GOOGLE_CLOUD_PROJECT/[SERVICE_NAME] \
      --platform managed \
      --region $COMMON_GOOGLE_CLOUD_LOCATION \
      --project $COMMON_GOOGLE_CLOUD_PROJECT \
      --allow-unauthenticated
    ```
    (Ensure `COMMON_GOOGLE_CLOUD_PROJECT` and `COMMON_GOOGLE_CLOUD_LOCATION` are set in your shell by sourcing `set_env.sh`.)
    Replace `[SERVICE_NAME]` accordingly. The `--allow-unauthenticated` flag makes the service publicly accessible; adjust as needed for your security requirements.
    Key environment variables required by the application (as defined in `.env.example`) must be available to the Cloud Run service. The `deploy_all.py` script handles this by passing them during deployment. If deploying manually, you will need to ensure these are set, for example, using the `--set-env-vars` flag with `gcloud run deploy` (e.g., `--set-env-vars "KEY1=VALUE1,KEY2=VALUE2"`) or by configuring them in the Cloud Console.

**Service-Specific Information:**

1.  **Instavibe App:**
    *   Service Name: `instavibe-app` (or your preferred name)
    *   Directory for `gcloud builds submit`: `instavibe/`
    *   Dockerfile Location: `instavibe/Dockerfile`

2.  **MCP Tool Server:**
    *   Service Name: `mcp-tool-server` (or your preferred name)
    *   Directory for `gcloud builds submit`: `tools/instavibe/`
    *   Dockerfile Location: `tools/instavibe/Dockerfile`

## Running Unit Tests

This project includes unit tests for the central deployment script (`deploy_all.py`). These tests verify the script's logic, such as command-line argument parsing and conditional dispatch to deployment functions, without performing actual deployments (as external calls are mocked).

### Prerequisites
- Python 3.x (the same version used for `deploy_all.py`)

### Executing Tests
To run the unit tests, navigate to the root directory of the repository and execute one of the following commands:

```bash
python -m unittest test_deploy_all.py
```
Or, since the test script `test_deploy_all.py` includes the standard `if __name__ == '__main__': unittest.main()` guard, you can also run it directly:
```bash
python test_deploy_all.py
```
The tests will run, and you should see output indicating the number of tests run and their status (e.g., "OK" if all pass, or details of failures).
