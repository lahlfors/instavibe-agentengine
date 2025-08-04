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


app = Flask(__name__)
# Load environment variables from root .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

app.secret_key = os.environ.get("INSTAVIBE_FLASK_SECRET_KEY", "a_default_secret_key_for_dev")
app.register_blueprint(ally_bp)

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
    print("INFO: The INSTAVIBE_GOOGLE_MAPS_API_KEY environment variable is not set. Mapping features relying on this key may be limited or non-functional.")

if not GOOGLE_MAPS_MAP_ID:
    print("INFO: The INSTAVIBE_GOOGLE_MAPS_MAP_ID environment variable is not set. Specific map styling or features may not be applied.")

if not PROJECT_ID:
    # This check is critical for Spanner client initialization.
    raise ValueError("CRITICAL: COMMON_GOOGLE_CLOUD_PROJECT environment variable not set. Application cannot start.")

# --- Spanner Client Initialization ---
# PROJECT_ID is now sourced from COMMON_GOOGLE_CLOUD_PROJECT, critical check above handles it.

db = None
try:
    print(f"Attempting to initialize Spanner client with Project ID: {PROJECT_ID}") # Add this log
    spanner_client = spanner.Client(project=PROJECT_ID)
    instance = spanner_client.instance(INSTANCE_ID) # Ensure INSTANCE_ID is defined
    database = instance.database(DATABASE_ID)       # Ensure DATABASE_ID is defined
    print(f"Attempting to connect to Spanner: {instance.name}/databases/{database.name}")

    if not instance.exists():
        print(f"CRITICAL Error: Spanner instance '{INSTANCE_ID}' does not exist in project '{PROJECT_ID}'.")
        raise RuntimeError(f"Spanner instance '{INSTANCE_ID}' not found in project '{PROJECT_ID}'. Application cannot start.")

    if not database.exists():
        print(f"CRITICAL Error: Database '{DATABASE_ID}' does not exist in instance '{INSTANCE_ID}'.")
        # Optionally, you could mention creating the database here if that's part of your SOPs
        raise RuntimeError(f"Spanner database '{DATABASE_ID}' not found in instance '{INSTANCE_ID}'. Application cannot start.")
    else:
        print("Spanner Database connection check successful (database exists).")
        db = database

except exceptions.NotFound as e: # Catch specific Spanner NotFound
    print(f"CRITICAL Spanner Error (NotFound): {e}. This usually means instance or database details are incorrect or they don't exist.")
    raise RuntimeError(f"Spanner resource not found: {e}. Application cannot start.") from e
except exceptions.GoogleAPICallError as e: # Catch broader API call errors
    print(f"CRITICAL Spanner API Call Error: {e}. This could be permissions, network, or configuration issues.")
    raise RuntimeError(f"Spanner API call failed: {e}. Application cannot start.") from e
except Exception as e: # Catch any other unexpected errors during initialization
    print(f"CRITICAL Unexpected error during Spanner initialization: {e}")
    traceback.print_exc() # Print full traceback for unexpected errors
    raise RuntimeError(f"Unexpected error during Spanner initialization: {e}. Application cannot start.") from e

# Final check after try-except block
if db is None:
    print("CRITICAL: Spanner database object 'db' is None after initialization attempts. This should not happen if exceptions are raised correctly.")
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
        print("Error: Database connection is not available.")
        raise ConnectionError("Spanner database connection not initialized.")

    results_list = []
    print(f"--- Executing SQL ---")
    print(f"SQL: {sql}")
    if params:
        print(f"Params: {params}")
    print("----------------------")

    try:
        with db.snapshot() as snapshot:
            results = snapshot.execute_sql(
                sql,
                params=params,
                param_types=param_types
            )

            # --- MODIFICATION START ---
            # Define field names based on the expected_fields argument
            # This avoids accessing results.fields which caused the error
            field_names = expected_fields
            if not field_names:
                 # Fallback or raise error if expected_fields were not provided
                 # For now, let's try the potentially failing way if not provided
                 print("Warning: expected_fields not provided to run_query. Attempting dynamic lookup.")
                 try:
                     field_names = [field.name for field in results.fields]
                 except AttributeError as e:
                     print(f"Error accessing results.fields even as fallback: {e}")
                     print("Cannot process results without field names.")
                     # Decide: raise error or return empty list?
                     raise ValueError("Could not determine field names for query results.") from e


            print(f"Using field names: {field_names}")
            # --- MODIFICATION END ---

            for row in results:
                # Now zip the known field names with the row values (which are lists)
                if len(field_names) != len(row):
                     print(f"Warning: Mismatch between number of field names ({len(field_names)}) and row values ({len(row)})")
                     print(f"Fields: {field_names}")
                     print(f"Row: {row}")
                     # Skip this row or handle error appropriately
                     continue # Skip malformed row for now
                results_list.append(dict(zip(field_names, row)))

            print(f"Query successful, fetched {len(results_list)} rows.")

    except (exceptions.NotFound, exceptions.PermissionDenied, exceptions.InvalidArgument) as spanner_err:
        print(f"Spanner Error ({type(spanner_err).__name__}): {spanner_err}")
        flash(f"Database error: {spanner_err}", "danger")
        return []
    except ValueError as e: # Catch the ValueError we might raise above
         print(f"Query Processing Error: {e}")
         flash("Internal error processing query results.", "danger")
         return []
    except Exception as e:
        print(f"An unexpected error occurred during query execution or processing: {e}")
        traceback.print_exc()
        flash(f"An unexpected server error occurred while fetching data.", "danger")
        raise e

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
            abort(404) # Event not found
    except Exception as e:
        flash(f"Failed to load event data: {e}", "danger")
        # Log the error for debugging
        print(f"Error fetching event {event_id}: {e}")
        traceback.print_exc()
        # Render the page with an error state or redirect
        return render_template('event_detail.html', event=None, error=True, google_maps_api_key=GOOGLE_MAPS_API_KEY)

    return render_template('event_detail.html', event=event_data, google_maps_api_key=GOOGLE_MAPS_API_KEY)


