# agents/orchestrate/intention_classifier.py
"""Helper module that isolates intent classification logic for the orchestrator.

The original implementation lived inside ``OrchestrateServiceAgent.classify_intent``.
By extracting it we achieve a single‑responsibility component that can be unit‑tested
independently and reused by other parts of the system.
"""

from __future__ import annotations

import logging
from typing import Any

from google.genai.types import GenerationConfig
from google.generativeai import GenerativeModel

# Import the UserIntent enum defined in ``agents.orchestrate.agent``
# Using a relative import to avoid circular dependencies at runtime.
from enum import Enum

class UserIntent(str, Enum):
    PLAN = "PLAN"
    SOCIAL = "SOCIAL"
    PLATFORM = "PLATFORM"
    UNKNOWN = "UNKNOWN"

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Encapsulates the LLM prompt used to map a user request to a ``UserIntent``.

    Parameters
    ----------
    model_client: GenerativeModel
        An instantiated ``GenerativeModel`` (e.g. Gemini‑2.5‑flash) that the
        orchestrator already creates in its ``__post_init__``.  The classifier
        re‑uses this client so that model configuration (temperature, etc.) stays
        consistent across the codebase.
    """

    def __init__(self, model_client: Any):
        self._model_client = model_client
        if not self._model_client:
            logger.warning("IntentClassifier initialized without a model client.")

    async def classify(self, user_input: str) -> UserIntent:
        """Classify ``user_input`` into one of the ``UserIntent`` categories.

        The method mirrors the original prompt used in ``OrchestrateServiceAgent``
        but is isolated for easier testing and potential future enhancements
        (e.g., adding few‑shot examples or a different model).
        """
        # --- Deterministic Overrides for Known Templates ---
        # This avoids LLM latency/error for standard client requests
        stripped_input = user_input.strip().upper()
        
        # Check for substring to be robust against headers/newlines
        if "CREATE EVENT PLAN" in stripped_input:
            logger.info("IntentClassifier: Fast-path matched 'CREATE EVENT PLAN' -> PLAN")
            return UserIntent.PLAN
            
        logger.info("IntentClassifier: No fast-path match, delegating to LLM...")
        
        prompt = f"""
        Classify the following user request into exactly one category:
        1. PLAN: Requests to plan an event, night out, party, itinerary, or suggestions for activities.
        2. SOCIAL: Requests to check social media, friends' posts, or what friends are doing.
        3. PLATFORM: Requests to post to the platform, create events, invite friends, or share plans.
        
        User Request: "{user_input}"
        
        Output ONLY the category name (PLAN, SOCIAL, or PLATFORM). If it doesn't fit, output UNKNOWN.
        """
        try:
            generation_config = GenerationConfig(
                response_mime_type="text/plain",
                temperature=0.0,  # deterministic output
            )
            response = await self._model_client.generate_content_async(
                prompt, generation_config=generation_config
            )
            text = response.text.strip().upper()
            if "PLAN" in text:
                return UserIntent.PLAN
            if "SOCIAL" in text:
                return UserIntent.SOCIAL
            if "PLATFORM" in text:
                return UserIntent.PLATFORM
            return UserIntent.UNKNOWN
        except Exception as e:
            logger.error(f"Error classifying intent: {e}")
            return UserIntent.UNKNOWN
