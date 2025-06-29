import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import Flask, render_template, abort, flash, request, jsonify
from google.cloud import spanner
from google.cloud.spanner_v1 import param_types
from google.api_core import exceptions
import humanize 
import uuid
import traceback
from dateutil import parser
from ally_routes import ally_bp
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
# BatchSpanProcessor removed - relying on Agent Engine for trace export
from opentelemetry.sdk.resources import Resource, SERVICE_NAME as OTEL_SERVICE_NAME_KEY
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
# Imports reverted to use agents.app.utils structure,
# as 'agents' directory is now copied directly into the image.
from agents.app.utils.logging_setup import setup_google_cloud_logging
# CloudTraceLoggingSpanExporter REMOVED - Rely on Agent Engine auto-export
# CloudTraceExporter (OTLP) REMOVED - Rely on Agent Engine auto-export

from opentelemetry import propagators
# GcpCloudTraceFormatPropagator REMOVED - Deprecated
from opentelemetry.propagators.composite import CompositePropagator # Kept for structure if other standard propagators are added
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Load environment variables from root .env file first.
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# Define service name for observability
SERVICE_NAME = "instavibe-app"
LOG_LEVEL = logging.INFO # Or logging.DEBUG, or from env var

# 0. Configure Global Propagator
# Rely on W3C TraceContextTextMapPropagator. Agent Engine handles GCP context.
propagators.set_global_textmap_propagator(
    TraceContextTextMapPropagator()
)
# If needing multiple standard propagators (e.g., baggage):
# propagators.set_global_textmap_propagator(
# CompositePropagator([
# TraceContextTextMapPropagator(),
# # BaggagePropagator(),
# ])
# )

# 1. Initialize OpenTelemetry TracerProvider
# Exporter and processor are removed; relying on Vertex AI Agent Engine's auto-export.
resource = Resource(attributes={
    OTEL_SERVICE_NAME_KEY: SERVICE_NAME
})
provider = TracerProvider(resource=resource)
# BatchSpanProcessor and its addition to the provider are REMOVED.
# The Vertex AI Agent Engine's environment is expected to handle trace export
# when a TracerProvider is initialized and set.
trace.set_tracer_provider(provider)

# 2. Instrument logging for OpenTelemetry
LoggingInstrumentor().instrument(set_logging_format=True)

# 3. Setup Google Cloud logging for the application
# This will configure the root logger. Flask's app.logger will inherit this.
setup_google_cloud_logging(log_level=LOG_LEVEL, service_name=SERVICE_NAME)

# Get a logger for this module AFTER global logging setup
logger = logging.getLogger(__name__)
logger.info(f"'{SERVICE_NAME}' base logging and OTel provider initialized.")

app = Flask(__name__)

# 4. Instrument Flask app with OpenTelemetry
# This should be done after TracerProvider setup and Flask app instantiation.
FlaskInstrumentor().instrument_app(app)
logger.info("Flask app instrumented with OpenTelemetry.")

logger.info("Environment variables (re-confirming) loaded for Instavibe app.") # .env already loaded

app.secret_key = os.environ.get("INSTAVIBE_FLASK_SECRET_KEY", "a_default_secret_key_for_dev")
app.register_blueprint(ally_bp)
logger.info("Flask app basic setup complete and Ally blueprint registered.")

# --- Spanner Configuration ---
INSTANCE_ID = os.environ.get("COMMON_SPANNER_INSTANCE_ID")
if not INSTANCE_ID:
    raise ValueError("CRITICAL: COMMON_SPANNER_INSTANCE_ID environment variable not set. Application cannot start.")
DATABASE_ID = os.environ.get("COMMON_SPANNER_DATABASE_ID")
if not DATABASE_ID:
    raise ValueError("CRITICAL: COMMON_SPANNER_DATABASE_ID environment variable not set. Application cannot start.")
PROJECT_ID = os.environ.get("COMMON_GOOGLE_CLOUD_PROJECT")
APP_HOST = os.environ.get("INSTAVIBE_APP_HOST", "0.0.0.0")

# For Cloud Run, PORT is provided by the environment. Use it if available.
# INSTAVIBE_APP_PORT can be a fallback for local dev or other environments.
APP_PORT = os.environ.get("PORT") # Cloud Run's standard PORT variable
if APP_PORT is None:
    APP_PORT = os.environ.get("INSTAVIBE_APP_PORT", "8080") # Fallback to INSTAVIBE_APP_PORT, then 8080
