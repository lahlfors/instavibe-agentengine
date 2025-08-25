import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import os
os.environ["COMMON_SPANNER_INSTANCE_ID"] = "test-instance"
os.environ["COMMON_SPANNER_DATABASE_ID"] = "test-database"
os.environ["COMMON_GOOGLE_CLOUD_PROJECT"] = "test-project"


# Patch the spanner client at the source, before it's imported by app.py
# This prevents the client from trying to authenticate when the module is loaded.
patcher = patch('google.cloud.spanner.Client', autospec=True)
patcher_ts = patch('google.cloud.spanner.COMMIT_TIMESTAMP', 'COMMIT_TIMESTAMP')
patcher_logging = patch('google.cloud.logging.Client', autospec=True)

from unittest.mock import MagicMock
# Start the patches
mock_spanner_client = patcher.start()
mock_spanner_ts = patcher_ts.start()
mock_logging_client = patcher_logging.start()
mock_logging_client.return_value._handlers = MagicMock()
mock_logging_client.return_value._handlers.add = MagicMock()
mock_logging_client.return_value.project = "test-project"


# Make sure to stop the patcher after tests are done
import atexit
atexit.register(patcher.stop)
atexit.register(patcher_ts.stop)
atexit.register(patcher_logging.stop)


# Must be imported before the modules that use them for patching to work
from flask import Flask, jsonify
import instavibe.app as instavibe_app
from tools.instavibe import instavibe as instavibe_tool_client
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
@patch('tools.instavibe.instavibe.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_id_by_name(mock_call_http):
    """Test the API client function for getting person ID by name."""
    mock_call_http.return_value = {"person_id": "person-123"}
    person_id = await instavibe_tool_client.get_person_id_by_name("Alice")
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
@patch('tools.instavibe.instavibe.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_attended_events(mock_call_http):
    """Test the API client function for getting attended events."""
    await instavibe_tool_client.get_person_attended_events("person-123")
    mock_call_http.assert_awaited_with(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=f"{instavibe_tool_client.BASE_URL}/api/person/person-123/attended_events",
        headers={},
        json={}
    )

@pytest.mark.asyncio
@patch('tools.instavibe.instavibe.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_posts(mock_call_http):
    """Test the API client function for getting person posts."""
    await instavibe_tool_client.get_person_posts("person-123")
    mock_call_http.assert_awaited_with(
        source_agent="instavibe_tool",
        target_service="instavibe_app",
        http_method="GET",
        url=f"{instavibe_tool_client.BASE_URL}/api/person/person-123/posts",
        headers={},
        json={}
    )

@pytest.mark.asyncio
@patch('tools.instavibe.instavibe.call_http_endpoint', new_callable=AsyncMock)
async def test_client_get_person_friends(mock_call_http):
    """Test the API client function for getting person friends."""
    await instavibe_tool_client.get_person_friends("person-123")
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

import os
@patch('google.cloud.logging_v2.handlers._monitored_resources.add_resource_labels', return_value={})
@patch('common.observability.Traceloop')
def test_setup_observability(mock_traceloop, mock_add_resource_labels):
    """Test that setup_observability calls Traceloop.init and a tracer can be acquired."""
    with patch.dict(os.environ, {}, clear=True):
        setup_observability("test-service")
        mock_traceloop.init.assert_called_with()
        assert os.environ["TRACELOOP_SERVICE_NAME"] == "test-service"

        # Verify that a tracer can be acquired
        tracer = trace.get_tracer("my.tracer")
        assert tracer is not None
        assert isinstance(tracer, trace.Tracer)
