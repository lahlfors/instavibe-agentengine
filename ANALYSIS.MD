# ANALYSIS.MD - System Refactoring and Architecture

## 1. Executive Summary of Refactoring

This project phase aimed to significantly refactor the multi-agent system to enhance modularity, standardize interactions with external systems like the MCP (Multi-Channel Platform), and align deployment practices with the recommended approaches for Vertex AI Agent Engine.

**Key Goals Achieved:**

*   **Decoupled Agent-to-Agent (A2A) Communication:** Moved from direct Python method calls between agents to a service-oriented architecture using HTTP calls.
*   **Standardized MCP Interaction:** Centralized the usage of the MCP Toolset within a dedicated client.
*   **Modernized Deployment:** Shifted from manual packaging and GAPIC client deployment to leveraging the more integrated `agent_engines.create()` Python SDK method for deploying agent objects directly to Vertex AI Agent Engine.

**Summary of Key Changes:**

*   **`A2AClient` Introduction:** A new client, `agents.app.common.a2a_client.A2AClient`, was introduced to manage HTTP-based communication between the Orchestrator and other specialized agent services.
*   **`MCPClient` Introduction:** The `agents.platform_mcp_client.mcp_client.MCPClient` was created to encapsulate all interactions with the MCP Toolset, providing a standardized way for the Platform agent to access MCP tools.
*   **Local FastAPI Test Services:** For each agent (Planner, Social, Platform, and Orchestrator), a `main_<agent_name>_service.py` file was created. These FastAPI applications serve primarily for local development, testing, and as an alternative deployment model.
*   **Deployment with `agent_engines.create()`:** The core deployment strategy for all agents (Planner, Social, Platform, Orchestrator) was refactored to use `vertexai.preview.agent_engines.create()`. This method deploys Python agent *objects* directly, with Vertex AI Agent Engine managing the serving environment and HTTP endpoint exposure.

These changes result in a more robust, scalable, and maintainable system, with clearer separation of concerns and alignment with best practices for Vertex AI.

## 2. Refactored A2A Communication

The communication between agents, particularly from the Orchestrator to the specialized agents (Planner, Social, Platform), has been fundamentally redesigned.

*   **`A2AClient` (`agents.app.common.a2a_client.A2AClient`):**
    *   This client is responsible for all outgoing HTTP requests from an agent (primarily the Orchestrator) to other agent services.
    *   It uses the `httpx` library for asynchronous HTTP POST calls, ensuring non-blocking operations.
    *   Target agent service URLs are dynamically configured at runtime via environment variables (e.g., `PLANNER_AGENT_SERVICE_URL`, `SOCIAL_AGENT_SERVICE_URL`, `PLATFORM_AGENT_SERVICE_URL`), which are set during the Orchestrator's deployment.
    *   **Target Endpoint:** The client now targets the standard Agent Engine `:query` method URL: `https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}:query`.
    *   **Request Payload:** The JSON payload sent by `A2AClient` is structured as `{"input": {"query": "...", "session_id": "..."}}` (with `session_id` being optional within the `input` object). This matches the way arguments are passed to the deployed agent's underlying `query` (or `async_query`) method by the Agent Engine's generic HTTP server.
    *   **Response Parsing:** `A2AClient` now expects the HTTP response from the Agent Engine endpoint to directly contain the JSON output of the agent's own `async_query` method (i.e., the `{"output": ..., "error": ...}` dictionary). Previous logic for checking a `predictions[0]` wrapper has been removed.
    *   **Authentication:** The `A2AClient`, through `httpx`, relies on Application Default Credentials (ADC) for authenticating calls to Google Cloud APIs, including Agent Engine endpoints. For local development, `gcloud auth application-default login` should be used. In GCP environments, ADC is typically available automatically to the service account running the code.

*   **Orchestrator Integration:**
    *   The `execute_planner_node`, `execute_social_node`, and `execute_platform_node` functions within the Orchestrator's LangGraph graph (defined in `agents/orchestrate/orchestrator_nodes.py` and used by `agents/app/graph_builder.py`) now utilize an instance of `A2AClient`.
    *   Instead of directly instantiating and calling methods on `PlannerAgent`, `SocialAgent`, or `PlatformAgent`, these nodes now use `await a2a_client.invoke_agent(agent_name, query, session_id)` to delegate tasks.