GOOGLE_MAPS_API_KEY = os.environ.get("INSTAVIBE_GOOGLE_MAPS_API_KEY")
GOOGLE_MAPS_MAP_ID = os.environ.get('INSTAVIBE_GOOGLE_MAPS_MAP_ID') # Corrected variable name GOOGLE_MAPS_MAP_KEY to GOOGLE_MAPS_MAP_ID

if not GOOGLE_MAPS_API_KEY:
    logger.info("The INSTAVIBE_GOOGLE_MAPS_API_KEY environment variable is not set. Mapping features relying on this key may be limited or non-functional.")

if not GOOGLE_MAPS_MAP_ID:
    logger.info("The INSTAVIBE_GOOGLE_MAPS_MAP_ID environment variable is not set. Specific map styling or features may not be applied.")

if not PROJECT_ID:
    # This check is critical for Spanner client initialization.
    logger.critical("CRITICAL: COMMON_GOOGLE_CLOUD_PROJECT environment variable not set. Application cannot start.")
    raise ValueError("CRITICAL: COMMON_GOOGLE_CLOUD_PROJECT environment variable not set. Application cannot start.")

# --- Spanner Client Initialization ---
# PROJECT_ID is now sourced from COMMON_GOOGLE_CLOUD_PROJECT, critical check above handles it.

db = None
try:
    logger.info(f"Attempting to initialize Spanner client with Project ID: {PROJECT_ID}")
    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID) # Ensure INSTANCE_ID is defined
    database = instance.database(DATABASE_ID)       # Ensure DATABASE_ID is defined
    logger.info(f"Attempting to connect to Spanner: {instance.name}/databases/{database.name}")

    if not instance.exists():
        logger.critical(f"CRITICAL Error: Spanner instance '{INSTANCE_ID}' does not exist in project '{PROJECT_ID}'.")
        raise RuntimeError(f"Spanner instance '{INSTANCE_ID}' not found in project '{PROJECT_ID}'. Application cannot start.")

    if not database.exists():
        logger.critical(f"CRITICAL Error: Database '{DATABASE_ID}' does not exist in instance '{INSTANCE_ID}'.")
        # Optionally, you could mention creating the database here if that's part of your SOPs
        raise RuntimeError(f"Spanner database '{DATABASE_ID}' not found in instance '{INSTANCE_ID}'. Application cannot start.")
    else:
        logger.info("Spanner Database connection check successful (database exists).")
        db = database

except exceptions.NotFound as e: # Catch specific Spanner NotFound
    logger.critical(f"CRITICAL Spanner Error (NotFound): {e}. This usually means instance or database details are incorrect or they don't exist.", exc_info=True)
    raise RuntimeError(f"Spanner resource not found: {e}. Application cannot start.") from e
except exceptions.GoogleAPICallError as e: # Catch broader API call errors
    logger.critical(f"CRITICAL Spanner API Call Error: {e}. This could be permissions, network, or configuration issues.", exc_info=True)
    raise RuntimeError(f"Spanner API call failed: {e}. Application cannot start.") from e
except Exception as e: # Catch any other unexpected errors during initialization
    logger.critical(f"CRITICAL Unexpected error during Spanner initialization: {e}", exc_info=True)
    # traceback.print_exc() # Already covered by exc_info=True in logger
    raise RuntimeError(f"Unexpected error during Spanner initialization: {e}. Application cannot start.") from e

# Final check after try-except block
if db is None:
    logger.critical("CRITICAL: Spanner database object 'db' is None after initialization attempts. This should not happen if exceptions are raised correctly.")
    raise RuntimeError("Spanner database connection could not be established. 'db' is None. Application cannot start.")

