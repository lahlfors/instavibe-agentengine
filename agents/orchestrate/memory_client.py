import os
from google.cloud.aiplatform_v1beta1 import MemoryBankServiceClient

def get_memory_bank_client():
    """Initializes and returns a MemoryBankServiceClient."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION")

    if not project_id or not location:
        print("Skipping Memory Bank client initialization due to missing GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_LOCATION.")
        return None

    try:
        client = MemoryBankServiceClient(
            client_options={"api_endpoint": f"{location}-aiplatform.googleapis.com"}
        )
        print("Memory Bank client initialized successfully.")
        return client
    except Exception as e:
        print(f"An unexpected error occurred during Memory Bank initialization: {e}")
        return None
