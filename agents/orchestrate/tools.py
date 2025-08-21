from vertexai.preview.generative_models import MemoryBankServiceClient
from google.cloud.aiplatform_v1beta1.types import memory_bank as memory_bank_types
import os

def create_memory(client: MemoryBankServiceClient):
    def create_memory_tool(user_id: str, content: str, metadata: dict):
        """Creates a new memory in the Memory Bank."""
        if not client:
            return None

        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION")

        parent = client.common_location_path(project_id, location)
        memory = memory_bank_types.Memory(
            user_id=user_id,
            content=content,
            metadata=metadata,
        )
        request = memory_bank_types.CreateMemoryRequest(
            parent=parent,
            memory=memory,
        )
        try:
            response = client.create_memory(request=request)
            return response
        except Exception as e:
            print(f"Error creating memory: {e}")
            return None
    return create_memory_tool

def search_memories(client: MemoryBankServiceClient):
    def search_memories_tool(user_id: str, query: str, top_k: int = 5):
        """Searches for memories in the Memory Bank."""
        if not client:
            return None

        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION")

        parent = client.common_location_path(project_id, location)
        request = memory_bank_types.SearchMemoriesRequest(
            parent=parent,
            user_id=user_id,
            query=query,
            top_k=top_k,
        )
        try:
            response = client.search_memories(request=request)
            return response
        except Exception as e:
            print(f"Error searching memories: {e}")
            return None
    return search_memories_tool