def run_query(sql, params=None, param_types=None, expected_fields=None): # Add expected_fields
    """
    Executes a SQL query against the Spanner database.

    Args:
        sql (str): The SQL query string.
        params (dict, optional): Dictionary of query parameters. Defaults to None.
        param_types (dict, optional): Dictionary mapping parameter names to their
                                      Spanner types (e.g., spanner.param_types.STRING).
                                      Defaults to None.
        expected_fields (list[str], optional): A list of strings representing the
                                                expected column names in the order
                                                they appear in the SELECT statement.
                                                Required if results.fields fails.
    """
    if not db:
        logger.error("Error: Database connection is not available for run_query.")
        raise ConnectionError("Spanner database connection not initialized.")

    results_list = []
    logger.debug(f"Executing SQL query: {sql[:500]}{'...' if len(sql) > 500 else ''}") # Log snippet of SQL
    if params:
        logger.debug(f"With parameters: {params}")

    try:
        with db.snapshot() as snapshot:
            results = snapshot.execute_sql(
                sql,
                params=params,
                param_types=param_types
            )

            field_names = expected_fields
            if not field_names:
                 logger.warning("expected_fields not provided to run_query. Attempting dynamic field name lookup from results.fields.")
                 try:
                     field_names = [field.name for field in results.fields]
                 except AttributeError as e_fields:
                     logger.error(f"Error accessing results.fields: {e_fields}. Cannot process results without field names.", exc_info=True)
                     raise ValueError("Could not determine field names for query results.") from e_fields

            logger.debug(f"Using field names for query results: {field_names}")

            for i, row in enumerate(results):
                if len(field_names) != len(row):
                     logger.warning(
                         f"Row {i}: Mismatch between number of field names ({len(field_names)}) and row values ({len(row)}). "
                         f"Fields: {field_names}, Row: {row}. Skipping this row."
                     )
                     continue
                results_list.append(dict(zip(field_names, row)))

            logger.info(f"Query successful, fetched {len(results_list)} rows for SQL: {sql[:80]}{'...' if len(sql) > 80 else ''}")

    except (exceptions.NotFound, exceptions.PermissionDenied, exceptions.InvalidArgument) as spanner_err:
        logger.error(f"Spanner Error ({type(spanner_err).__name__}) executing query: {sql[:80]}... Error: {spanner_err}", exc_info=True)
        flash(f"Database error: {spanner_err}", "danger") # Keep flash for user feedback
        return [] # Return empty list on error to maintain function signature for UI
    except ValueError as e_val: # Catch the ValueError we might raise above
         logger.error(f"Query Processing Error: {e_val}", exc_info=True)
         flash("Internal error processing query results.", "danger")
         return []
    except Exception as e_unexpected:
        logger.error(f"An unexpected error occurred during query execution or processing: {e_unexpected}", exc_info=True)
        # traceback.print_exc() # Covered by exc_info=True
        flash(f"An unexpected server error occurred while fetching data.", "danger")
        raise e_unexpected # Re-raise for server to handle, or return [] if UI should degrade gracefully

    return results_list

# --- HOW TO CALL IT ---

def get_all_posts_with_author_db():
    """Fetch all posts and join with author information from Spanner."""
    sql = """
        SELECT
            p.post_id, p.author_id, p.text, p.sentiment, p.post_timestamp,
            author.name as author_name
        FROM Post AS p
        JOIN Person AS author ON p.author_id = author.person_id
        ORDER BY p.post_timestamp DESC
    """
    # Define the fields exactly as they appear in the SELECT statement
    fields = ["post_id", "author_id", "text", "sentiment", "post_timestamp", "author_name"]
    return run_query(sql, expected_fields=fields) # Pass the list here

def get_person_db(person_id):
    """Fetch a single person's details from Spanner."""
    sql = """
        SELECT person_id, name, age
        FROM Person
        WHERE person_id = @person_id
    """
    params = {"person_id": person_id}
    param_types_map = {"person_id": param_types.STRING} # Renamed variable
    fields = ["person_id", "name", "age"]
    results = run_query(sql, params=params, param_types=param_types_map, expected_fields=fields)
    return results[0] if results else None

def get_posts_by_person_db(person_id):
    """Fetch posts written by a specific person from Spanner."""
    sql = """
        SELECT
            p.post_id, p.author_id, p.text, p.sentiment, p.post_timestamp,
            author.name as author_name
        FROM Post AS p
        JOIN Person AS author ON p.author_id = author.person_id
        WHERE p.author_id = @person_id
        ORDER BY p.post_timestamp DESC
    """
    params = {"person_id": person_id}
    param_types_map = {"person_id": param_types.STRING}
    fields = ["post_id", "author_id", "text", "sentiment", "post_timestamp", "author_name"]
    return run_query(sql, params=params, param_types=param_types_map, expected_fields=fields)

def get_friends_db(person_id):
    """Fetch friends of a specific person from Spanner."""
    sql = """
        SELECT DISTINCT
            friend.person_id, friend.name
        FROM Friendship AS f
        JOIN Person AS friend ON
            (f.person_id_a = @person_id AND f.person_id_b = friend.person_id) OR
            (f.person_id_b = @person_id AND f.person_id_a = friend.person_id)
        WHERE f.person_id_a = @person_id OR f.person_id_b = @person_id
        ORDER BY friend.name
    """
    params = {"person_id": person_id}
    param_types_map = {"person_id": param_types.STRING}
    fields = ["person_id", "name"]
    return run_query(sql, params=params, param_types=param_types_map, expected_fields=fields)


