# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.sdk.resources import Resource

def get_tracer(service_name: str):
    """
    Initializes and returns an OpenTelemetry tracer.
    """
    project_id = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")
    if not project_id:
        print("COMMON_GOOGLE_CLOUD_PROJECT environment variable not set. Tracing will be disabled.")
        return None

    resource = Resource(attributes={
        "service.name": service_name,
    })
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(CloudTraceSpanExporter(project_id=project_id))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
