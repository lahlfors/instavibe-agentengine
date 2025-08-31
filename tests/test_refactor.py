import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import site

print(f"\n--- DEBUG: Test Execution Environment ---")
print(f"Python Executable: {sys.executable}")
print(f"VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV')}")
print(f"sys.path:")
for p in sys.path:
    print(f" - {p}")
print(f"Site Packages: {site.getsitepackages()}")
print("--- END DEBUG ---\n")
import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import os
import logging
os.environ["COMMON_SPANNER_INSTANCE_ID"] = "test-instance"
os.environ["COMMON_SPANNER_DATABASE_ID"] = "test-database"
os.environ["COMMON_GOOGLE_CLOUD_PROJECT"] = "test-project"

# Patch the spanner client at the source, before it's imported by app.py
# This prevents the client from trying to authenticate when the module is loaded.
patcher = patch('google.cloud.spanner.Client', autospec=True)
patcher_ts = patch('google.cloud.spanner.COMMIT_TIMESTAMP', 'COMMIT_TIMESTAMP')

from unittest.mock import MagicMock

# Start the patches
mock_spanner_client = patcher.start()
mock_spanner_ts = patcher_ts.start()

# Make sure to stop the patcher after tests are done
import atexit
atexit.register(patcher.stop)
atexit.register(patcher_ts.stop)

# Must be imported before the modules that use them for patching to work
from flask import Flask, jsonify
import instavibe.app as instavibe_app
from tools.instavibe import mcp_server as instavibe_tool_client
from agents.social import instavibe as social_instavibe_data

# --- 1. Tests for instavibe/app.py (Flask App API Endpoints) ---
@pytest.fixture
def app():
    """Create and configure a new app instance for each test."""
    # The main app object is created at the module level in instavibe.app
    # We can just use it directly
    app = instavibe_app.app
    app.config.update({
        "TESTING": True,
    })
    yield app

@pytest.fixture
def client(app):
    """A test client for the app."""
    return app.test_client()

@patch('instavibe.app.get_person_by_name_db')
def test_get_person_id_by_name_api(mock_get_person_by_name_db, client):
    """Test the /api/person/by_name/<name> endpoint."""
    # Test case 1: Person found
    mock_get_person_by_name_db.return_value = "person-123"
    response = client.get('/api/person/by_name/Alice')
    assert response.status_code == 200
    assert response.json == {"person_id": "person-123"}


    # Test case 2: Person not found
    mock_get_person_by_name_db.return_value = None
    response = client.get('/api/person/by_name/Unknown')
    assert response.status_code == 404
    assert 'error' in response.json
@patch('instavibe.app.get_person_db')
@patch('instavibe.app.get_person_attended_events_db')
def test_get_person_attended_events_api(mock_get_events_db, mock_get_person_db, client):
    """Test the /api/person/<id>/attended_events endpoint."""
    mock_get_person_db.return_value = {"person_id": "person-123", "name": "Alice"} # Simulate person exists
    mock_get_events_db.return_value = [{"event_id": "event-1", "name": "Test Event"}]
    response = client.get('/api/person/person-123/attended_events')
    assert response.status_code == 200
    assert response.json == [{"event_id": "event-1", "name": "Test Event"}]
    mock_get_events_db.assert_called_with("person-123")

@patch('instavibe.app.get_person_db')
@patch('instavibe.app.get_posts_by_person_db')
def test_get_person_posts_api(mock_get_posts_db, mock_get_person_db, client):
    """Test the /api/person/<id>/posts endpoint."""
    mock_get_person_db.return_value = {"person_id": "person-123", "name": "Alice"}
    mock_get_posts_db.return_value = [{"post_id": "post-1", "text": "Hello"}]
    response = client.get('/api/person/person-123/posts')
    assert response.status_code == 200
    assert response.json == [{"post_id": "post-1", "text": "Hello"}]
    mock_get_posts_db.assert_called_with("person-123")

@patch('instavibe.app.get_person_db')
@patch('instavibe.app.get_friends_db')
def test_get_person_friends_api(mock_get_friends_db, mock_get_person_db, client):
    """Test the /api/person/<id>/friends endpoint."""
    mock_get_person_db.return_value = {"person_id": "person-123", "name": "Alice"}
    mock_get_friends_db.return_value = [{"person_id": "person-456", "name": "Bob"}]
    response = client.get('/api/person/person-123/friends')
    assert response.status_code == 200
    assert response.json == [{"person_id": "person-456", "name": "Bob"}]
    mock_get_friends_db.assert_called_with("person-123")