def get_all_events_with_attendees_db():
    """Fetch all events and their attendees from Spanner."""
    # Get all events first
    event_sql = """
        SELECT event_id, name, event_date
        FROM Event
        ORDER BY event_date DESC
        LIMIT 50
    """
    event_fields = ["event_id", "name", "event_date"]
    events = run_query(event_sql, expected_fields=event_fields)
    if not events:
        return []

    events_with_attendees = {event['event_id']: {'details': event, 'attendees': []} for event in events}
    event_ids = list(events_with_attendees.keys())

    # Fetch attendees
    attendee_sql = """
        SELECT
            a.event_id,
            p.person_id, p.name
        FROM Attendance AS a
        JOIN Person AS p ON a.person_id = p.person_id
        WHERE a.event_id IN UNNEST(@event_ids)
        ORDER BY a.event_id, p.name
    """
    params = {"event_ids": event_ids}
    param_types_map = {"event_ids": param_types.Array(param_types.STRING)}
    attendee_fields = ["event_id", "person_id", "name"]
    all_attendees = run_query(attendee_sql, params=params, param_types=param_types_map, expected_fields=attendee_fields)

    for attendee in all_attendees:
        event_id = attendee['event_id']
        if event_id in events_with_attendees:
            # No change needed here, attendee is already a dict
            events_with_attendees[event_id]['attendees'].append(attendee)

    return [events_with_attendees[event['event_id']] for event in events]

def get_event_details_with_locations_attendees_db(event_id):
    """
    Fetch full details for a single event, including its description,
    locations, and attendees.
    """
    if not db:
        raise ConnectionError("Spanner database connection not initialized.")

    event_details = {}

    # 1. Fetch Event basic details (including new description)
    event_sql = """
        SELECT event_id, name, description, event_date
        FROM Event
        WHERE event_id = @event_id
    """
    params = {"event_id": event_id}
    param_types_map = {"event_id": param_types.STRING}
    event_fields = ["event_id", "name", "description", "event_date"]
    event_result = run_query(event_sql, params=params, param_types=param_types_map, expected_fields=event_fields)

    if not event_result:
        return None # Event not found
    event_details = event_result[0]

    # 2. Fetch Event Locations
    locations_sql = """
        SELECT l.location_id, l.name, l.description, l.latitude, l.longitude, l.address
        FROM Location AS l
        JOIN EventLocation AS el ON l.location_id = el.location_id
        WHERE el.event_id = @event_id
        ORDER BY l.name
    """
    # Params and param_types_map are the same as for event_sql
    location_fields = ["location_id", "name", "description", "latitude", "longitude", "address"]
    event_details["locations"] = run_query(locations_sql, params=params, param_types=param_types_map, expected_fields=location_fields)

    # 3. Fetch Event Attendees
    attendees_sql = """
        SELECT p.person_id, p.name
        FROM Person AS p
        JOIN Attendance AS a ON p.person_id = a.person_id
        WHERE a.event_id = @event_id
        ORDER BY p.name
    """
    # Params and param_types_map are the same
    attendee_fields = ["person_id", "name"]
    event_details["attendees"] = run_query(attendees_sql, params=params, param_types=param_types_map, expected_fields=attendee_fields)

    # Convert datetimes to ISO format if they are not already strings
    if isinstance(event_details.get('event_date'), datetime):
        event_details['event_date'] = event_details['event_date'].isoformat()

    # Ensure locations have float for lat/lon if they are Decimal or other numeric types
    for loc in event_details.get("locations", []):
        if loc.get("latitude") is not None: loc["latitude"] = float(loc["latitude"])
        if loc.get("longitude") is not None: loc["longitude"] = float(loc["longitude"])
    return event_details


# --- Custom Jinja Filter ---
@app.template_filter('humanize_datetime')
def _jinja2_filter_humanize_datetime(value, default="just now"):
    """
    Convert a datetime object to a human-readable relative time string.
    e.g., '5 minutes ago', '2 hours ago', '3 days ago'
    """
    if not value:
        return default
   
    dt_object = None
    if isinstance(value, str):
        try:
            # Attempt to parse ISO 8601 format.
            # .replace('Z', '+00:00') handles UTC 'Z' suffix for fromisoformat.
            dt_object = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            # Fallback to dateutil.parser for more general string formats
            try:
                dt_object = parser.parse(value)
            except (parser.ParserError, TypeError, ValueError) as e:
                app.logger.warning(f"Could not parse date string '{value}' in humanize_datetime: {e}")
                return str(value) # Return original string if unparseable
    elif isinstance(value, datetime):
        dt_object = value
    else:
        # If not a string or datetime, return its string representation
        return str(value)

    if dt_object is None: # Should have been handled, but as a safeguard
        app.logger.warning(f"Date value '{value}' resulted in None dt_object in humanize_datetime.")
        return str(value)

    now = datetime.now(timezone.utc)
    # Use dt_object for all datetime operations from here
    if dt_object.tzinfo is None or dt_object.tzinfo.utcoffset(dt_object) is None:
        # If dt_object is naive, assume it's UTC
        dt_object = dt_object.replace(tzinfo=timezone.utc)
    else:
        # Convert aware dates to UTC
        dt_object = dt_object.astimezone(timezone.utc)

    try:
        return humanize.naturaltime(now - dt_object)
    except TypeError:
        # Fallback or handle error if date calculation fails
        return dt_object.strftime("%Y-%m-%d %H:%M")


