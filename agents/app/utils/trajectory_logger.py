import json
import logging
import os
from google.cloud import storage
from datetime import datetime

def log_trajectory_to_gcs(
    agent_name: str,
    trajectory_data: dict,
    bucket_name: str,
    project_id: str,
):
    """
    Logs agent trajectory data to a file in a GCS bucket.

    Args:
        agent_name: The name of the agent.
        trajectory_data: The trajectory data to log.
        bucket_name: The name of the GCS bucket.
        project_id: The GCP project ID.
    """
    try:
        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)

        # Create a unique filename for each trajectory
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        blob_name = f"trajectories/{agent_name}/{timestamp}.jsonl"
        blob = bucket.blob(blob_name)

        # Convert the dictionary to a JSON string
        json_string = json.dumps(trajectory_data)

        # Upload the data
        blob.upload_from_string(json_string, content_type="application/jsonl")

        logging.info(f"Successfully logged trajectory for agent '{agent_name}' to gs://{bucket_name}/{blob_name}")

    except Exception as e:
        logging.error(f"Failed to log trajectory to GCS for agent '{agent_name}': {e}", exc_info=True)
