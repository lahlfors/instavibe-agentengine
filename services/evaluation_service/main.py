import os
import json
import logging
from flask import Flask, request
from google.cloud import storage
from vertexai.preview.evaluation import EvalTask

app = Flask(__name__)

@app.route("/evaluate", methods=["POST"])
def evaluate():
    """
    Triggers the evaluation pipeline.
    """
    try:
        data = request.get_json()
        if not data:
            return "Invalid request", 400

        bucket_name = data.get("bucket_name")
        project_id = data.get("project_id")
        agent_name = data.get("agent_name")

        if not all([bucket_name, project_id, agent_name]):
            return "Missing required parameters", 400

        storage_client = storage.Client(project=project_id)
        bucket = storage_client.bucket(bucket_name)

        # Load evaluation dataset
        dataset_path = f"agents/{agent_name}/evaluation_dataset.jsonl"
        with open(dataset_path, "r") as f:
            eval_dataset = [json.loads(line) for line in f]

        # Get the latest trajectory
        trajectory_blob_name = f"trajectories/{agent_name}/"
        blobs = list(bucket.list_blobs(prefix=trajectory_blob_name))
        if not blobs:
            return "No trajectories found", 404

        latest_blob = max(blobs, key=lambda b: b.time_created)
        trajectory_data = json.loads(latest_blob.download_as_string())

        # Perform evaluation
        eval_task = EvalTask(
            dataset=eval_dataset,
            metrics=["trajectory_exact_match", "trajectory_in_order_match"],
        )

        result = eval_task.evaluate(
            instance_display_name=f"{agent_name}_evaluation",
            model_inference_output=trajectory_data["trajectory"],
        )

        logging.info(f"Evaluation result: {result}")

        return "Evaluation complete", 200

    except Exception as e:
        logging.error(f"Evaluation failed: {e}", exc_info=True)
        return "Evaluation failed", 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