## 3. Standardized MCP Protocol Usage

Interaction with the MCP (Multi-Channel Platform, e.g., Instavibe) has been standardized and encapsulated.

*   **`MCPClient` (`agents.platform_mcp_client.mcp_client.MCPClient`):**
    *   This dedicated client is now the sole interface for interacting with the MCP.
    *   It internally manages the `MCPToolset` from the `google-adk` library. It attempts to initialize the real `MCPToolset` if available (via `google.adk.tools.mcp_tool.mcp_toolset`) and configured with a server URL (via the `AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL` environment variable).
    *   If the real `MCPToolset` cannot be initialized, `MCPClient` gracefully falls back to a dummy implementation, ensuring the Platform agent can still operate (albeit with mock data) for testing or when MCP is unavailable.
    *   `MCPClient` exposes the MCP functionalities as a list of LangChain `BaseTool` instances, making them readily usable within a LangChain agent or graph.

*   **Platform Agent Integration (`agents.platform_mcp_client.platform_node.py`):**
    *   The Platform agent's core logic (within `PlatformAgent` which utilizes the graph defined in `platform_node.py`) initializes `MCPClient`.
    *   It retrieves the LangChain tools from `MCPClient` and uses them within its LangGraph graph to handle user requests related to MCP actions (e.g., creating posts, events). This decouples the Platform agent's graph logic from the direct specifics of `MCPToolset` initialization.

## 4. Local Development and Testing (FastAPI Services)

To facilitate local development, iterative testing, and provide a clear service contract, FastAPI services were created for each agent:

*   **`main_<agent_name>_service.py` Files:**
    *   Located in each agent's directory (e.g., `agents/planner/main_planner_service.py`, `agents/orchestrate/main_orchestrator_service.py`).
    *   Each file defines a minimal FastAPI application that wraps its respective agent (e.g., `PlannerAgent`, `OrchestrateServiceAgent`).
    *   They expose a common endpoint structure, typically `/agents/{agent_name}/invoke`, which accepts a JSON payload and calls the agent's `async_query` method.

*   **Primary Role:**
    *   **Local Development & Testing:** These services allow developers to run individual agents (or the entire ensemble if service URLs are configured locally via environment variables) on their local machines using Uvicorn. This enables rapid iteration, debugging, and unit/integration testing of agent logic via standard HTTP calls.
    *   **Alternative Deployment Option:** While not the primary path for Vertex AI Agent Engine, these FastAPI apps could be containerized and deployed to other environments like Google Cloud Run, Kubernetes, or VMs if needed.

*   **Clarification on Deployment to Agent Engine:**
    *   These FastAPI applications (`main_<agent_name>_service.py` and their Uvicorn servers) are **not** what is directly deployed to Vertex AI Agent Engine when using the `vertexai.preview.agent_engines.create()` method.
    *   Instead, `agent_engines.create()` deploys the Python agent *object* itself, and Agent Engine provides its own managed HTTP server to expose that object.

## 5. Deployment to Vertex AI Agent Engine (Using `agent_engines.create()`)

The deployment strategy for all agents has been standardized to use the `vertexai.preview.agent_engines.create()` Python SDK method, which simplifies and streamlines the process.

*   **Core Method:** All per-agent `deploy.py` scripts (in `agents/planner/`, `agents/social/`, `agents/platform_mcp_client/`, `agents/orchestrate/`) now use `agent_engines.create()` as their central deployment mechanism.

*   **Deployed Artifact:**
    *   The primary argument to `agent_engines.create()` is `local_agent_instance`, which is an *instance* of the agent class (e.g., `PlannerAgent()`, `OrchestrateServiceAgent()`).
    *   Vertex AI Agent Engine handles the pickling of this Python object, packaging it with its dependencies, and deploying it into a managed runtime. Agent Engine then wraps this deployed object with its own internal HTTP server to make it invokable.

