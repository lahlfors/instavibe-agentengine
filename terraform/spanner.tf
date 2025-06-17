resource "google_spanner_instance" "main" {
  project      = var.project_id
  name         = var.spanner_instance_name
  config       = var.spanner_config_name # e.g., "regional-us-central1"
  display_name = var.spanner_display_name
  num_nodes    = var.spanner_num_nodes

  labels = {
    env = "instavibe-app" # Example label
  }
}

resource "google_spanner_database" "main" {
  project      = var.project_id
  instance     = google_spanner_instance.main.name
  name         = var.spanner_database_name
  # ddl = [
  #   "CREATE TABLE users (userId STRING(36) NOT NULL,) PRIMARY KEY (userId)",
  #   "CREATE TABLE posts (postId STRING(36) NOT NULL, userId STRING(36) NOT NULL, content STRING(MAX),) PRIMARY KEY (postId)",
  # ] # Initial DDL can be placed here, but setup.py will handle it via local-exec
  deletion_protection = false # Set to true for production environments
}

# IAM policy for the application's Cloud Run service account to access Spanner
# This assumes the Cloud Run service account is created in cloudrun.tf
# and its email is accessible via an output or direct reference if defined in the same root module.
# For now, we use the variable `var.cloud_run_sa_name` to construct the email,
# assuming a consistent SA naming convention. A more robust way is to use output from SA resource.
#
# UPDATE: We will now directly reference google_service_account.instavibe_app_sa (defined in cloudrun.tf)
# This removes the need for the data source below.
#
# data "google_service_account" "cloud_run_sa_for_spanner" {
#   account_id = var.cloud_run_sa_name
#   project    = var.project_id
#   depends_on = [google_project_service.iam_api] # Ensure IAM API is enabled
# }


resource "google_spanner_database_iam_member" "db_user_for_cloud_run_app" {
  project  = var.project_id
  instance = google_spanner_instance.main.name
  database = google_spanner_database.main.name
  role     = "roles/spanner.databaseUser" # Provides R/W access. More granular roles: roles/spanner.databaseReader, roles/spanner.databaseWriter
  member   = "serviceAccount:${google_service_account.instavibe_app_sa.email}" # Direct reference to the SA defined in cloudrun.tf

  depends_on = [
    google_spanner_database.main,
    google_service_account.instavibe_app_sa # Ensure SA is created before attempting to bind
  ]
}

resource "google_spanner_instance_iam_member" "instance_user_for_cloud_run_app" {
  project  = var.project_id
  instance = google_spanner_instance.main.name
  role     = "roles/spanner.viewer" # Necessary for some operations like listing databases, sessions.
                                   # `roles/spanner.databaseUser` on the database is key for data access.
  member   = "serviceAccount:${google_service_account.instavibe_app_sa.email}" # Direct reference

  depends_on = [
    google_spanner_instance.main,
    google_service_account.instavibe_app_sa # Ensure SA is created before attempting to bind
  ]
}

# null_resource for running the Spanner schema setup script (instavibe/setup.py)
resource "null_resource" "db_schema_setup" {
  triggers = {
    # Re-run if the setup script changes
    setup_script_hash = filemd5("../instavibe/setup.py") # Assuming instavibe is one level up from terraform dir
    # Re-run if the requirements for the setup script change
    requirements_hash = fileexists("../instavibe/requirements.txt") ? filemd5("../instavibe/requirements.txt") : ""
    # Re-run if the Spanner database name or instance name changes, indicating a new DB might need setup
    database_name_trigger   = google_spanner_database.main.name
    instance_name_trigger = google_spanner_instance.main.name
  }

  provisioner "local-exec" {
    # Command to execute:
    # 1. Create/activate a Python virtual environment in the script's directory.
    # 2. Install dependencies from requirements.txt if it exists.
    # 3. Run the Python setup script.
    # Using python3 assuming it's available in the execution environment.
    command = <<EOT
      set -e
      cd ../instavibe
      if [ ! -d ".venv" ]; then
        python3 -m venv .venv
      fi
      source .venv/bin/activate
      if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
      fi
      python setup.py
    EOT

    # working_dir is implicitly ../instavibe due to `cd ../instavibe`
    # If not using `cd` in command, set: working_dir = "${path.module}/../instavibe"

    environment = {
      # GCP Context (passed to setup.py if it needs to interact with GCP APIs directly for setup)
      COMMON_GOOGLE_CLOUD_PROJECT  = var.project_id
      COMMON_GOOGLE_CLOUD_LOCATION = var.region

      # Spanner Specific details for the script
      SPANNER_PROJECT_ID           = var.project_id # Can be derived by script if running in GCP env
      SPANNER_INSTANCE_ID          = google_spanner_instance.main.name # Use the created instance name
      SPANNER_DATABASE_ID          = google_spanner_database.main.name # Use the created database name

      # Other relevant environment variables for the setup script
      LOG_LEVEL                    = var.app_log_level # Example
      # Ensure any sensitive vars needed by setup.py are handled securely if passed here
    }

    # Optional: Specify interpreter if not using bash/sh or if system default is not desired
    # interpreter = ["bash", "-c"]
  }

  # Ensure this runs only after the Spanner database resource is successfully created.
  depends_on = [
    google_spanner_database.main
  ]
}
