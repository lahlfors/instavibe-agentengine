import logging
import os
import functools
import asyncio
from typing import Any, Callable, Dict, Optional, Generator, AsyncGenerator
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from common.observability import setup_observability

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

class AgentGateway:
    def __init__(self, service_name: str, display_name: str = None, otel_endpoint_override: str = None):
        self.service_name = service_name
        self.display_name = display_name or service_name
        # Setup observability once per gateway initialization
        # Note: setup_observability uses OTEL_SERVICE_NAME env var if set,
        # or defaults based on suffix. We set it here to be explicit.
        os.environ["OTEL_SERVICE_NAME"] = self.service_name
        setup_observability(service_name_suffix=self.service_name, endpoint_override=otel_endpoint_override)

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        input_cost = float(os.getenv("GEMINI_2_0_FLASH_INPUT_COST", "0.10"))
        output_cost = float(os.getenv("GEMINI_2_0_FLASH_OUTPUT_COST", "0.30"))
        return (prompt_tokens * input_cost / 1000000) + (completion_tokens * output_cost / 1000000)

    def execute_sync(self, operation_name: str, func: Callable, *args, **kwargs) -> Any:
        with tracer.start_as_current_span(operation_name) as span:
            try:
                result = func(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                logger.error(f"Error during {operation_name}: {e}", exc_info=True)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def execute_async(self, operation_name: str, func: Callable, *args, **kwargs) -> Any:
        with tracer.start_as_current_span(operation_name) as span:
            try:
                result = await func(*args, **kwargs)
                span.set_status(Status(StatusCode.OK))
                return result
            except Exception as e:
                logger.error(f"Error during {operation_name}: {e}", exc_info=True)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    async def execute_async_generator(self, operation_name: str, func: Callable, *args, **kwargs) -> AsyncGenerator[Any, None]:
        with tracer.start_as_current_span(operation_name) as span:
            try:
                async for item in func(*args, **kwargs):
                    # Policy/Observability: check for usage metadata in item
                    # This logic is specific to the google.adk.events.Event structure or similar
                    if hasattr(item, 'usage_metadata') and item.usage_metadata:
                         prompt_tokens = item.usage_metadata.prompt_token_count
                         completion_tokens = item.usage_metadata.candidates_token_count
                         total_tokens = item.usage_metadata.total_token_count
                         cost = self._calculate_cost(prompt_tokens, completion_tokens)

                         span.set_attribute("gen_ai.usage.prompt_tokens", prompt_tokens)
                         span.set_attribute("gen_ai.usage.completion_tokens", completion_tokens)
                         span.set_attribute("gen_ai.usage.total_tokens", total_tokens)
                         span.set_attribute("gen_ai.usage.cost", cost)

                    # Policy/Observability: check for content to log
                    if hasattr(item, 'is_final_response') and item.is_final_response():
                         if hasattr(item, 'content') and item.content and item.content.parts:
                             final_output = item.content.parts[0].text
                             span.set_attribute("gen_ai.assistant.message", final_output)

                    yield item
                span.set_status(Status(StatusCode.OK))
            except Exception as e:
                logger.error(f"Error during {operation_name}: {e}", exc_info=True)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