*   **Parameters for `agent_engines.create()`:**
    *   **`requirements`**: A Python list of package dependencies (e.g., `["google-cloud-aiplatform[agent_engines,langgraph]==1.96.0", "httpx==0.25.0"]`). These lists *exclude* `fastapi` and `uvicorn` for this deployment method.
    *   **`extra_packages`**: A list of local directory or file paths for Python source code that the agent depends on. This includes the agent's own code directory, shared modules (e.g., `agents/app/common/`), and the `agents/a2a_common-0.1.0-py3-none-any.whl` file. For the Orchestrator, this also includes paths to the node definition files of other agents as these are imported by its graph builder.
    *   **`env_vars`**: A dictionary for setting agent-specific and inter-agent URL environment variables.

*   **`deploy_all.py` Role:**
    *   The main `deploy_all.py` script orchestrates the deployment process by calling the updated per-agent deployment functions.
    *   **Service URL Discovery:**
        *   Each per-agent deployment function returns a `RemoteAgent` object.
        *   `deploy_all.py` uses `extract_service_url_from_deployment_info(remote_agent_object, agent_name)` to derive the invokable HTTP URL.
        *   This function constructs the URL in the format `https://{location}-aiplatform.googleapis.com/v1beta1/{resource_name}:query`. The `resource_name` (e.g., `projects/PROJECT_ID/locations/LOCATION/reasoningEngines/REASONING_ENGINE_ID`) is obtained from `remote_agent_object.resource_name`, and `location` is parsed from this string. This provides a deterministic method for URL construction.
    *   **Orchestrator Configuration:** `deploy_all.py` passes the collected Planner, Social, and Platform agent service URLs as environment variables to the Orchestrator agent during its deployment via the `env_vars` parameter of `agent_engines.create()`.

## 6. Environment Variable Management for Deployed Services

Proper management of environment variables is crucial for the configuration, security, and portability of deployed services.

*   **Vertex AI Agent Engine Deployments:**
    *   **Warning:** Users should not set system-reserved environment variables like `GOOGLE_CLOUD_PROJECT`, `PORT`, `GOOGLE_APPLICATION_CREDENTIALS`, etc., or use the prefix `GOOGLE_CLOUD_AGENT_ENGINE`.
    *   The project's per-agent `deploy.py` scripts comply by only setting custom, application-specific environment variables (e.g., `AGENTS_PLATFORM_MCP_CLIENT_MCP_SERVER_URL` for the Platform Agent; service URLs for the Orchestrator Agent).
    *   The Agent Engine runtime provides necessary system variables for its managed HTTP server.

*   **Cloud Run Deployments (Instavibe App & MCP Tool Server):**
    *   `deploy_all.py` no longer explicitly sets project, location, or port variables for these services.
    *   Applications on Cloud Run rely on the runtime for project/location context and use the `PORT` variable set by Cloud Run.
    *   Application-specific environment variables (database details, API keys, `TOOLS_INSTAVIBE_BASE_URL`) continue to be set by `deploy_all.py`.

*   **General Recommendations:**
    *   Rely on platform-provided environment variables for system configurations where available.
    *   Use distinct, application-specific naming for custom environment variables.

## 7. ADK Dependency Management (Post-Refactoring)

*   **Deployment SDK:** The primary SDK for deploying agents to Vertex AI Agent Engine is `google-cloud-aiplatform`, specifically with extras like `[agent_engines,langgraph]`.
*   **`MCPClient`:** Encapsulates the `google-adk` dependency for `MCPToolset`, isolating it to the Platform agent's context.
*   **`a2a_common.whl`:** Included in `extra_packages` for Agent Engine deployments, providing shared utilities or ensuring runtime compatibility.
*   **ADK-Independence:** Core A2A communication (via `A2AClient` and `httpx`) and the local FastAPI services are ADK-independent.

## 8. LangGraph Compatibility

The internal architecture of the agents, particularly their use of LangGraph for defining execution flows and managing state, remains unchanged and fully compatible with this refactoring. The refactoring effort concentrated on inter-component communication and the deployment model, not the graph definitions themselves. The power and flexibility of LangGraph for defining complex agent behaviors within each service are retained.

---