# --- Internal Endpoint for Toolbox ---
@app.route('/internal/create_event', methods=['POST'])
def internal_create_event():
    """
    Internal API endpoint for use by the genai-toolbox's http tool.
    This contains the complex, transactional logic for creating an event.
    """
    if not db:
        return jsonify({"error": "Database connection not available"}), 503

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    # (The following logic is moved from the old add_event_api)
    # --- Input Validation ---
    required_fields = ["event_name", "description", "event_date", "locations", "attendee_names"]
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({"error": f"Missing required fields: {', '.join(missing_fields)}"}), 400

    event_name = data['event_name']
    description = data['description']
    event_date_str = data['event_date']
    locations_data = data['locations']
    attendee_names = data['attendee_names']

    if not isinstance(attendee_names, list) or not attendee_names:
        return jsonify({"error": "'attendee_names' must be a non-empty list of strings"}), 400
    if not isinstance(locations_data, list) or not locations_data:
        return jsonify({"error": "'locations' must be a non-empty list"}), 400

    # --- Process Inputs ---
    try:
        event_date = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        else:
            event_date = event_date.astimezone(timezone.utc)
    except ValueError as e:
        return jsonify({"error": f"Invalid timestamp format for 'event_date': {e}"}), 400

    try:
        # 1. Find person_ids for all attendee names
        attendee_ids_to_add = []
        processed_attendees_info = []
        for name in attendee_names:
            person_id = get_person_by_name_db(name)
            if not person_id:
                return jsonify({"error": f"Attendee '{name}' not found"}), 404
            attendee_ids_to_add.append(person_id)
            processed_attendees_info.append({"id": person_id, "name": name})

        # 2. Generate a unique ID for the new event
        new_event_id = str(uuid.uuid4())

        # 3. Insert the event and all attendees atomically
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
            }
            return jsonify(event_data), 201
        else:
            return jsonify({"error": "Failed to save event to the database"}), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "An internal server error occurred"}), 500


# --- Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404 # You'll need to create 404.html

@app.errorhandler(500)
def internal_server_error(e):
     # Log the error e
     print(f"Internal Server Error: {e}")
     return render_template('500.html'), 500 # You'll need to create 500.html

@app.errorhandler(503)
def service_unavailable(e):
     # Log the error e
     print(f"Service Unavailable Error: {e}")
     return render_template('503.html'), 503 # You'll need to create 503.html


# --- Helper Functions for Internal Endpoint ---
# These are kept because the internal endpoint still needs them.

def get_person_by_name_db(name):
    """Fetch a person's ID by their name from Spanner."""
    if not db:
        raise ConnectionError("Spanner database connection not initialized.")
    sql = "SELECT person_id FROM Person WHERE name = @name LIMIT 1"
    params = {"name": name}
    param_types_map = {"name": param_types.STRING}
    fields = ["person_id"]
    try:
        results = run_query(sql, params=params, param_types=param_types_map, expected_fields=fields)
        return results[0]['person_id'] if results else None
    except Exception as e:
        print(f"Error fetching person by name '{name}': {e}")
        raise e

def add_full_event_with_details_db(event_id, event_name, description, event_date, locations_data, attendee_ids):
    """
    Inserts a new event with its title, description, multiple locations,
    and its attendees into Spanner within a transaction.
    """
    if not db:
        raise ConnectionError("Spanner database connection not initialized.")

    def _insert_event_and_attendee(transaction):
        transaction.insert(
            table="Event",
            columns=["event_id", "name", "description", "event_date", "create_time"],
            values=[(event_id, event_name, description, event_date, spanner.COMMIT_TIMESTAMP)]
        )
        for loc_data in locations_data:
            location_id = str(uuid.uuid4())
            transaction.insert(
                table="Location",
                columns=["location_id", "name", "description", "latitude", "longitude", "address", "create_time"],
                values=[(
                    location_id, loc_data.get("name"), loc_data.get("description"),
                    float(loc_data.get("latitude", 0.0)), float(loc_data.get("longitude", 0.0)),
                    loc_data.get("address"), spanner.COMMIT_TIMESTAMP
                )]
            )
            transaction.insert(
                table="EventLocation",
                columns=["event_id", "location_id", "create_time"],
                values=[(event_id, location_id, spanner.COMMIT_TIMESTAMP)]
            )
        if attendee_ids:
            for attendee_id_to_add in attendee_ids:
                transaction.insert(
                    table="Attendance",
                    columns=["event_id", "person_id", "attendance_time"],
                    values=[(event_id, attendee_id_to_add, spanner.COMMIT_TIMESTAMP)]
                )
    try:
        db.run_in_transaction(_insert_event_and_attendee)
        return True
    except Exception as e:
        traceback.print_exc()
        return False


if __name__ == '__main__':
    # Check if db connection was successful before running
    if not db:
        print("\n--- Cannot start Flask app: Spanner database connection failed during initialization. ---")
        print("--- Please check GCP project, instance ID, database ID, permissions, and network connectivity. ---")
    else:
        print("\n--- Starting Flask Development Server ---")
        # Use debug=True only in development! It reloads code and provides better error pages.
        # Use host='0.0.0.0' to make it accessible on your network (e.g., from a VM)
        app.run(debug=True, host=APP_HOST, port=int(APP_PORT)) # Ensure APP_PORT is int, and uses updated INSTAVIBE_APP_HOST/PORT