def get_person_by_name_db(name):
    """Fetch a person's ID by their name from Spanner."""
    if not db:
        logger.error("Error: Database connection is not available for get_person_by_name_db.")
        raise ConnectionError("Spanner database connection not initialized.")

    sql = "SELECT person_id FROM Person WHERE name = @name LIMIT 1"
    params = {"name": name}
    param_types_map = {"name": param_types.STRING}
    fields = ["person_id"] # Expected field from the SELECT
    try:
        results = run_query(sql, params=params, param_types=param_types_map, expected_fields=fields)
        person_id = results[0]['person_id'] if results else None
        if person_id:
            logger.info(f"Found person_id '{person_id}' for name '{name}'.")
        else:
            logger.warning(f"Could not find person_id for name '{name}'.")
        return person_id
    except Exception as e:
        logger.error(f"Error fetching person by name '{name}': {e}", exc_info=True)
        raise e

# --- Helper function to insert a post ---
def add_post_db(post_id, author_id, text, sentiment=None):
    """Inserts a new post into the Spanner database."""
    if not db:
        logger.error("Error: Database connection is not available for add_post_db.")
        raise ConnectionError("Spanner database connection not initialized.")

    def _insert_post(transaction):
        logger.debug(f"Transaction attempting to insert post_id: {post_id} by author_id: {author_id}")
        transaction.insert(
            table="Post",
            columns=[
                "post_id", "author_id", "text", "sentiment",
                "post_timestamp", "create_time"
            ],
            values=[(
                post_id, author_id, text, sentiment,
                datetime.now(timezone.utc),
                spanner.COMMIT_TIMESTAMP
            )]
        )
        logger.info(f"Post insertion prepared in transaction for post_id: {post_id}")

    try:
        db.run_in_transaction(_insert_post)
        logger.info(f"Successfully inserted post_id: {post_id}")
        return True
    except Exception as e:
        logger.error(f"Error inserting post (id: {post_id}): {e}", exc_info=True)
        return False

def add_full_event_with_details_db(event_id, event_name, description, event_date, locations_data, attendee_ids):
    """
    Inserts a new event with its title, description, multiple locations,
    and its first attendee into Spanner within a transaction.

    Args:
        event_id (str): The unique ID for the new event.
        event_name (str): Name of the event (maps to Event.name).
        description (str): Description of the event.
        event_date (datetime): Date/time of the event (timezone-aware recommended).
        locations_data (list[dict]): A list of location dictionaries. Each dict should contain:
                                     'name', 'description', 'latitude', 'longitude', 'address'.
        attendee_ids (list[str]): A list of person_ids for the attendees.

    Returns:
        bool: True if the transaction was successful, False otherwise.
    """
    if not db:
        logger.error("Error: Database connection is not available for add_full_event_with_details_db.")
        raise ConnectionError("Spanner database connection not initialized.")

    def _insert_event_and_attendee(transaction):
        logger.debug(f"Transaction attempting to insert event_id: {event_id} with name '{event_name}'")
        transaction.insert(
            table="Event",
            columns=[
                "event_id", "name", "description", "event_date", "create_time"
            ],
            values=[(
                event_id, event_name, description, event_date,
                spanner.COMMIT_TIMESTAMP
            )]
        )

        for i, loc_data in enumerate(locations_data):
            location_id = str(uuid.uuid4())
            logger.debug(f"Transaction attempting to insert location_id: {location_id} (Location {i+1}) for event {event_id}")
            transaction.insert(
                table="Location",
                columns=["location_id", "name", "description", "latitude", "longitude", "address", "create_time"],
                values=[(
                    location_id, loc_data.get("name"), loc_data.get("description"),
                    float(loc_data.get("latitude", 0.0)), float(loc_data.get("longitude", 0.0)),
                    loc_data.get("address"), spanner.COMMIT_TIMESTAMP
                )]
            )
            logger.debug(f"Transaction attempting to link event {event_id} with location {location_id}")
            transaction.insert(
                table="EventLocation",
                columns=["event_id", "location_id", "create_time"],
                values=[(event_id, location_id, spanner.COMMIT_TIMESTAMP)]
            )

        if attendee_ids:
            for attendee_id_to_add in attendee_ids:
                logger.debug(f"Transaction attempting to insert attendee {attendee_id_to_add} for event {event_id} into Attendance")
                transaction.insert(
                    table="Attendance",
                    columns=["event_id", "person_id", "attendance_time"],
                    values=[(event_id, attendee_id_to_add, spanner.COMMIT_TIMESTAMP)]
                )
        logger.info(f"Event {event_id} and related data prepared in transaction.")

    try:
        db.run_in_transaction(_insert_event_and_attendee)
        logger.info(f"Successfully inserted event {event_id} with details and attendees {attendee_ids}")
        return True
    except Exception as e:
        logger.error(f"Error inserting full event (event_id: {event_id}, attendees: {attendee_ids}): {e}", exc_info=True)
        return False

