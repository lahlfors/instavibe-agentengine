import os
import uuid
from urllib.parse import urlparse
import cloudpickle
import tarfile
import tempfile
import shutil # For shutil.copy and shutil.copytree

from google.cloud import aiplatform as vertexai # Standard alias
from google.cloud.aiplatform_v1.services import reasoning_engine_service
from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC
from google.cloud.aiplatform_v1.types import ReasoningEngineSpec
from google.cloud import storage
import google.auth # For google.auth.exceptions
from dotenv import load_dotenv # For loading .env file

from agents.planner.planner_agent import PlannerAgent

# Load environment variables from the root .env file
# This ensures that any implicit environment variable reads by underlying
# libraries (e.g., Google Cloud clients if project_id isn't explicit everywhere)
# are configured from the root .env.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

def deploy_planner_main_func(project_id: str, region: str, base_dir: str):
    """
    Deploys the Planner Agent as a Vertex AI Reasoning Engine using GAPIC client,
    packaging the agent's source code and local wheel dependency.
    """
    display_name = "Planner Agent"
    description = """This agent helps users plan activities and events, considering their interests, budget, and location. It can generate creative and fun plan suggestions."""

    staging_bucket_uri = vertexai.initializer.global_config.staging_bucket
    if not staging_bucket_uri:
        raise ValueError("Vertex AI staging bucket is not set. Please configure it via aiplatform.init(staging_bucket='gs://your-bucket').")

    parsed_uri = urlparse(staging_bucket_uri)
    bucket_name = parsed_uri.netloc
    bucket_prefix = parsed_uri.path.lstrip('/')
    if bucket_prefix and not bucket_prefix.endswith('/'):
        bucket_prefix += '/'

    try:
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)
    except google.auth.exceptions.DefaultCredentialsError as e:
        print(f"ERROR: Google Cloud Default Credentials not found. {e}")
        print("Please ensure you have authenticated via `gcloud auth application-default login` "
              "or set the GOOGLE_APPLICATION_CREDENTIALS environment variable.")
        raise

    planner_agent_instance = PlannerAgent()

    pickled_agent_filename = f"planner_agent_pickle_{uuid.uuid4()}.pkl"
    gcs_pickle_path = os.path.join(bucket_prefix, 'reasoning_engine_packages', pickled_agent_filename)
    blob_pickle = bucket.blob(gcs_pickle_path)
    with blob_pickle.open("wb") as f:
        cloudpickle.dump(planner_agent_instance, f)
    pickle_object_gcs_uri = f"gs://{bucket_name}/{gcs_pickle_path}"
    print(f"Uploaded pickled agent to {pickle_object_gcs_uri}")

    # --- Handle dependencies (wheel and agent source code) ---
    local_wheel_filename = "a2a_common-0.1.0-py3-none-any.whl"
    local_wheel_path = os.path.join(base_dir, "agents", local_wheel_filename)
    if not os.path.exists(local_wheel_path):
        raise FileNotFoundError(f"Local wheel {local_wheel_path} not found. Expected in 'agents' directory relative to base_dir.")

    agents_dir_source_path = os.path.join(base_dir, "agents")
    if not os.path.isdir(agents_dir_source_path):
        raise FileNotFoundError(f"Source 'agents' directory {agents_dir_source_path} not found.")

    dependency_files_gcs_uri = None
    with tempfile.TemporaryDirectory() as temp_dir_for_tar:
        # Copy the wheel into the temp directory root
        copied_wheel_path = os.path.join(temp_dir_for_tar, local_wheel_filename)
        shutil.copy(local_wheel_path, copied_wheel_path)

        # Copy the 'agents' directory into the temp directory, maintaining its structure
        temp_agents_dir_dest_path = os.path.join(temp_dir_for_tar, "agents")
        print(f"Copying source 'agents' directory from {agents_dir_source_path} to {temp_agents_dir_dest_path} for tarball...")
        shutil.copytree(agents_dir_source_path, temp_agents_dir_dest_path, dirs_exist_ok=True)

        tarball_local_filename = f"dependencies_pkg_src_{uuid.uuid4()}.tar.gz"
        tarball_local_path = os.path.join(tempfile.gettempdir(), tarball_local_filename)

        print(f"Creating tarball {tarball_local_path} containing {local_wheel_filename} and agents/ directory...")
        with tarfile.open(tarball_local_path, "w:gz") as tar:
            # Add the wheel to the root of the tarball
            tar.add(copied_wheel_path, arcname=local_wheel_filename)
            # Add the 'agents' directory (containing all agent code) to the root of the tarball
            tar.add(temp_agents_dir_dest_path, arcname="agents")

        gcs_tarball_path = os.path.join(bucket_prefix, 'reasoning_engine_dependencies', tarball_local_filename)
        blob_tarball = bucket.blob(gcs_tarball_path)
        print(f"Uploading {tarball_local_path} to gs://{bucket_name}/{gcs_tarball_path}...")
        blob_tarball.upload_from_filename(tarball_local_path)
        dependency_files_gcs_uri = f"gs://{bucket_name}/{gcs_tarball_path}"
        print(f"Uploaded dependency tarball to {dependency_files_gcs_uri}")

        os.remove(tarball_local_path)
    # --- End handle dependencies ---

    original_requirements_file_path = os.path.join(base_dir, "agents/planner/requirements.txt")
    if not os.path.exists(original_requirements_file_path):
        raise FileNotFoundError(f"Original requirements file {original_requirements_file_path} not found.")

    with open(original_requirements_file_path, "r") as f:
        original_requirements_lines = f.readlines()

    modified_requirements_lines = []
    found_gcs_package = False
    replaced_local_wheel_in_reqs = False

    for line in original_requirements_lines:
        stripped_line = line.strip()
        if local_wheel_filename in stripped_line:
            modified_requirements_lines.append(f"{local_wheel_filename}\n")
            print(f"Modified requirements: Replaced '{stripped_line}' with '{local_wheel_filename}'.")
            replaced_local_wheel_in_reqs = True
        else:
            modified_requirements_lines.append(line)

        if "google-cloud-storage" in stripped_line:
            found_gcs_package = True

    if not replaced_local_wheel_in_reqs:
        print(f"Warning: Local wheel reference for '{local_wheel_filename}' not found to replace in {original_requirements_file_path}. Appending filename directly.")
        modified_requirements_lines.append(f"{local_wheel_filename}\n")

    if not found_gcs_package:
        print("Adding 'google-cloud-storage' to requirements for GCS URI handling.")
        modified_requirements_lines.append("google-cloud-storage\n")

    modified_requirements_content = "".join(modified_requirements_lines)

    print("---- BEGIN Modified requirements.txt content ----")
    print(modified_requirements_content)
    print("---- END Modified requirements.txt content ----")

    gcs_requirements_filename = f"planner_requirements_modified_{uuid.uuid4()}.txt"
    gcs_requirements_path = os.path.join(bucket_prefix, 'reasoning_engine_packages', gcs_requirements_filename)

    blob_reqs = bucket.blob(gcs_requirements_path)
    print(f"Uploading modified requirements to gs://{bucket_name}/{gcs_requirements_path}...")
    blob_reqs.upload_from_string(modified_requirements_content)
    requirements_gcs_uri = f"gs://{bucket_name}/{gcs_requirements_path}"
    print(f"Uploaded modified requirements to {requirements_gcs_uri}")

    current_package_spec = ReasoningEngineSpec.PackageSpec(
        pickle_object_gcs_uri=pickle_object_gcs_uri,
        requirements_gcs_uri=requirements_gcs_uri,
        dependency_files_gcs_uri=dependency_files_gcs_uri,
        python_version="3.12"
    )

    reasoning_engine_spec = ReasoningEngineSpec(
        package_spec=current_package_spec
    )

    gapic_reasoning_engine_config = ReasoningEngineGAPIC(
        display_name=display_name,
        description=description,
        spec=reasoning_engine_spec
    )

    print(f"Initializing GAPIC ReasoningEngineServiceClient with endpoint: {region}-aiplatform.googleapis.com")
    client_options = {"api_endpoint": f"{region}-aiplatform.googleapis.com"}
    gapic_client = reasoning_engine_service.ReasoningEngineServiceClient(client_options=client_options)

    parent_path = f"projects/{project_id}/locations/{region}"

    print(f"Creating Reasoning Engine using GAPIC client with parent: {parent_path}...")
    operation = gapic_client.create_reasoning_engine(
        parent=parent_path,
        reasoning_engine=gapic_reasoning_engine_config
    )

    print(f"Reasoning Engine creation operation started: {operation.operation.name}")
    print("Waiting for operation to complete...")
    deployed_agent_resource = operation.result()

    print(f"Planner Agent (Reasoning Engine) deployed successfully via GAPIC client: {deployed_agent_resource.name}")
    return deployed_agent_resource
