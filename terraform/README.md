# Instavibe Application Infrastructure - Terraform Configuration

This directory contains the Terraform configuration for deploying the Instavibe application and its associated infrastructure on Google Cloud Platform (GCP). This includes:

- Google Spanner instance and database.
- Database schema initialization using a Python script.
- Vertex AI Agent deployments (Planner, Social, Platform MCP Client, Orchestrator) via local Python scripts.
- Google Cloud Run service for the main Instavibe application.
- Necessary IAM bindings and service accounts.

## Prerequisites

Before applying this Terraform configuration, ensure you have the following:

1.  **Terraform Installed**: Terraform version 1.0.0 or higher.
2.  **Google Cloud SDK (`gcloud`)**: Installed and configured. Authenticate with GCP:
    ```bash
    gcloud auth login
    gcloud auth application-default login
    ```
3.  **GCP Project**: A Google Cloud Project where the resources will be deployed. Ensure billing is enabled for this project.
4.  **Python Environment**: Python 3.8+ is required for the `local-exec` provisioners that deploy agents and set up the database schema. Ensure `python3` is in your PATH. Virtual environment creation (`venv`) and `pip` are also used.
5.  **Source Code**: The application source code, including the `instavibe/` and `agents/` directories, must be present relative to this `terraform/` directory as expected by the `local-exec` provisioners (e.g., `../instavibe/setup.py`, `../agents/planner_agent/main.py`).
6.  **Required APIs Enabled**: While the `main.tf` attempts to enable many necessary APIs, ensure the user or service account running Terraform has permissions to enable APIs (`serviceusage.services.enable`). If not, enable them manually in your GCP project beforehand:
    - Compute Engine API (`compute.googleapis.com`)
    - Identity and Access Management (IAM) API (`iam.googleapis.com`)
    - Cloud Run API (`run.googleapis.com`)
    - Spanner API (`spanner.googleapis.com`)
    - Artifact Registry API (`artifactregistry.googleapis.com`) (if using for Docker images)
    - Cloud Build API (`cloudbuild.googleapis.com`) (if using for Docker images via `gcloud builds submit` outside Terraform)
    - Vertex AI API (`aiplatform.googleapis.com`)
    - Secret Manager API (`secretmanager.googleapis.com`) (if using for managing secrets)
    - Cloud Resource Manager API (`cloudresourcemanager.googleapis.com`)

## Configuration

1.  **Copy Example tfvars**:
    Create a `terraform.tfvars` file from the example:
    ```bash
    cp terraform.tfvars.example terraform.tfvars
    ```

2.  **Edit `terraform.tfvars`**:
    Update `terraform.tfvars` with your specific configuration values:
    - `project_id`: Your GCP project ID.
    - `region`: The GCP region for deployment.
    - `spanner_instance_name`, `spanner_database_name`, etc.
    - `instavibe_app_image_url`: The full URL to your application's Docker image in GCR or Artifact Registry. This should be built by a separate CI/CD pipeline.
    - `vertex_ai_staging_bucket`: A unique GCS bucket name for Vertex AI staging.
    - Sensitive values like `flask_secret_key`, `openai_api_key`, `gemini_api_key`. **It is strongly recommended to manage these via a secure method like environment variables (`TF_VAR_name=value`) or a secrets manager instead of plain text in the `.tfvars` file for production.**

## Deployment - Multi-Step Process

This Terraform configuration uses `local-exec` provisioners to run Python scripts for deploying Vertex AI agents. These scripts generate resource names that are then needed by other parts of the configuration (e.g., the Orchestrator agent needing other agent names, the main app needing the Orchestrator name). Due to Terraform's execution model, this requires a multi-step apply process:

**Step 1: Initial Infrastructure and Tool Agent Deployment**

   - **Purpose**: Deploy Spanner, setup database schema, and deploy the "tool" agents (Planner, Social, Platform MCP Client). Their Python deployment scripts should output their fully qualified Vertex AI Agent resource names.
   - **Action**:
     1. Initialize Terraform:
        ```bash
        terraform init
        ```
     2. Apply the configuration. At this stage, `tool_agents_deployed_and_vars_updated` and `orchestrator_agent_deployed_and_var_updated` should be `false` (their default) in your `terraform.tfvars`.
        ```bash
        terraform apply
        ```
     3. **Collect Agent Resource Names**: Carefully observe the output of the `local-exec` scripts for the Planner, Social, and Platform MCP Client agents. Each script should print the generated Vertex AI resource name (e.g., `projects/your-project/locations/your-region/agents/your-agent-id`).
     4. **Update `terraform.tfvars`**:
        - Set `planner_agent_resource_name` with the collected Planner agent ID.
        - Set `social_agent_resource_name` with the collected Social agent ID.
        - Set `platform_mcp_client_agent_resource_name` with the collected Platform MCP Client agent ID.
        - Change `tool_agents_deployed_and_vars_updated` to `true`.

**Step 2: Deploy Orchestrator Agent**

   - **Purpose**: Deploy the Orchestrator agent, which depends on the resource names of the tool agents.
   - **Action**:
     1. Apply Terraform again. It will now detect the updated variables and the change to `tool_agents_deployed_and_vars_updated = true`, triggering the Orchestrator agent's deployment.
        ```bash
        terraform apply
        ```
     2. **Collect Orchestrator Agent Resource Name**: Observe the output of the Orchestrator agent's deployment script for its generated Vertex AI resource name.
     3. **Update `terraform.tfvars`**:
        - Set `orchestrate_agent_resource_name` with the collected Orchestrator agent ID.
        - Change `orchestrator_agent_deployed_and_var_updated` to `true`.

**Step 3: Deploy Main Instavibe Application**

   - **Purpose**: Deploy the main Instavibe Cloud Run application, which depends on the Orchestrator agent's resource name.
   - **Action**:
     1. Apply Terraform a final time. It will detect the update to `orchestrator_agent_deployed_and_var_updated = true` and deploy the `instavibe-app` Cloud Run service.
        ```bash
        terraform apply
        ```

After these steps, all infrastructure, agents, and the main application should be deployed.

## Key Files

- **`main.tf`**: Provider configuration, API enablement.
- **`variables.tf`**: All input variable definitions.
- **`spanner.tf`**: Spanner instance, database, IAM, and schema setup (`db_schema_setup` null_resource).
- **`cloudrun.tf`**: Instavibe Cloud Run service, service account, and related IAM.
- **`agents.tf`**: `null_resource` definitions for Vertex AI agent deployments.
- **`outputs.tf`**: Output values (e.g., Cloud Run URL).
- **`terraform.tfvars.example`**: Example variable file.
- **`README.md`**: This file.

## Cleaning Up

To destroy all resources managed by this Terraform configuration:

```bash
terraform destroy
```
Ensure that any manually set flags in `terraform.tfvars` (like `tool_agents_deployed_and_vars_updated`) are set to `false` or that the `count` meta-arguments on the resources are handled appropriately if you want to destroy resources in phases or if dependencies might prevent clean destruction in one go. For a full takedown, setting flags to allow all resources to be "visible" to Terraform during the destroy operation is best.

Be cautious with `terraform destroy` in a production environment. Ensure Spanner deletion protection is handled if enabled.