# --- Routes ---
@app.route('/')
def home():
    """Home page: Shows all posts and the events panel."""
    all_posts = []
    all_events_attendance = [] # Initialize

    if not db:
        flash("Database connection not available. Cannot load page data.", "danger")
    else:
        try:
            # Fetch both posts and events
            all_posts = get_all_posts_with_author_db()
            all_events_attendance = get_all_events_with_attendees_db() # Fetch events
        except Exception as e:
             flash(f"Failed to load page data: {e}", "danger")
             # Ensure variables are defined even on error
             all_posts = []
             all_events_attendance = []

    return render_template(
        'index.html',
        posts=all_posts,
        all_events_attendance=all_events_attendance, # Pass events to template
        google_maps_api_key=GOOGLE_MAPS_API_KEY, # For potential future use on home page
        google_maps_map_id=GOOGLE_MAPS_MAP_ID # Pass it to the template, ensuring consistency with the variable name used at definition
    )


@app.route('/person/<string:person_id>')
def person_profile(person_id):
    """Person profile page, fetching data from Spanner."""
    if not db:
        flash("Database connection not available. Cannot load profile.", "danger")
        abort(503) # Service Unavailable

    try:
        person = get_person_db(person_id)
        if not person:
            abort(404) # Person not found

        person_posts = get_posts_by_person_db(person_id)
        friends = get_friends_db(person_id)
        all_events_attendance = get_all_events_with_attendees_db()

    except Exception as e:
         flash(f"Failed to load profile data: {e}", "danger")
         # Redirect to home or show an error page might be better than aborting
         return render_template('person.html', person=person, person_posts=[], friends=[], all_events_attendance=[], error=True)


    return render_template(
        'person.html',
        person=person,
        person_posts=person_posts,
        friends=friends,
        all_events_attendance=all_events_attendance
    )

@app.route('/event/<string:event_id>')
def event_detail_page(event_id):
    """Event detail page showing description, locations on a map, and attendees."""
    if not db:
        flash("Database connection not available. Cannot load event details.", "danger")
        abort(503) # Service Unavailable

    if not GOOGLE_MAPS_API_KEY:
        flash("INSTAVIBE_GOOGLE_MAPS_API_KEY is not configured. Map functionality will be disabled.", "warning")

    event_data = None
    try:
        event_data = get_event_details_with_locations_attendees_db(event_id)
        if not event_data:
            logger.warning(f"Event with ID '{event_id}' not found in database.")
            abort(404) # Event not found
    except Exception as e:
        flash(f"Failed to load event data: {e}", "danger")
        logger.error(f"Error fetching event details for event_id '{event_id}': {e}", exc_info=True)
        return render_template('event_detail.html', event=None, error=True, google_maps_api_key=GOOGLE_MAPS_API_KEY, google_maps_map_id=GOOGLE_MAPS_MAP_ID)

    return render_template('event_detail.html', event=event_data, google_maps_api_key=GOOGLE_MAPS_API_KEY, google_maps_map_id=GOOGLE_MAPS_MAP_ID)


