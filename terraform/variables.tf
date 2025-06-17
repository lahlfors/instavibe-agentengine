# --- GCP Project and Region ---
variable "project_id" {
  description = "The Google Cloud project ID where resources will be deployed."
  type        = string
  # No default, should be provided explicitly for each environment.
}

variable "region" {
  description = "The Google Cloud region for deploying resources."
  type        = string
  default     = "us-central1" # Or any other preferred default
}

# --- Spanner Configuration ---
variable "spanner_instance_name" {
  description = "The name/ID of the Spanner instance."
  type        = string
  default     = "instavibe-spanner-instance"
}

variable "spanner_config_name" {
  description = "The Spanner instance config (e.g., regional-us-central1). Should align with the project's region."
  type        = string
  default     = "regional-us-central1" # Adjust if your default region is different
}

variable "spanner_display_name" {
  description = "The display name for the Spanner instance in the GCP console."
  type        = string
  default     = "Instavibe Spanner Instance"
}

variable "spanner_num_nodes" {
  description = "The number of nodes to allocate for the Spanner instance."
  type        = number
  default     = 1
}

variable "spanner_database_name" {
  description = "The name/ID of the Spanner database."
  type        = string
  default     = "instavibe-db"
}

# --- Cloud Run Configuration ---
variable "instavibe_app_image_url" {
  description = "The full URL of the Instavibe application's container image in GCR or Artifact Registry. This is typically provided by a CI/CD pipeline."
  type        = string
  default     = "gcr.io/cloudrun/hello" # Placeholder; update with actual image URL
}

variable "cloud_run_sa_name" {
  description = "The name (account_id) for the Cloud Run service account for the main Instavibe app."
  type        = string
  default     = "instavibe-app-sa"
}

variable "app_container_port" {
  description = "The port inside the container on which the Instavibe application listens. Cloud Run automatically injects the PORT environment variable with this value."
  type        = number
  default     = 8080
}

# --- Application-Specific Environment Variables ---
variable "app_log_level" {
  description = "Application log level for the Instavibe app (e.g., INFO, DEBUG, WARNING, ERROR)."
  type        = string
  default     = "INFO"
}

variable "flask_secret_key" {
  description = "Secret key for Flask application session management and other security features. This is a sensitive value."
  type        = string
  sensitive   = true
  # No default; should be unique and strong, provided via secure means.
  # Example: "super-secret-random-string-generated-safely"
}

variable "gemini_api_key" {
  description = "API key for accessing Google Gemini services. This is a sensitive value."
  type        = string
  sensitive   = true
  # No default; provide via secure means.
}

# Add other application-specific variables as needed
# variable "some_other_app_setting" {
#   description = "Description of another application setting."
#   type        = string
#   default     = "default_value"
# }

# --- Vertex AI and Agent Configuration ---
variable "vertex_ai_staging_bucket" {
  description = "The GCS bucket name for Vertex AI to store staging artifacts for agent deployments and other operations. Should be globally unique if not prefixed with project ID by scripts."
  type        = string
  # Example: "your-project-id-vertex-ai-staging"
  # No default, as it often includes the project ID or a unique name.
}

variable "planner_agent_resource_name" {
  description = "The fully qualified resource name of the deployed Planner agent (e.g., projects/your-project/locations/your-region/agents/your-agent-id). This is manually updated after initial Planner agent deployment."
  type        = string
  default     = "" # To be updated in a .tfvars file or via environment variables after deployment.
}

variable "social_agent_resource_name" {
  description = "The fully qualified resource name of the deployed Social agent. Manually updated after its deployment."
  type        = string
  default     = ""
}

variable "platform_mcp_client_agent_resource_name" {
  description = "The fully qualified resource name of the deployed Platform MCP Client agent. Manually updated after its deployment."
  type        = string
  default     = ""
}

variable "orchestrate_agent_resource_name" {
  description = "The fully qualified resource name of the deployed Orchestrate agent. Manually updated after its deployment."
  type        = string
  default     = ""
}

# --- Control Flags for Phased Deployment ---
variable "tool_agents_deployed_and_vars_updated" {
  description = "Set to true after Planner, Social, and Platform MCP Client agents are deployed AND their respective Terraform resource name variables (e.g., var.planner_agent_resource_name) have been updated."
  type        = bool
  default     = false
}

variable "orchestrator_agent_deployed_and_var_updated" {
  description = "Set to true after the Orchestrate agent is deployed AND its Terraform resource name variable (var.orchestrate_agent_resource_name) has been updated."
  type        = bool
  default     = false
}
