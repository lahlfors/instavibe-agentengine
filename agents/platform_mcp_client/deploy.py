import os
import uuid
from urllib.parse import urlparse
import cloudpickle
import tarfile
import tempfile
import shutil # For shutil.copy and shutil.copytree

from google.cloud import aiplatform as vertexai
from google.cloud.aiplatform_v1.services import reasoning_engine_service
from google.cloud.aiplatform_v1.types import ReasoningEngine as ReasoningEngineGAPIC
from google.cloud.aiplatform_v1.types import ReasoningEngineSpec
from google.cloud import storage
import google.auth # For google.auth.exceptions

# Import the agent module that contains the `root_agent`
from agents.platform_mcp_client import agent as platform_mcp_client_agent_module

def deploy_platform_mcp_client_main_func(project_id: str, region: str, base_dir: str):
    """Deploys the Platform MCP Client Agent to Vertex AI Reasoning Engines using GAPIC client."""

    display_name = "Platform MCP Client Agent"
    description = "An agent that connects to an MCP Tool Server to provide tools for other agents or clients. It can interact with Instavibe services like creating posts and events."

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

    # The agent to pickle is platform_mcp_client_agent_module.root_agent
    agent_instance_to_pickle = platform_mcp_client_agent_module.root_agent
    if agent_instance_to_pickle is None:
        raise ValueError("Error: The root_agent in platform_mcp_client.agent is None. Ensure it's initialized.")

    pickled_agent_filename = f"platform_mcp_client_agent_pickle_{uuid.uuid4()}.pkl"
    gcs_pickle_path = os.path.join(bucket_prefix, 'reasoning_engine_packages', pickled_agent_filename)
    blob_pickle = bucket.blob(gcs_pickle_path)
    with blob_pickle.open("wb") as f:
        cloudpickle.dump(agent_instance_to_pickle, f)
    pickle_object_gcs_uri = f"gs://{bucket_name}/{gcs_pickle_path}"
    print(f"Uploaded pickled Platform MCP Client agent to {pickle_object_gcs_uri}")

    local_wheel_filename = "a2a_common-0.1.0-py3-none-any.whl"

    agents_content_base_path = base_dir
    # Adjust agents_content_base_path if base_dir is specific
    if os.path.basename(base_dir) == "platform_mcp_client" and os.path.isdir(os.path.join(base_dir, "..", "agents")):
        agents_content_base_path = os.path.abspath(os.path.join(base_dir, ".."))
    elif os.path.basename(base_dir) == "agents" and os.path.isdir(base_dir):
        agents_content_base_path = os.path.abspath(os.path.join(base_dir, ".."))
    elif not os.path.isdir(os.path.join(base_dir, "agents")):
       potential_repo_root = os.path.abspath(os.path.join(base_dir, "..", ".."))
       if os.path.isdir(os.path.join(potential_repo_root, "agents")):
           agents_content_base_path = potential_repo_root

    local_wheel_path = os.path.join(agents_content_base_path, "agents", local_wheel_filename)
    if not os.path.exists(local_wheel_path):
        raise FileNotFoundError(f"Local wheel {local_wheel_path} not found. Base dir: {base_dir}, Derived agents_content_base_path: {agents_content_base_path}")

    actual_platform_mcp_client_src_path = os.path.join(agents_content_base_path, "agents", "platform_mcp_client")
    if not os.path.isdir(actual_platform_mcp_client_src_path):
        raise FileNotFoundError(f"Source directory {actual_platform_mcp_client_src_path} not found.")

    dependency_files_gcs_uri = None
    with tempfile.TemporaryDirectory() as temp_dir_for_tar:
        temp_agents_root_in_tar_dir = os.path.join(temp_dir_for_tar, "agents")
        os.makedirs(temp_agents_root_in_tar_dir, exist_ok=True)

        copied_wheel_path = os.path.join(temp_dir_for_tar, local_wheel_filename)
        shutil.copy(local_wheel_path, copied_wheel_path)
        print(f"Copied wheel to {copied_wheel_path}")

        dest_platform_mcp_client_in_temp_agents = os.path.join(temp_agents_root_in_tar_dir, "platform_mcp_client")
        shutil.copytree(actual_platform_mcp_client_src_path, dest_platform_mcp_client_in_temp_agents, dirs_exist_ok=True)
        print(f"Copied {actual_platform_mcp_client_src_path} to {dest_platform_mcp_client_in_temp_agents}")

        staged_agents_init_py = os.path.join(temp_agents_root_in_tar_dir, "__init__.py")
        source_agents_init_py = os.path.join(agents_content_base_path, "agents", "__init__.py")
        if os.path.exists(source_agents_init_py):
            shutil.copy(source_agents_init_py, staged_agents_init_py)
        elif not os.path.exists(staged_agents_init_py): # Create if not copied and not already exists (e.g. from previous copytree)
            with open(staged_agents_init_py, "w") as f_init:
                f_init.write("# Auto-generated __init__.py for agents package\n")

        tarball_local_filename = f"platform_mcp_client_deps_{uuid.uuid4()}.tar.gz"
        tarball_local_path = os.path.join(tempfile.gettempdir(), tarball_local_filename)

        print(f"Creating tarball {tarball_local_path} containing {local_wheel_filename} (at root) and 'agents/' dir (with 'platform_mcp_client/').")
        with tarfile.open(tarball_local_path, "w:gz") as tar:
            tar.add(copied_wheel_path, arcname=local_wheel_filename)
            tar.add(temp_agents_root_in_tar_dir, arcname="agents")

        gcs_tarball_path = os.path.join(bucket_prefix, 'reasoning_engine_dependencies', tarball_local_filename)
        blob_tarball = bucket.blob(gcs_tarball_path)
        blob_tarball.upload_from_filename(tarball_local_path)
        dependency_files_gcs_uri = f"gs://{bucket_name}/{gcs_tarball_path}"
        print(f"Uploaded dependency tarball to {dependency_files_gcs_uri}")
        os.remove(tarball_local_path)

    original_requirements_file_path = os.path.join(agents_content_base_path, "agents", "platform_mcp_client", "requirements.txt")
    if not os.path.exists(original_requirements_file_path):
         if os.path.basename(base_dir) == "platform_mcp_client" and os.path.exists(os.path.join(base_dir, "requirements.txt")):
             original_requirements_file_path = os.path.join(base_dir, "requirements.txt")
         else:
             alt_req_path = os.path.join(base_dir, "platform_mcp_client", "requirements.txt")
             if os.path.basename(base_dir) == "agents" and os.path.exists(alt_req_path):
                 original_requirements_file_path = alt_req_path
             else:
                 raise FileNotFoundError(f"Original requirements file for platform_mcp_client not found. Checked: {original_requirements_file_path} and fallbacks based on base_dir: {base_dir}")

    print(f"Reading original requirements from: {original_requirements_file_path}")
    with open(original_requirements_file_path, "r") as f:
        original_requirements_lines = f.readlines()

    modified_requirements_lines = []
    found_gcs_package = False
    replaced_local_wheel = False

    for line in original_requirements_lines:
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith('#'):
            modified_requirements_lines.append(line)
            continue
        if "../" + local_wheel_filename in stripped_line or local_wheel_filename in stripped_line :
            if not replaced_local_wheel: # Add only once
                modified_requirements_lines.append(f"{local_wheel_filename}\n")
                print(f"Modified requirements: Replaced '{stripped_line}' with '{local_wheel_filename}'.")
                replaced_local_wheel = True
            else: # If somehow listed multiple times
                print(f"Modified requirements: Removed redundant reference to '{local_wheel_filename}'.")
            continue

        modified_requirements_lines.append(line)
        if "google-cloud-storage" in stripped_line:
            found_gcs_package = True

    if not replaced_local_wheel:
       print(f"Warning: Local wheel reference for '{local_wheel_filename}' not found to replace in {original_requirements_file_path}. Appending filename directly.")
       modified_requirements_lines.append(f"{local_wheel_filename}\n")

    if not found_gcs_package:
        modified_requirements_lines.append("google-cloud-storage\n")
        print("Modified requirements: Added 'google-cloud-storage'.")

    modified_requirements_content = "".join(modified_requirements_lines)
    modified_requirements_content = '\n'.join(filter(None, [l.strip() for l in modified_requirements_content.splitlines()])) + '\n'


    print("---- BEGIN Modified requirements.txt content for Platform MCP Client ----")
    print(modified_requirements_content)
    print("---- END Modified requirements.txt content ----")

    gcs_requirements_filename = f"platform_mcp_client_requirements_modified_{uuid.uuid4()}.txt"
    gcs_requirements_path = os.path.join(bucket_prefix, 'reasoning_engine_packages', gcs_requirements_filename)
    blob_reqs = bucket.blob(gcs_requirements_path)
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

    print(f"Creating Platform MCP Client Reasoning Engine using GAPIC client with parent: {parent_path}...")
    operation = gapic_client.create_reasoning_engine(
        parent=parent_path,
        reasoning_engine=gapic_reasoning_engine_config
    )
    print(f"Reasoning Engine creation operation started: {operation.operation.name}")
    print("Waiting for operation to complete...")
    deployed_agent_resource = operation.result()
    print(f"Platform MCP Client Agent (Reasoning Engine) deployed successfully via GAPIC: {deployed_agent_resource.name}")
    return deployed_agent_resource