@app.route('/api/posts', methods=['POST'])
def add_post_api():
    """
    API endpoint to add a new post.
    Expects JSON body: {"author_name": "...", "text": "...", "sentiment": "..." (optional)}
    """
    if not db:
        return jsonify({"error": "Database connection not available"}), 503 # Service Unavailable

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400
    if 'author_name' not in data or 'text' not in data:
        return jsonify({"error": "Missing 'author_name' or 'text' in request body"}), 400

    author_name = data['author_name']
    text = data['text']
    sentiment = data.get('sentiment') # Optional, defaults to None if not provided

    # Basic input validation
    if not isinstance(author_name, str) or not author_name.strip():
         return jsonify({"error": "'author_name' must be a non-empty string"}), 400
    if not isinstance(text, str) or not text.strip():
         return jsonify({"error": "'text' must be a non-empty string"}), 400
    if sentiment is not None and not isinstance(sentiment, str):
         return jsonify({"error": "'sentiment' must be a string if provided"}), 400

    try:
        # 1. Find the author_id using the provided name
        author_id = get_person_by_name_db(author_name)
        if not author_id:
            return jsonify({"error": f"Author '{author_name}' not found"}), 404 # Not Found

        # 2. Generate a unique ID for the new post
        new_post_id = str(uuid.uuid4())

        # 3. Insert the post into the database
        success = add_post_db(
            post_id=new_post_id,
            author_id=author_id,
            text=text,
            sentiment=sentiment
        )

        if success:
            # 4. Return a success response
            post_data = {
                "message": "Post added successfully",
                "post_id": new_post_id,
                "author_id": author_id,
                "author_name": author_name, # Include for convenience
                "text": text,
                "sentiment": sentiment,
                # Provide an approximate timestamp (actual is set by DB)
                "post_timestamp": datetime.now(timezone.utc).isoformat()
            }
            return jsonify(post_data), 201 # 201 Created status code
        else:
            # Insertion failed for some reason (logged in add_post_db)
            return jsonify({"error": "Failed to save post to the database"}), 500 # Internal Server Error

    except ConnectionError as e:
         logger.error(f"ConnectionError during post add API call: {e}", exc_info=True)
         return jsonify({"error": "Database connection error during operation"}), 503
    except Exception as e:
        logger.error(f"Unexpected error processing add post request: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred"}), 500



