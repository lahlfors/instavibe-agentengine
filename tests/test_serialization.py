import cloudpickle
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import vertexai

# Set dummy environment variables to allow modules to import
os.environ["COMMON_GOOGLE_CLOUD_PROJECT"] = "test-project"
os.environ["COMMON_GOOGLE_CLOUD_LOCATION"] = "us-central1"
os.environ["COMMON_VERTEX_STAGING_BUCKET"] = "test-bucket"
os.environ["COMMON_SPANNER_INSTANCE_ID"] = "test-instance"
os.environ["COMMON_SPANNER_DATABASE_ID"] = "test-database"

# Initialize Vertex AI
vertexai.init(project="test-project", location="us-central1")

from agents.planner.deploy import deploy_planner_main_func

try:
    print("Attempting to get the local agent object for serialization test...")
    local_agent = deploy_planner_main_func(
        project_id="test-project",
        region="us-central1",
        base_dir=".",
        dry_run=True
    )

    print("Successfully got the agent object. Now testing serialization...")
    pickled_agent = cloudpickle.dumps(local_agent)
    print("Successfully pickled the agent.")

except Exception as e:
    print(f"Serialization test failed: {e}", file=sys.stderr)
    import traceback
    traceback.print_exc()
