# agents/app/utils/communication.py

import aiohttp
import json
import logging
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

# It's better to use Python's logging module than print()
log = logging.getLogger(__name__)

# Get a tracer for this module
tracer = trace.get_tracer(__name__)


def _safe_serialize(data: Any, max_length: int = 4096) -> str:
    """Safely serializes data to a string and truncates it."""
    try:
        s = json.dumps(data, default=str)
        if len(s) > max_length:
            return s[:max_length] + "..."
        return s
    except Exception as e:
        log.warning(f"Failed to serialize data for tracing: {e}")
        return "<serialization error>"


async def call_agent_capability(
    source_agent: str, target_agent: str, capability: str, prompt: Dict[str, Any]
) -> Dict[str, Any]:
    """A wrapper to trace an Agent-to-Agent (A2A) capability call."""
    span_name = f"A2A.{capability}"
    with tracer.start_as_current_span(span_name, kind=trace.SpanKind.CLIENT) as span:
        # --- Use OpenTelemetry Semantic Conventions for RPCs ---
        span.set_attribute("rpc.system", "adk-a2a")
        span.set_attribute("rpc.service", target_agent)
        span.set_attribute("rpc.method", capability)
        span.set_attribute("agent.source", source_agent) # Custom attribute

        # --- Use GenAI conventions for prompts ---
        span.set_attribute("gen_ai.request.prompt", _safe_serialize(prompt))

        try:
            from google.adk import agents # Lazy import inside function

            agent = agents.find(target_agent)
            if not agent:
                raise ValueError(f"Agent '{target_agent}' not found.")

            capability_obj = agent.a2a.get_capability(capability)
            if not capability_obj:
                raise ValueError(
                    f"Capability '{capability}' not on agent '{target_agent}'."
                )

            response = await capability_obj.invoke(prompt)

            span.set_attribute("gen_ai.response.content", _safe_serialize(response))
            span.set_status(Status(StatusCode.OK))
            return response

        except Exception as e:
            if span.is_recording():
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, f"A2A call failed: {e}"))
            raise


async def call_http_endpoint(
    source_agent: str,
    target_service: str,
    http_method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """A wrapper to trace an HTTP call to an external service."""
    method = http_method.upper()
    span_name = f"HTTP {method}"
    with tracer.start_as_current_span(span_name, kind=trace.SpanKind.CLIENT) as span:
        # --- Use OpenTelemetry Semantic Conventions for HTTP ---
        span.set_attribute("http.request.method", method)
        span.set_attribute("url.full", url)
        span.set_attribute("agent.source", source_agent) # Custom attribute
        span.set_attribute("agent.target", target_service) # Custom attribute

        if json_payload:
            span.set_attribute("http.request.body", _safe_serialize(json_payload))

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=method, url=url, headers=headers, json=json_payload
                ) as response:
                    status_code = response.status
                    span.set_attribute("http.response.status_code", status_code)

                    # Check for HTTP error codes and set span status accordingly
                    if status_code >= 400:
                        span.set_status(Status(StatusCode.ERROR, f"HTTP Error: {status_code}"))

                    response_data = await response.json()
                    span.set_attribute("http.response.body", _safe_serialize(response_data))

                    # You might still want to raise an exception for error codes
                    response.raise_for_status()

                    return response_data

        except aiohttp.ClientError as e:
            if span.is_recording():
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, f"HTTP call failed: {e}"))
            raise