@app.route('/api/events', methods=['POST'])
def add_event_api():
    """
    API endpoint to add a new event and its first attendee (simplified schema).
    Expects JSON body: {
        "event_name": "...", // Name of the event
        "description": "...", // Detailed description
        "event_date": "YYYY-MM-DDTHH:MM:SSZ" or "YYYY-MM-DDTHH:MM:SS+HH:MM",
        "locations": [ // List of location objects
            {"name": "...", "description": "...", "latitude": 0.0, "longitude": 0.0, "address": "..."}
        ],
        "attendee_names": ["...", "..."] // List of attendee names
    }
    """
    if not db:
        return jsonify({"error": "Database connection not available"}), 503

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    # --- Input Validation (Simplified) ---
    required_fields = ["event_name", "description", "event_date", "locations", "attendee_names"]
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    event_name = data['event_name'] 
    description = data['description']
    event_date_str = data['event_date']
    locations_data = data['locations']
    attendee_names = data['attendee_names']

    # Basic type checks
    if not isinstance(event_name, str) or not event_name.strip(): 
         return jsonify({"error": "'event_name' must be a non-empty string"}), 400 
    if not isinstance(description, str):
         return jsonify({"error": "'description' must be a string"}), 400
    if not isinstance(event_date_str, str) or not event_date_str.strip():
         return jsonify({"error": "'event_date' must be a non-empty string"}), 400
    if not isinstance(attendee_names, list) or not attendee_names: # Ensure it's a non-empty list
         return jsonify({"error": "'attendee_names' must be a non-empty list of strings"}), 400
    for name in attendee_names:
        if not isinstance(name, str) or not name.strip():
            return jsonify({"error": "Each name in 'attendee_names' must be a non-empty string"}), 400
    if not isinstance(locations_data, list):
        return jsonify({"error": "'locations' must be a list"}), 400
    if not locations_data: 
        return jsonify({"error": "'locations' list cannot be empty"}), 400

    for i, loc in enumerate(locations_data):
        if not isinstance(loc, dict):
            return jsonify({"error": f"Each item in 'locations' must be an object (error at index {i})"}), 400
        loc_req_fields = ["name", "latitude", "longitude"]
        missing_loc_fields = [f for f in loc_req_fields if f not in loc or not str(loc[f]).strip()] # Check for presence and non-empty string for name
        if missing_loc_fields:
            return jsonify({"error": f"Location at index {i} missing required fields or has empty values: {', '.join(missing_loc_fields)}"}), 400
        try:
            float(loc["latitude"])
            float(loc["longitude"])
        except (ValueError, TypeError):
            return jsonify({"error": f"Location at index {i} has invalid latitude/longitude. Must be numbers."}), 400
        # Optional fields like description and address can be checked if needed
        if "description" in loc and not isinstance(loc["description"], str):
            return jsonify({"error": f"Location at index {i} 'description' must be a string if provided."}), 400
        if "address" in loc and not isinstance(loc["address"], str):
            return jsonify({"error": f"Location at index {i} 'address' must be a string if provided."}), 400

    # --- Process Inputs (Simplified) ---
    try:
        # Parse timestamp (ISO 8601 format expected)
        event_date = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))

        # Spanner prefers timezone-aware datetimes.
        # Ensure it's aware (fromisoformat usually handles this if tz is present)
        if event_date.tzinfo is None or event_date.tzinfo.utcoffset(event_date) is None:
             # If input was naive, assume UTC as a sensible default
             logger.warning(f"Received naive datetime string '{event_date_str}'. Assuming UTC.")
             event_date = event_date.replace(tzinfo=timezone.utc)
        else:
             # Convert to UTC if it had a different offset
             event_date = event_date.astimezone(timezone.utc)


    except ValueError as e:
        logger.error(f"Invalid timestamp format for 'event_date': {event_date_str}. Details: {e}", exc_info=True)
        return jsonify({"error": f"Invalid timestamp format for 'event_date'. Use ISO 8601 (e.g., YYYY-MM-DDTHH:MM:SSZ or YYYY-MM-DDTHH:MM:SS+HH:MM). Details: {e}"}), 400

    try:
        logger.info(f"Processing add_event_api request for event '{event_name}'. Attendees: {attendee_names}")
        attendee_ids_to_add = []
        processed_attendees_info = []
        for attendee_name_str in attendee_names:
            attendee_id = get_person_by_name_db(attendee_name_str)
            if not attendee_id:
                logger.warning(f"Attendee '{attendee_name_str}' not found during event creation '{event_name}'.")
                return jsonify({"error": f"Attendee '{attendee_name_str}' not found"}), 404
            attendee_ids_to_add.append(attendee_id)
            processed_attendees_info.append({"id": attendee_id, "name": attendee_name_str})

        if not attendee_ids_to_add:
            logger.warning(f"No valid attendee IDs found for event '{event_name}'. Original names: {attendee_names}")
            return jsonify({"error": "No valid attendees found or provided."}), 400

        new_event_id = str(uuid.uuid4())
        logger.debug(f"Generated new event_id: {new_event_id} for event '{event_name}'")

        success = add_full_event_with_details_db(
            event_id=new_event_id,
            event_name=event_name,
            description=description,
            event_date=event_date,
            locations_data=locations_data,
            attendee_ids=attendee_ids_to_add,
        )

        if success:
            event_data = {
                "message": "Event and attendees added successfully",
                "event_id": new_event_id,
                "event_name": event_name,
                "description": description,
                "event_date": event_date.isoformat(),
                "locations": locations_data,
                "attendees": processed_attendees_info
            }
            logger.info(f"Event '{event_name}' (ID: {new_event_id}) created successfully.")
            return jsonify(event_data), 201
        else:
            logger.error(f"Failed to save event '{event_name}' (ID: {new_event_id}) to database.")
            return jsonify({"error": "Failed to save event and attendee to the database"}), 500

    except ConnectionError as e:
         logger.error(f"ConnectionError during event add API call for '{event_name}': {e}", exc_info=True)
         return jsonify({"error": "Database connection error during operation"}), 503
    except Exception as e:
        logger.error(f"Unexpected error processing add event request for '{event_name}': {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred"}), 500


# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    logger.warning(f"404 Not Found error: {e}. Request URL: {request.url}")
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
     logger.error(f"500 Internal Server Error: {e}. Request URL: {request.url}", exc_info=e.original_exception if hasattr(e, 'original_exception') else True)
     return render_template('500.html'), 500

@app.errorhandler(503)
def service_unavailable(e):
     logger.error(f"503 Service Unavailable error: {e}. Request URL: {request.url}", exc_info=e.original_exception if hasattr(e, 'original_exception') else True)
     return render_template('503.html'), 503





if __name__ == '__main__':
    # Check if db connection was successful before running
    if not db:
        logger.critical("\n--- Cannot start Flask app: Spanner database connection failed during initialization. ---")
        logger.critical("--- Please check GCP project, instance ID, database ID, permissions, and network connectivity. ---")
    else:
        logger.info("\n--- Starting Flask Development Server ---")
        # For production, use a proper WSGI server like Gunicorn.
        # Debug mode should be False in production.
        # The host '0.0.0.0' makes it accessible on your network.
        # The port is cast to int as uvicorn/gunicorn expect it.
        # Flask's default logger is used unless `log_config=None` is passed to uvicorn/gunicorn if they are configured to take over logging.
        # Our `setup_google_cloud_logging` configures the root logger, which Flask's app.logger will use.
        app.run(debug=os.environ.get("FLASK_DEBUG", "False").lower() == "true", host=APP_HOST, port=int(APP_PORT))