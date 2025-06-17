# locals block for common paths to agent scripts and requirements files
locals {
  agents_root_dir                   = "${path.module}/../agents" # Assuming 'agents' dir is one level up from 'terraform'
  planner_agent_dir                 = "${local.agents_root_dir}/planner_agent"
  social_agent_dir                  = "${local.agents_root_dir}/social_agent"
  orchestrate_agent_dir             = "${local.agents_root_dir}/orchestrate_agent"
  platform_mcp_client_agent_dir     = "${local.agents_root_dir}/platform_mcp_client_agent"

  # Path to a potential root requirements file for all agents, if applicable
  # If agents have all their deps in their own requirements.txt, this might not be needed or can be an empty file.
  root_agent_requirements_file = "${local.agents_root_dir}/requirements.txt"
}

# --- 1. Planner Agent Deployment ---
resource "null_resource" "deploy_planner_agent" {
  triggers = {
    # Re-run if the main deployment script for this agent changes
    script_hash = filemd5("${local.planner_agent_dir}/main.py") # Adjust script name if different
    # Re-run if the agent's specific requirements file changes
    agent_requirements_hash = fileexists("${local.planner_agent_dir}/requirements.txt") ? filemd5("${local.planner_agent_dir}/requirements.txt") : ""
    # Re-run if a common root requirements file for agents changes
    root_agent_requirements_hash = fileexists(local.root_agent_requirements_file) ? filemd5(local.root_agent_requirements_file) : ""
    # Add other triggers like config files specific to this agent if any
  }

  provisioner "local-exec" {
    working_dir = local.planner_agent_dir
    command     = <<EOT
      set -e
      echo "Starting Planner Agent deployment script..."
      if [ ! -d ".venv" ]; then
        python3 -m venv .venv
      fi
      source .venv/bin/activate
      if [ -f "${local.root_agent_requirements_file}" ]; then
        echo "Installing dependencies from ${local.root_agent_requirements_file}..."
        pip install -r "${local.root_agent_requirements_file}"
      fi
      if [ -f "requirements.txt" ]; then
        echo "Installing dependencies from ${local.planner_agent_dir}/requirements.txt..."
        pip install -r requirements.txt
      fi
      echo "Running Planner Agent main deployment function..."
      # Assuming the Python script takes these arguments. Adjust as per actual script.
      python main.py deploy_planner_main_func \
        --project_id="${var.project_id}" \
        --region="${var.region}" \
        --base_dir="." \
        --vertex_ai_staging_bucket="${var.vertex_ai_staging_bucket}"
      echo "Planner Agent deployment script finished."
    EOT
    environment = {
      COMMON_GOOGLE_CLOUD_PROJECT    = var.project_id
      COMMON_GOOGLE_CLOUD_LOCATION   = var.region
      COMMON_VERTEX_STAGING_BUCKET = var.vertex_ai_staging_bucket
      LOG_LEVEL                      = var.app_log_level # If agent scripts use this
      # Any other specific env vars needed by this agent's deployment script
    }
  }

  depends_on = [
    null_resource.db_schema_setup, # If agents rely on DB schema being present
    google_project_service.aiplatform_api,
  ]
}

# --- 2. Social Agent Deployment ---
resource "null_resource" "deploy_social_agent" {
  triggers = {
    script_hash                  = filemd5("${local.social_agent_dir}/main.py")
    agent_requirements_hash      = fileexists("${local.social_agent_dir}/requirements.txt") ? filemd5("${local.social_agent_dir}/requirements.txt") : ""
    root_agent_requirements_hash = fileexists(local.root_agent_requirements_file) ? filemd5(local.root_agent_requirements_file) : ""
  }

  provisioner "local-exec" {
    working_dir = local.social_agent_dir
    command     = <<EOT
      set -e
      echo "Starting Social Agent deployment script..."
      if [ ! -d ".venv" ]; then
        python3 -m venv .venv
      fi
      source .venv/bin/activate
      if [ -f "${local.root_agent_requirements_file}" ]; then
        pip install -r "${local.root_agent_requirements_file}"
      fi
      if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
      fi
      python main.py deploy_social_main_func \
        --project_id="${var.project_id}" \
        --region="${var.region}" \
        --base_dir="." \
        --vertex_ai_staging_bucket="${var.vertex_ai_staging_bucket}"
      echo "Social Agent deployment script finished."
    EOT
    environment = {
      COMMON_GOOGLE_CLOUD_PROJECT    = var.project_id
      COMMON_GOOGLE_CLOUD_LOCATION   = var.region
      COMMON_VERTEX_STAGING_BUCKET = var.vertex_ai_staging_bucket
      LOG_LEVEL                      = var.app_log_level
    }
  }
  depends_on = [
    null_resource.db_schema_setup,
    google_project_service.aiplatform_api,
  ]
}

