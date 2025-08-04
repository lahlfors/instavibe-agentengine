from typing import Optional, Dict
# In deploy_all.py
def build_and_deploy_cloud_run_service(
    project_id: str,
    region: str,
    service_name: str,
    source_path: str,
    env_vars: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Builds and deploys a Cloud Run service using the generic root cloudbuild.yaml.
    """
    logging.info(f"--- Deploying Cloud Run Service: {service_name} from path {source_path} ---")
    if not os.path.isdir(source_path):
        raise DeploymentError(f"Source path not found: {source_path}")

    image_path = f"{region}-docker.pkg.dev/{project_id}/instavibe-images/{service_name}:latest"

    # Start with the base substitutions
    substitutions = {
        "_IMAGE_PATH": image_path,
        "_AGENT_NAME": service_name,
        "_SERVICE_DIR": source_path,
        "_REGION": region,
    }

    # Add environment variables directly to the substitutions dictionary.
    # The key is prefixed with an underscore to match the YAML placeholder.
    if env_vars:
        for k, v in env_vars.items():
            if v is not None:  # Ensure value is not None
                substitutions[f"_{k}"] = str(v)

    # Convert the final substitutions dictionary to the format gcloud expects.
    substitutions_string = ",".join([f"{k}={v}" for k, v in substitutions.items()])

    build_submit_cmd = [
        "gcloud", "builds", "submit", ".",
        "--config", "cloudbuild.yaml",
        f"--substitutions={substitutions_string}",
        "--project", project_id,
    ]

    try:
        logging.info(f"Submitting build and deploy for {service_name} using root cloudbuild.yaml...")
        logging.info(f"Substitutions: {substitutions_string}")
        run_command(build_submit_cmd, timeout=900, check=True)
    except subprocess.CalledProcessError as e:
        raise DeploymentError(f"Cloud Build submission failed for {service_name}") from e

    # ... The rest of the function remains the same ...
    url_cmd = [
        "gcloud", "run", "services", "describe", service_name,
        "--platform", "managed", "--region", region, "--project", project_id,
        "--format=value(status.url)"
    ]
    try:
        result = run_command(url_cmd, check=True)
        service_url = result.stdout.strip()
        if not service_url:
            raise DeploymentError(f"Failed to get URL for Cloud Run service {service_name}")
        logging.info(f"Successfully deployed '{service_name}' to {service_url}")
        return service_url
    except (subprocess.CalledProcessError, DeploymentError) as e:
        logging.warning(f"Could not retrieve service URL for {service_name} after deployment. Error: {e}")
        return None
