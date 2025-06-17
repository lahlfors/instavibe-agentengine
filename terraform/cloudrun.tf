# Service Account for the main Instavibe Cloud Run application
resource "google_service_account" "instavibe_app_sa" {
  project      = var.project_id
  account_id   = var.cloud_run_sa_name # From variables.tf, e.g., "instavibe-app-sa"
  display_name = "Instavibe Application Service Account"
}

# IAM policy to allow the main Instavibe Cloud Run service to be invoked
# This example allows public (unauthenticated) access.
# For restricted access, replace "allUsers" with specific members or groups.
resource "google_cloud_run_v2_service_iam_member" "allow_public_invocations" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.instavibe_app.name # Depends on the Cloud Run service

  role   = "roles/run.invoker"
  member = "allUsers" # Caution: Makes the service publicly accessible

  depends_on = [google_cloud_run_v2_service.instavibe_app]
}

# Main Instavibe Application Cloud Run Service
resource "google_cloud_run_v2_service" "instavibe_app" {
  # Only deploy if the orchestrator agent (and its dependencies) are deployed and vars updated
  # This assumes the main app relies on the orchestrator.
  # If the app can run without agents, this count can be removed or adjusted.
  count    = var.orchestrator_agent_deployed_and_var_updated ? 1 : 0

  project  = var.project_id
  name     = "instavibe-app" # Consider making this a variable: var.instavibe_app_service_name
  location = var.region

  template {
    service_account = google_service_account.instavibe_app_sa.email

    scaling {
      min_instance_count = 0 # Can be 0 for cost savings, or 1 for reduced cold starts
      max_instance_count = 3 # Adjust as needed
    }

    containers {
      image = var.instavibe_app_image_url # Provided by CI/CD, defined in variables.tf

      ports {
        # Cloud Run injects the PORT env var with this value.
        # The application inside the container must listen on this port.
        container_port = var.app_container_port
      }

      # Environment variables for the Instavibe application
      env = [
        {
          name  = "COMMON_GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        },
        {
          name  = "COMMON_GOOGLE_CLOUD_LOCATION"
          value = var.region
        },
        {
          name  = "SPANNER_INSTANCE_ID"
          value = var.spanner_instance_name # Direct reference to var, or google_spanner_instance.main.name
        },
        {
          name  = "SPANNER_DATABASE_ID"
          value = var.spanner_database_name # Direct reference to var, or google_spanner_database.main.name
        },
        {
          name  = "ORCHESTRATE_AGENT_RESOURCE_NAME"
          value = var.orchestrate_agent_resource_name # Manually updated variable
        },
        {
          name  = "PLANNER_AGENT_RESOURCE_NAME"
          value = var.planner_agent_resource_name # Manually updated variable
        },
        {
          name  = "SOCIAL_AGENT_RESOURCE_NAME"
          value = var.social_agent_resource_name # Manually updated variable
        },
        {
          name  = "PLATFORM_MCP_CLIENT_AGENT_RESOURCE_NAME"
          value = var.platform_mcp_client_agent_resource_name # Manually updated variable
        },
        {
          name  = "LOG_LEVEL"
          value = var.app_log_level
        },
        {
          name  = "FLASK_SECRET_KEY"
          # For sensitive values like this, it's best to use Secret Manager.
          # This approach passes the value directly, which is less secure.
          # Terraform will mark it as sensitive in its output if var.flask_secret_key is sensitive.
          value = var.flask_secret_key
        }
        # The PORT environment variable is automatically injected by Cloud Run.
      ]

      # Example of mounting secrets from Google Secret Manager (Recommended for API keys, Flask Secret Key)
      # This requires the Secret Manager API to be enabled and the SA to have access.
      # env {
      #   name = "API_KEY_BACKEND_OPENAI"
      #   value_from {
      #     secret_key_ref {
      #       secret  = "openai-api-key" # Name of the secret in Secret Manager
      #       version = "latest"          # Version of the secret
      #     }
      #   }
      # }
      # env {
      #   name = "API_KEY_BACKEND_GEMINI"
      #   value_from {
      #     secret_key_ref {
      #       secret  = "gemini-api-key"
      #       version = "latest"
      #     }
      #   }
      # }
      # env {
      #   name = "FLASK_SECRET_KEY_FROM_SECRET_MANAGER" # Different name to avoid conflict if also direct
      #   value_from {
      #     secret_key_ref {
      #       secret  = "flask-secret-key"
      #       version = "latest"
      #     }
      #   }
      # }

      resources {
        limits = {
          cpu    = "1000m" # 1 CPU
          memory = "512Mi" # Adjust as needed
        }
      }
    }
  }

  # Define how traffic is routed. 100% to the latest revision.
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.run_api,
    google_service_account.instavibe_app_sa,
    google_spanner_database.main, # Ensure Spanner DB is available
    # Explicit dependency on null_resource.deploy_orchestrate_agent is implicitly handled by
    # the `var.orchestrator_agent_deployed_and_var_updated` flag in `count`.
    # However, if var.orchestrate_agent_resource_name was an output of a resource,
    # an explicit depends_on might be used.
  ]
}

# (Optional) Define Secret Manager secrets if you want Terraform to manage them
# resource "google_secret_manager_secret" "openai_api_key_secret" {
#   project_id = var.project_id
#   secret_id  = "openai-api-key" # Corresponds to secret_key_ref above
#   replication {
#     automatic = true
#   }
# }
# resource "google_secret_manager_secret_version" "openai_api_key_secret_version" {
#   secret      = google_secret_manager_secret.openai_api_key_secret.id
#   secret_data = var.openai_api_key # Value comes from sensitive Terraform variable
# }
# resource "google_secret_manager_secret_iam_member" "cloud_run_sa_access_openai_secret" {
#   project_id = var.project_id
#   secret_id  = google_secret_manager_secret.openai_api_key_secret.secret_id
#   role       = "roles/secretmanager.secretAccessor"
#   member     = "serviceAccount:${google_service_account.instavibe_app_sa.email}"
# }

# Repeat for gemini_api_key and flask_secret_key if managing them via Secret Manager through Terraform
```
