# Environment Variable Setup Guide

This guide provides instructions on how to obtain or define the values for each environment variable required by the project, as listed in the `.env.example` file.

## General Instructions

1.  **Copy `.env.example`**: If you haven't already, copy `.env.example` to a new file named `.env` in the project root:
    ```bash
    cp .env.example .env
    ```
2.  **Edit `.env`**: Open the `.env` file in a text editor and fill in the values as described below.
3.  **Security**: Treat your `.env` file as sensitive. It contains credentials and project-specific information. Ensure it is listed in your `.gitignore` file and is not committed to version control.

---

## Common Configuration

These variables are shared across multiple components of the application and **must be manually configured by you in your `.env` file.**

### `COMMON_GOOGLE_CLOUD_PROJECT`
*   **Purpose**: Your Google Cloud Project ID where all resources will be deployed and managed.
*   **How to obtain**:
    1.  If you have an existing project, you can find the Project ID on the [Google Cloud Console dashboard](https://console.cloud.google.com/home/dashboard).
    2.  If you need to create a new project, follow the instructions [here](https://cloud.google.com/resource-manager/docs/creating-managing-projects).
    *   Example: `my-gcp-project-12345`

### `COMMON_GOOGLE_CLOUD_PROJECT_NUMBER`
*   **Purpose**: The unique numerical identifier for your Google Cloud Project. Some Google Cloud services or permissions might require this.
*   **How to obtain**:
    1.  Go to the [Google Cloud Console dashboard](https://console.cloud.google.com/home/dashboard).
    2.  In the "Project info" card, you'll find the "Project number".
    3.  Alternatively, use the gcloud command: `gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)"` (replace `YOUR_PROJECT_ID` with your actual Project ID).
    *   Example: `123456789012`

### `COMMON_DEFAULT_COMPUTE_SERVICE_ACCOUNT`
*   **Purpose**: The email address of the default Compute Engine service account for your project. This is sometimes used by Google Cloud services for default credentials or permissions.
*   **How to obtain**:
    1.  In the Google Cloud Console, navigate to "IAM & Admin" > "Service Accounts".
    2.  Look for an account named "Compute Engine default service account". Its email will typically be in the format `PROJECT_NUMBER-compute@developer.gserviceaccount.com`.
    3.  Alternatively, use the gcloud command: `gcloud iam service-accounts list --filter="displayName:'Compute Engine default service account'" --format="value(email)"`
    *   Example: `123456789012-compute@developer.gserviceaccount.com`

### `COMMON_VERTEX_STAGING_BUCKET`
*   **Purpose**: A Google Cloud Storage (GCS) bucket URI used by Vertex AI for staging files, such as packaged code for custom models or reasoning engines.
*   **How to obtain**:
    1.  Create a GCS bucket in the same project and preferably in the same region as your Vertex AI deployments. See [Creating GCS Buckets](https://cloud.google.com/storage/docs/creating-buckets).
    2.  The value should be the GCS URI.
    *   Example: `gs://your-unique-bucket-name-for-vertex-staging`

### `COMMON_GOOGLE_CLOUD_LOCATION`
*   **Purpose**: The default Google Cloud region for deploying resources (e.g., Cloud Run services, Vertex AI Engines).
*   **How to obtain**: This is a region you choose. Common examples include `us-central1`, `europe-west1`, etc. Ensure the services you intend to use are available in the chosen region.
    *   Example: `us-central1`

### `COMMON_SPANNER_INSTANCE_ID`
*   **Purpose**: The ID of your Google Cloud Spanner instance used by the Instavibe application and Social Agent.
*   **How to obtain**:
    1.  If you don't have one, create a Spanner instance. See [Creating and managing instances](https://cloud.google.com/spanner/docs/create-manage-instances).
    2.  The Instance ID is chosen by you during creation.
    *   Example: `instavibe-graph-instance`

### `COMMON_SPANNER_DATABASE_ID`
*   **Purpose**: The ID of your Spanner database within the instance specified by `COMMON_SPANNER_INSTANCE_ID`.
*   **How to obtain**:
    1.  Create a database within your Spanner instance. See [Creating and managing databases](https://cloud.google.com/spanner/docs/create-manage-databases). The schema for this project is typically applied separately (e.g., via `instavibe/reset.sql` or similar setup scripts if provided).
    2.  The Database ID is chosen by you during creation.
    *   Example: `graphdb`

---

## Instavibe Application (`instavibe/app.py`)

These variables are primarily for the Instavibe web application and **should be manually configured by you in your `.env` file.**

### `INSTAVIBE_FLASK_SECRET_KEY`
*   **Purpose**: A secret key used by Flask to sign session cookies and for other security-related purposes.
*   **How to obtain**: Generate a strong random string. You can use Python to generate one:
    ```python
    import secrets
    secrets.token_hex(24)
    ```
    *   Example: `YOUR_INSTAVIBE_FLASK_SECRET_KEY_CHANGE_ME` (Replace this with your generated key)

### `INSTAVIBE_GOOGLE_MAPS_API_KEY`
*   **Purpose**: (Optional) Google Maps API Key for displaying maps in the Instavibe application.
*   **How to obtain**:
    1.  Enable the "Maps JavaScript API" (and potentially other Maps APIs like Geocoding, Places) in the [Google Cloud Console](https://console.cloud.google.com/google/maps-apis/overview).
    2.  Create an API key. See [Using API Keys](https://developers.google.com/maps/documentation/javascript/get-api-key).
    3.  **Important**: Restrict your API key to prevent unauthorized use (e.g., by HTTP referrers or API restrictions).
    *   Example: `AIzaSyYOUR_MAPS_API_KEY` (Leave blank if not using this feature)

### `INSTAVIBE_GOOGLE_MAPS_MAP_ID`
*   **Purpose**: (Optional) Google Maps Map ID for using custom map styles with the Maps JavaScript API.
*   **How to obtain**:
    1.  If you want to use custom map styles, create a Map ID in the [Google Cloud Console](https://console.cloud.google.com/google/maps-apis/client-side/mapids). See [Using Map IDs](https://developers.google.com/maps/documentation/javascript/map-ids).
    *   Example: `YOUR_MAP_ID_IF_ANY` (Leave blank if not using custom styles)

### `INSTAVIBE_APP_HOST`
*   **Purpose**: Host address for the Flask development server when running `instavibe/app.py` locally.
*   **Value**: Typically `0.0.0.0` to make it accessible from your network, or `127.0.0.1` for local access only. This is ignored by Gunicorn in Cloud Run (which uses `0.0.0.0`).
    *   Default: `0.0.0.0`

### `INSTAVIBE_APP_PORT`
*   **Purpose**: Port for the Flask development server when running `instavibe/app.py` locally.
*   **Value**: Any available port. This is overridden by the `PORT` environment variable in Cloud Run.
    *   Default: `8080`

---

## Agent Configuration: Dynamic vs. Static Values

**Important Note on Dynamic Configuration:** When deploying the full system using the `deploy_all.py` script, key agent identifiers (like their resource names on Vertex AI and the list of agents for the Orchestrator) are determined **dynamically** during the deployment process. These dynamic values are then used to configure inter-agent communication and the `instavibe-app`'s connections to the agents.

The corresponding static values in your `.env` file (e.g., `AGENTS_..._PUBLIC_URL`, `AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES`) are therefore primarily for:
*   Local development and testing of individual agents.
*   Direct interaction with an agent outside the `deploy_all.py` orchestrated system.
*   Serving as fallbacks if the dynamic deployment flow is not used or if an agent is run independently.

The `deploy_all.py` script will inject the dynamically obtained resource names (e.g., `AGENTS_PLANNER_RESOURCE_NAME`) as environment variables into the `instavibe-app` container during its deployment. The `instavibe-app` should be configured to use these `_RESOURCE_NAME` variables to connect to the agents via the Vertex AI SDK.

---

## Agent: Orchestrate (`agents/orchestrate/`)

### `AGENTS_ORCHESTRATE_GOOGLE_GENAI_USE_VERTEXAI`
*   **Purpose**: Boolean flag (`TRUE` or `FALSE`) to indicate if the agent should use Vertex AI for Google's generative AI models.
*   **Value**: Typically `TRUE` for this project.
    *   Default: `TRUE`

### `AGENTS_ORCHESTRATE_AGENT_BASE_URL`
*   **Purpose**: The base URL that the Orchestrate Agent might use to interact with other services (e.g., the Instavibe app API). This might be used if the Orchestrator needs to call back to the main application for certain tasks.
*   **Value**: Depends on where the target service (e.g., Instavibe) is running.
    *   Example for local: `http://localhost:8080`
    *   **Note for `deploy_all.py` users**: The `instavibe-app` does not typically need to know the Orchestrator's direct public URL for startup. Instead, other agents might be configured (dynamically or statically) with the Orchestrator's resource name or address if they need to call it. The Orchestrator's own outbound calls defined by this `_AGENT_BASE_URL` are for its tools, if any, to reach other services.

### `AGENTS_ORCHESTRATE_REMOTE_AGENT_ADDRESSES`
*   **Purpose**: A comma-separated list of public URLs or Vertex AI resource names for other agents that the Orchestrate Agent needs to communicate with.
*   **Value**:
    *   **When using `deploy_all.py`**: This value is **dynamically constructed** by `deploy_all.py`. It gathers the resource names of the Planner, Social, and Platform MCP Client agents after they are deployed and passes this comma-separated string to the Orchestrate agent's deployment. The static value in `.env` is ignored in this scenario for the Orchestrator's primary configuration.
    *   For local development or independent Orchestrator testing: You would manually provide the necessary agent endpoints or resource names here.
    *   Example (if set manually): `projects/YOUR_PROJECT/locations/us-central1/reasoningEngines/PLANNER_ID,projects/YOUR_PROJECT/locations/us-central1/reasoningEngines/SOCIAL_ID`
    *   The `.env.example` file has this commented out as it's typically set dynamically.

---

## Agent: Planner (`agents/planner/`)

### `AGENTS_PLANNER_GOOGLE_GENAI_USE_VERTEXAI`
*   **Purpose**: Boolean flag (`TRUE` or `FALSE`) for using Vertex AI with Google's generative models.
*   **Value**: Typically `TRUE`.
    *   Default: `TRUE`

### `AGENTS_PLANNER_GOOGLE_API_KEY`
*   **Purpose**: (Optional) Specific Google API key if the Planner agent requires one.
*   **How to obtain**: If needed, create an API key in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
    *   Example: `AIzaSyYOUR_PLANNER_SPECIFIC_API_KEY` (Leave blank if not needed or using ADC)

### `AGENTS_PLANNER_A2A_HOST`
*   **Purpose**: Hostname for local Agent-to-Agent (A2A) communication when running the Planner agent locally.
*   **Value**: `localhost`.
    *   Default: `localhost`

### `AGENTS_PLANNER_A2A_PORT`
*   **Purpose**: Port for local A2A communication for the Planner agent.
*   **Value**: An available port.
    *   Default: `10003`

### `AGENTS_PLANNER_PUBLIC_URL`
*   **Purpose**: The publicly accessible URL where the Planner agent is hosted.
*   **Value**:
    *   For local development (e.g., using ngrok): The ngrok forwarding URL.
    *   **Note for `deploy_all.py` users**: When `deploy_all.py` deploys the Planner agent, it captures the unique Vertex AI Reasoning Engine `resource_name`. This resource name (e.g., `AGENTS_PLANNER_RESOURCE_NAME`) is then injected as an environment variable into the `instavibe-app`. The `instavibe-app` should use this resource name to interact with the agent via the Vertex AI SDK. The static `AGENTS_PLANNER_PUBLIC_URL` in `.env` is thus superseded for this flow but can be used for direct testing.
    *   Example (local with ngrok): `http://your-ngrok-subdomain.ngrok.io`
    *   The `.env.example` file has this commented out as it's typically set dynamically for the `instavibe-app`.

---

## Agent: Platform MCP Client (`agents/platform_mcp_client/`)

### `AGENTS_PLATFORM_MCP_CLIENT_GOOGLE_GENAI_USE_VERTEXAI`
*   **Purpose**: Boolean flag (`TRUE` or `FALSE`) for Vertex AI.
*   **Value**: `TRUE`.
    *   Default: `TRUE`

### `AGENTS_PLATFORM_MCP_CLIENT_GOOGLE_API_KEY`
*   **Purpose**: (Optional) Specific Google API key for this agent.
*   **How to obtain**: See `AGENTS_PLANNER_GOOGLE_API_KEY`.
    *   Example: `AIzaSyYOUR_MCP_CLIENT_API_KEY`

### `AGENTS_PLATFORM_MCP_CLIENT_A2A_HOST`
*   **Purpose**: Hostname for local A2A communication.
*   **Value**: `localhost`.
    *   Default: `localhost`

### `AGENTS_PLATFORM_MCP_CLIENT_A2A_PORT`
*   **Purpose**: Port for local A2A communication.
*   **Value**: An available port.
    *   Default: `10002`

### `AGENTS_PLATFORM_MCP_CLIENT_PUBLIC_URL`
*   **Purpose**: Publicly accessible URL for this agent.
*   **Value**:
    *   See `AGENTS_PLANNER_PUBLIC_URL` for guidance on local vs. deployed values.
    *   **Note for `deploy_all.py` users**: Similar to the Planner agent, `deploy_all.py` captures the `resource_name` for the Platform MCP Client agent and provides it to the `instavibe-app` (as `AGENTS_PLATFORM_MCP_CLIENT_RESOURCE_NAME`) and to the Orchestrator agent. The static value in `.env` is primarily for local/direct testing.
    *   The `.env.example` file has this commented out.

### `AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL`
*   **Purpose**: The URL of the MCP Tool Server that this client agent will connect to. **This MUST be set correctly.**
*   **Value**:
    *   For local development: The URL where your `mcp_server.py` (from `tools/instavibe/`) is running, e.g., `http://localhost:8081/sse` (if the MCP server uses port 8081 and the SSE endpoint is `/sse`). *Ensure this port does not clash with other services like the Instavibe app itself.*
    *   When deployed: The public URL of your deployed MCP Tool Server on Cloud Run (e.g., `https://mcp-tool-server-YOUR_HASH-uc.a.run.app/sse`).
    *   Example (local): `http://localhost:8081/sse`

---

## Agent: Social (`agents/social/`)

### `AGENTS_SOCIAL_GOOGLE_GENAI_USE_VERTEXAI`
*   **Purpose**: Boolean flag (`TRUE` or `FALSE`) for Vertex AI.
*   **Value**: `TRUE`.
    *   Default: `TRUE`

### `AGENTS_SOCIAL_GOOGLE_API_KEY`
*   **Purpose**: (Optional) Specific Google API key for this agent.
*   **How to obtain**: See `AGENTS_PLANNER_GOOGLE_API_KEY`.
    *   Example: `AIzaSyYOUR_SOCIAL_AGENT_API_KEY`

### `AGENTS_SOCIAL_A2A_HOST`
*   **Purpose**: Hostname for local A2A communication.
*   **Value**: `localhost`.
    *   Default: `localhost`

### `AGENTS_SOCIAL_A2A_PORT`
*   **Purpose**: Port for local A2A communication.
*   **Value**: An available port.
    *   Default: `10001`

### `AGENTS_SOCIAL_PUBLIC_URL`
*   **Purpose**: Publicly accessible URL for this agent.
*   **Value**:
    *   See `AGENTS_PLANNER_PUBLIC_URL` for guidance on local vs. deployed values.
    *   **Note for `deploy_all.py` users**: Similar to other agents, `deploy_all.py` captures the `resource_name` for the Social agent and provides it to the `instavibe-app` (as `AGENTS_SOCIAL_RESOURCE_NAME`) and to the Orchestrator agent. The static value in `.env` is primarily for local/direct testing.
    *   The `.env.example` file has this commented out.
*   **Note**: This agent also uses `COMMON_SPANNER_INSTANCE_ID` and `COMMON_SPANNER_DATABASE_ID` for database access.

---

## Tools Configurations (`tools/`)

These settings are typically for tools used by agents, such as the `instavibe.py` tool functions called by the MCP Tool Server. **These should be manually configured by you in your `.env` file.**

### `TOOLS_GOOGLE_GENAI_USE_VERTEXAI`
*   **Purpose**: Boolean flag (`TRUE` or `FALSE`) if tools interacting with Google GenAI models should use Vertex AI.
*   **Value**: `TRUE`.
    *   Default: `TRUE`

### `TOOLS_GOOGLE_API_KEY`
*   **Purpose**: (Optional) A general Google API key that tools might use if they don't fall under a specific agent's key and don't use Application Default Credentials.
*   **How to obtain**: See `AGENTS_PLANNER_GOOGLE_API_KEY`.
    *   Example: `AIzaSyYOUR_TOOLS_API_KEY`

### `TOOLS_INSTAVIBE_BASE_URL`
*   **Purpose**: The base URL for the Instavibe API, used by tools that interact with the Instavibe application (e.g., `tools/instavibe/instavibe.py`).
*   **Value**:
    *   For local development: `http://localhost:8080/api` (if Instavibe runs on port 8080 and its API is at `/api`).
    *   When deployed: The public URL of your deployed Instavibe app's API (e.g., `https://instavibe-app-YOUR_HASH-uc.a.run.app/api`).
    *   Default: `http://localhost:8080/api`

---