# --- 3. Platform MCP Client Agent Deployment ---
resource "null_resource" "deploy_platform_mcp_client_agent" {
  triggers = {
    script_hash                  = filemd5("${local.platform_mcp_client_agent_dir}/main.py")
    agent_requirements_hash      = fileexists("${local.platform_mcp_client_agent_dir}/requirements.txt") ? filemd5("${local.platform_mcp_client_agent_dir}/requirements.txt") : ""
    root_agent_requirements_hash = fileexists(local.root_agent_requirements_file) ? filemd5(local.root_agent_requirements_file) : ""
  }

  provisioner "local-exec" {
    working_dir = local.platform_mcp_client_agent_dir
    command     = <<EOT
      set -e
      echo "Starting Platform MCP Client Agent deployment script..."
      if [ ! -d ".venv" ]; then
        python3 -m venv .venv
      fi
      source .venv/bin/activate
      if [ -f "${local.root_agent_requirements_file}" ]; then
        pip install -r "${local.root_agent_requirements_file}"
      fi
      if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
      fi
      python main.py deploy_platform_mcp_client_main_func \
        --project_id="${var.project_id}" \
        --region="${var.region}" \
        --base_dir="." \
        --vertex_ai_staging_bucket="${var.vertex_ai_staging_bucket}"
      echo "Platform MCP Client Agent deployment script finished."
    EOT
    environment = {
      COMMON_GOOGLE_CLOUD_PROJECT    = var.project_id
      COMMON_GOOGLE_CLOUD_LOCATION   = var.region
      COMMON_VERTEX_STAGING_BUCKET = var.vertex_ai_staging_bucket
      LOG_LEVEL                      = var.app_log_level
    }
  }
  depends_on = [
    null_resource.db_schema_setup,
    google_project_service.aiplatform_api,
  ]
}

# --- 4. Orchestrate Agent Deployment ---
resource "null_resource" "deploy_orchestrate_agent" {
  # Only deploy if the tool agents are deployed and their resource name variables are updated
  count = var.tool_agents_deployed_and_vars_updated ? 1 : 0

  triggers = {
    script_hash                  = filemd5("${local.orchestrate_agent_dir}/main.py")
    agent_requirements_hash      = fileexists("${local.orchestrate_agent_dir}/requirements.txt") ? filemd5("${local.orchestrate_agent_dir}/requirements.txt") : ""
    root_agent_requirements_hash = fileexists(local.root_agent_requirements_file) ? filemd5(local.root_agent_requirements_file) : ""
    # Trigger re-deployment if any of the dependent agent resource names change
    planner_resource_name        = var.planner_agent_resource_name
    social_resource_name         = var.social_agent_resource_name
    platform_mcp_resource_name   = var.platform_mcp_client_agent_resource_name
  }

  # Construct the dynamic remote agent addresses string for the orchestrator's script
  # The Python script for the orchestrator will need to parse this.
  # Example format: "planner=projects/.../agents/id,social=projects/.../agents/id"
  # Ensure the Python script expects this format or adjust accordingly.
  locals {
    remote_agents_config_string = join(",", [
      "planner_agent_resource_name=${var.planner_agent_resource_name}",
      "social_agent_resource_name=${var.social_agent_resource_name}",
      "platform_mcp_client_agent_resource_name=${var.platform_mcp_client_agent_resource_name}"
    ])
  }

  provisioner "local-exec" {
    working_dir = local.orchestrate_agent_dir
    command     = <<EOT
      set -e
      echo "Starting Orchestrate Agent deployment script..."
      if [ ! -d ".venv" ]; then
        python3 -m venv .venv
      fi
      source .venv/bin/activate
      if [ -f "${local.root_agent_requirements_file}" ]; then
        pip install -r "${local.root_agent_requirements_file}"
      fi
      if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
      fi
      # Pass the constructed string of dependent agent resource names
      python main.py deploy_orchestrate_main_func \
        --project_id="${var.project_id}" \
        --region="${var.region}" \
        --base_dir="." \
        --vertex_ai_staging_bucket="${var.vertex_ai_staging_bucket}" \
        --remote_agent_config_string="${local.remote_agents_config_string}"
      echo "Orchestrate Agent deployment script finished."
    EOT
    environment = {
      COMMON_GOOGLE_CLOUD_PROJECT             = var.project_id
      COMMON_GOOGLE_CLOUD_LOCATION            = var.region
      COMMON_VERTEX_STAGING_BUCKET          = var.vertex_ai_staging_bucket
      LOG_LEVEL                               = var.app_log_level
      # Pass individual agent resource names also as env vars if script prefers/needs them that way too
      PLANNER_AGENT_RESOURCE_NAME           = var.planner_agent_resource_name
      SOCIAL_AGENT_RESOURCE_NAME            = var.social_agent_resource_name
      PLATFORM_MCP_CLIENT_AGENT_RESOURCE_NAME = var.platform_mcp_client_agent_resource_name
    }
  }

  depends_on = [
    null_resource.deploy_planner_agent,
    null_resource.deploy_social_agent,
    null_resource.deploy_platform_mcp_client_agent,
    google_project_service.aiplatform_api,
    # Implicit dependency on db_schema_setup through the tool agents
  ]
}