# --- 2. Tests for tools/instavibe/instavibe.py (API Client) ---
@pytest.mark.asyncio
@patch('tools.instavibe.mcp_server.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_id_by_name(mock_call_http):
    """Test the API client function for getting person ID by name."""
    mock_call_http.return_value = {"person_id": "person-123"}
    tool_result = await instavibe_tool_client.get_person_id_by_name.run({"name": "Alice"})
    person_id = tool_result.content[0].text
    assert person_id == "person-123"
    mock_call_http.assert_awaited_with(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=f"{instavibe_tool_client.BASE_URL}/api/person/by_name/Alice",
        headers={},
        json={}
    )

@pytest.mark.asyncio
@patch('tools.instavibe.mcp_server.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_attended_events(mock_call_http):
    """Test the API client function for getting attended events."""
    tool_result = await instavibe_tool_client.get_person_attended_events.run({"person_id": "person-123"})
    assert tool_result.content[0].text is not None
    mock_call_http.assert_awaited_with(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=f"{instavibe_tool_client.BASE_URL}/api/person/person-123/attended_events",
        headers={},
        json={}
    )

@pytest.mark.asyncio
@patch('tools.instavibe.mcp_server.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_posts(mock_call_http):
    """Test the API client function for getting person posts."""
    tool_result = await instavibe_tool_client.get_person_posts.run({"person_id": "person-123"})
    assert tool_result.content[0].text is not None
    mock_call_http.assert_awaited_with(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=f"{instavibe_tool_client.BASE_URL}/api/person/person-123/posts",
        headers={},
        json={}
    )

@pytest.mark.asyncio
@patch('tools.instavibe.mcp_server.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_friends(mock_call_http):
    """Test the API client function for getting person friends."""
    tool_result = await instavibe_tool_client.get_person_friends.run({"person_id": "person-123"})
    assert tool_result.content[0].text is not None
    mock_call_http.assert_awaited_with(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=f"{instavibe_tool_client.BASE_URL}/api/person/person-123/friends",
        headers={},
        json={}
    )

# --- 3. Tests for agents/social/instavibe.py (Refactored Data Access Layer) ---
@pytest.mark.asyncio
@patch('agents.social.instavibe.instavibe_client', new_callable=MagicMock)
async def test_social_get_person_id_by_name(mock_client):
    """Test the refactored social agent data access function."""
    mock_client.get_person_id_by_name = AsyncMock(return_value="person-123")
    result = await social_instavibe_data.get_person_id_by_name("Alice")
    mock_client.get_person_id_by_name.assert_awaited_with(name="Alice")
    assert result == "person-123"

@pytest.mark.asyncio
@patch('agents.social.instavibe.instavibe_client', new_callable=MagicMock)
async def test_social_get_attended_events(mock_client):
    """Test the refactored social agent data access function."""
    mock_client.get_person_attended_events = AsyncMock(return_value=[])
    await social_instavibe_data.get_person_attended_events("person-123")
    mock_client.get_person_attended_events.assert_awaited_with(person_id="person-123")

@pytest.mark.asyncio
@patch('agents.social.instavibe.instavibe_client', new_callable=MagicMock)
async def test_social_get_posts(mock_client):
    """Test the refactored social agent data access function."""
    mock_client.get_person_posts = AsyncMock(return_value=[])
    await social_instavibe_data.get_person_posts("person-123")
    mock_client.get_person_posts.assert_awaited_with(person_id="person-123")

@pytest.mark.asyncio
@patch('agents.social.instavibe.instavibe_client', new_callable=MagicMock)
async def test_social_get_friends(mock_client):
    """Test the refactored social agent data access function."""
    mock_client.get_person_friends = AsyncMock(return_value=[])
    await social_instavibe_data.get_person_friends("person-123")
    mock_client.get_person_friends.assert_awaited_with(person_id="person-123")

# --- 4. Tests for common/observability.py ---
from common.observability import setup_observability
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource

@patch('common.observability.google.auth.default', return_value=(("creds", "project-id")))
@patch('common.observability.trace.get_tracer_provider')
@patch('common.observability.BatchSpanProcessor')
@patch('common.observability.ConsoleSpanExporter')
@patch('common.observability.OTLPMetricExporter')
@patch('common.observability.PeriodicExportingMetricReader')
@patch('common.observability.MeterProvider')
@patch('common.observability.propagate.set_global_textmap')
@patch('common.observability.google.cloud.logging.Client')
@patch('common.observability.VertexAIInstrumentor')
@patch('common.observability.RequestsInstrumentor')
@patch('common.observability.GrpcInstrumentorClient')
@patch('common.observability.AioHttpClientInstrumentor')
@patch('common.observability.AuthMetadataPlugin')
@patch('common.observability.grpc.ssl_channel_credentials')
@patch('common.observability.grpc.composite_channel_credentials')
def test_setup_observability_with_existing_provider(
    mock_composite_channel_credentials,
    mock_ssl_channel_credentials,
    mock_auth_metadata_plugin,
    mock_aiohttp_instrumentor,
    mock_grpc_client_instrumentor,
    mock_requests_instrumentor,
    mock_vertexai_instrumentor,
    mock_logging_client,
    mock_set_global_textmap,
    mock_meter_provider,
    mock_periodic_exporting_metric_reader,
    mock_otlp_metric_exporter,
    mock_console_exporter,
    mock_batch_span_processor,
    mock_get_tracer_provider,
    mock_google_auth,
):
    """Test setup_observability when a TracerProvider already exists."""
    # Arrange
    mock_provider = MagicMock(spec=TracerProvider)
    mock_provider.resource = Resource.create({"existing.attr": "value"})
    mock_provider._span_processors = []
    mock_get_tracer_provider.return_value = mock_provider
    os.environ["SERVICE_NAME"] = "test_service"

    # Act
    setup_observability()

    # Assert
    mock_google_auth.assert_called_once()
    mock_get_tracer_provider.assert_called() # Called to get the provider

    # Resource merging check
    assert "service.name" in mock_provider._resource.attributes
    assert mock_provider._resource.attributes["service.name"] == "test_service"
    assert "existing.attr" in mock_provider._resource.attributes

    # Console exporter check (idempotency)
    mock_provider.add_span_processor.assert_called_once()
    mock_console_exporter.assert_called_once()
    mock_batch_span_processor.assert_called_once_with(mock_console_exporter.return_value)

    # Metrics check
    mock_otlp_metric_exporter.assert_called_once()
    mock_periodic_exporting_metric_reader.assert_called_once()
    mock_meter_provider.assert_called_once()

    # Instrumentors check
    mock_vertexai_instrumentor.return_value.instrument.assert_called_once()
    mock_requests_instrumentor.return_value.instrument.assert_called_once()
    mock_grpc_client_instrumentor.return_value.instrument.assert_called_once()
    mock_aiohttp_instrumentor.return_value.instrument.assert_called_once()
