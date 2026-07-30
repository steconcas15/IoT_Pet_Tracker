# ==============================================================================
#                 MODULE IMPORTS & FLASK BLUEPRINTS SETUP
# ==============================================================================
import os
import json
from werkzeug.utils import secure_filename

# Import Flask dependencies for routing, requests, JSON responses, and application context
from flask import Blueprint, request, jsonify, current_app

# Import Werkzeug security for safe password hashing
from werkzeug.security import generate_password_hash, check_password_hash

# Import datetime for handling timestamps
from datetime import datetime

# Import ObjectId for handling MongoDB document identifiers
from bson import ObjectId

# Import JWT tools for authentication and route protection
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

# Create a blueprint for Digital Twin (DT) specific APIs with a base URL prefix
dt_api = Blueprint('dt_api', __name__, url_prefix='/api/dt')

# Create a blueprint for Digital Replica (DR) specific APIs with a base URL prefix
dr_api = Blueprint('dr_api', __name__, url_prefix='/api/dr')

# Create a blueprint for Digital Twin management and orchestration APIs with a base URL prefix
dt_management_api = Blueprint('dt_management_api', __name__, url_prefix='/api/dt-management')

# Create a blueprint for Authentication APIs with a base URL prefix
user_api = Blueprint('user_api', __name__, url_prefix='/api/user')

# Create the folder to save photos if it doesn't exist
UPLOAD_FOLDER = 'uploads/cameras'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==============================================================================
#                            DIGITAL TWIN APIs (dt_api)
# ==============================================================================

# ----------------- HOME ENVIRONMENT CREATION (Main User / Admin) --------------
@dt_api.route('/', methods=['POST'])
@jwt_required()
def create_digital_twin():
    """
    Creates a new virtual Home environment uniquely associated with an Admin.
    Requires a valid JWT token. Uses get_jwt_identity() to securely extract the user ID.
    Expects JSON payload: { "name": "...", "description": "..." }
    """
    try:
        # Retrieve the JSON payload
        data = request.get_json()

        # Securely extract the user ID directly from the validated token
        current_user_id = get_jwt_identity()

        required_fields = ['name', 'description']
        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Missing required fields: name, description'
            }), 400

        # 1. Create the Digital Twin via the Factory
        dt_id = current_app.config['DT_FACTORY'].create_dt(
            name=data['name'],
            description=data['description']
        )

        # 2. Update the user profile by adding the home to owned_homes
        current_app.config['DB_SERVICE'].add_owned_home(current_user_id, dt_id)

        return jsonify({
            'status': 'success',
            'message': 'Home environment created successfully',
            'data': {
                'home_id': dt_id,
                'home_name': data['name'],
                'admin_user_id': current_user_id,
                'role_assigned': 'admin'
            }
        }), 201

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to create Home Environment: {str(e)}'
        }), 500


# ----------------- HOME ENVIRONMENT REMOVAL (Admin) -----------------
@dt_api.route('/', methods=['DELETE'])
@jwt_required()
def delete_digital_twin():
    """
    Completely removes a Home environment and cascades the deletion to all associated 
    Digital Replicas. Also cleans up the home ID from all user profiles (admins and viewers).
    Requires Admin authorization via JWT token.
    Expects JSON payload: { "dt_id": "string" }
    """
    try:
        data = request.get_json()
        if not data or 'dt_id' not in data:
            return jsonify({'error': 'Missing required field in payload: dt_id'}), 400
            
        dt_id = data['dt_id']
        current_user_id = get_jwt_identity()

        # Check: Is the requesting user actually the admin of this home?
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the administrator can delete this Home Environment.'}), 403

        # Check: Does the home actually exist? 
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        # --- CASCADE DELETE: Removal of associated Digital Replicas ---
        for replica in dt_exists.get("digital_replicas", []):
            try:
                current_app.config['DB_SERVICE'].delete_dr(dr_type=replica["type"], dr_id=replica["id"])
            except Exception as e:
                print(f"[WARNING] Failed to delete replica {replica['id']} of type {replica['type']}: {str(e)}")

        # 1. Delete the Digital Twin via the Factory
        current_app.config['DT_FACTORY'].delete_dt(dt_id)

        # 2. Global Cleanup: Remove the home ID from the arrays of ALL users
        current_app.config['DB_SERVICE'].remove_home_from_all_users(dt_id)

        return jsonify({
            'status': 'success',
            'message': f'Home environment {dt_id} and all associated replicas successfully removed.'
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to delete Home Environment: {str(e)}'}), 500
    

# ==============================================================================
#                 DIGITAL TWIN MANAGEMENT APIs (dt_management_api)
# ==============================================================================

# ----------------- ADD VIEWER (by the Admin) -----------------
@dt_management_api.route('/viewers', methods=['POST'])
@jwt_required()
def add_viewer():
    """
    Adds a viewer user to a specific Home Environment via their USERNAME.
    Updates the viewer's 'viewable_homes' array in their profile.
    Requires a valid JWT token representing the Admin.
    Expects JSON payload: { "dt_id": "string", "viewer_username": "string" }
    """
    try:
        data = request.get_json()
        
        if not data or 'dt_id' not in data or 'viewer_username' not in data:
            return jsonify({'error': 'Missing required fields: dt_id, viewer_username'}), 400

        dt_id = data['dt_id']
        viewer_username = data['viewer_username']
        current_user_id = get_jwt_identity()

        # 1. Verify that the user making the request is actually the admin
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the administrator can add viewers.'}), 403

        # 2. Verify the existence of the home
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        # 3. Search for the viewer in the database via their username
        viewer_user = current_app.config['DB_SERVICE'].get_user_by_username(viewer_username)
        if not viewer_user:
            return jsonify({'error': f'The user {viewer_username} is not registered.'}), 404
        
        viewer_id = str(viewer_user['_id'])

        # Prevent the admin from adding themselves as a viewer
        if viewer_id == current_user_id:
            return jsonify({'error': 'The admin cannot also be a viewer.'}), 400

        # Check if the user is already a viewer
        if dt_id in viewer_user.get('data', {}).get('viewable_homes', []):
            return jsonify({'error': 'The user is already a viewer of this home.'}), 400

        # 4. Save the permission in the user's viewable_homes array
        current_app.config['DB_SERVICE'].add_viewable_home(viewer_id, dt_id)

        return jsonify({
            'status': 'success',
            'message': f'User {viewer_username} added as viewer to Home {dt_id}'
        }), 201

    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add viewer: {str(e)}'}), 500
    

# ----------------- VIEWER REMOVAL (by the Admin) -----------------
@dt_management_api.route('/viewers', methods=['DELETE'])
@jwt_required()
def remove_viewer():
    """
    Removes a specific user's viewer access via their USERNAME.
    Requires a valid JWT token representing the Admin.
    Expects JSON payload: { "dt_id": "string", "viewer_username": "string" }
    """
    try:
        data = request.get_json()

        if not data or 'dt_id' not in data or 'viewer_username' not in data:
            return jsonify({'error': 'Missing required fields: dt_id, viewer_username'}), 400

        dt_id = data['dt_id']
        viewer_username = data['viewer_username']
        current_user_id = get_jwt_identity()

        # Check: Is the requesting user actually the admin of this home?
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the admin can remove viewers.'}), 403

        # Search the database to find the viewer
        viewer_user = current_app.config['DB_SERVICE'].get_user_by_username(viewer_username)
        if not viewer_user:
             return jsonify({'error': f'The user {viewer_username} is not registered.'}), 404
             
        viewer_id = str(viewer_user['_id'])

        # Remove the permission from the user's viewable_homes array
        current_app.config['DB_SERVICE'].remove_viewable_home(viewer_id, dt_id)

        return jsonify({
            'status': 'success',
            'message': f'User {viewer_username} removed from viewers of Home {dt_id}'
        }), 200

    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to remove viewer: {str(e)}'}), 500


# ==============================================================================
#                            DIGITAL REPLICA APIs (dr_api)
# ==============================================================================

# ----------------- ADDING A ROOM TO A SPECIFIC HOME -------------------
@dr_api.route('/rooms', methods=['POST'])
@jwt_required()
def create_and_associate_room():
    """
    Creates a "Room" type Digital Replica, validating the fields using DRFactory,
    and instantly associates it with the Home Environment.
    Requires a valid JWT token representing the Admin.
    Expects JSON payload: { "dt_id": "string", "name": "...", "floor": ... }
    """
    try:
        raw_data = request.get_json()

        if not raw_data or 'dt_id' not in raw_data:
            return jsonify({'error': 'Missing required field in payload: dt_id'}), 400

        dt_id = raw_data['dt_id']
        room_name = raw_data.get("name") # Extract the requested room name
        current_user_id = get_jwt_identity()

        # Protection: Only the admin of the home can add rooms to it
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the home admin can add rooms.'}), 403

        # 1. Verify if the house (Digital Twin) exists via the factory.
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found'}), 404

        # --- NEW CHECK: Avoid rooms with the same name ---
        # Check all digital replicas associated with this home
        for replica in dt_exists.get("digital_replicas", []):
            if replica.get("type") == "room":
                # Retrieve room data from the database
                existing_room = current_app.config['DB_SERVICE'].get_dr("room", replica["id"])
                # If the room exists and its name matches, block the request
                if existing_room and existing_room.get("profile", {}).get("name") == room_name:
                    return jsonify({'error': f'A room named "{room_name}" already exists in this home.'}), 409
        # ---------------------------------------------------------

        # 2. Structure flat data to make it compatible with DRFactory.
        initial_data = {
            "profile": {
                "name": room_name,
                "description": raw_data.get("description", ""),
                "floor": raw_data.get("floor"),
                "permission_level": raw_data.get("permission_level", "allowed")
            },
            "data": {
                "esp32cam_device": raw_data.get("esp32cam_mac", ""),
                "ultrasonic_sensors": raw_data.get("ultrasonic_sensors", [])
            }
        }

        # 3. PYDANTIC VALIDATION: delegate creation and validation to the DRFactory.
        validated_room = current_app.config['DR_FACTORY_ROOM'].create_dr(
            dr_type='room',
            initial_data=initial_data
        )

        # 4. Save the validated replica to the database
        room_id = current_app.config['DB_SERVICE'].save_dr(
            dr_type='room',
            dr_data=validated_room
        )

        # 5. NATURAL ASSOCIATION: Link the new room to the Digital Twin
        current_app.config['DT_FACTORY'].add_digital_replica(
            dt_id=dt_id,
            dr_type='room',
            dr_id=room_id
        )

        return jsonify({
            'status': 'success',
            'message': f'Room successfully validated, created and linked.',
            'data': {
                'home_id': dt_id,
                'room_id': room_id
            }
        }), 201

    except ValueError as ve:
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add room: {str(e)}'}), 500


# ----------------- ADDING A DOOR TO A SPECIFIC HOME -------------------
@dr_api.route('/doors', methods=['POST'])
@jwt_required()
def create_and_associate_door():
    """
    Creates a "Door" type Digital Replica, validating the fields using DRFactory,
    and instantly associates it with the Home Environment.
    Requires a valid JWT token representing the Admin.
    Expects JSON payload: { "dt_id": "string", "name": "...", "description": "..." }
    """
    try:
        raw_data = request.get_json()

        if not raw_data or 'dt_id' not in raw_data or 'name' not in raw_data:
            return jsonify({'error': 'Missing required fields in payload: dt_id, name'}), 400

        dt_id = raw_data['dt_id']
        door_name = raw_data['name']
        current_user_id = get_jwt_identity()

        # Protection: Only the admin of the home can add doors to it
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the home admin can add doors.'}), 403

        # 1. Verify if the house (Digital Twin) exists via the factory.
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found'}), 404

        # 2. Prevent duplicate doors with the same name inside the same home
        for replica in dt_exists.get("digital_replicas", []):
            if replica.get("type") == "door":
                # Retrieve the door data from the database
                existing_door = current_app.config['DB_SERVICE'].get_dr("door", replica["id"])
                # If the door exists and the name matches, block the request
                if existing_door and existing_door.get("profile", {}).get("name") == door_name:
                    return jsonify({'error': f'A door named "{door_name}" already exists in this home.'}), 409

        # 3. Structure flat data to make it compatible with DRFactory.
        # Note: sensor_status will automatically be set to "UNKNOWN" by initialization rules in door.yaml
        initial_data = {
            "profile": {
                "name": door_name,
                "description": raw_data.get("description", "")
            }
        }

        # 4. PYDANTIC VALIDATION: delegate creation and validation to the DRFactory.
        validated_door = current_app.config['DR_FACTORY_DOOR'].create_dr(
            dr_type='door',
            initial_data=initial_data
        )

        # 5. Save the validated replica to the database
        door_id = current_app.config['DB_SERVICE'].save_dr(
            dr_type='door',
            dr_data=validated_door
        )

        # 6. NATURAL ASSOCIATION: Link the new door to the Digital Twin
        current_app.config['DT_FACTORY'].add_digital_replica(
            dt_id=dt_id,
            dr_type='door',
            dr_id=door_id
        )

        return jsonify({
            'status': 'success',
            'message': f'Door successfully validated, created and linked.',
            'data': {
                'home_id': dt_id,
                'door_id': door_id,
                'door_name': door_name
            }
        }), 201

    except ValueError as ve:
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add door: {str(e)}'}), 500


# ----------------- REMOVING A DOOR FROM A SPECIFIC HOME -------------------
@dr_api.route('/doors', methods=['DELETE'])
@jwt_required()
def remove_door():
    """
    Removes a "Door" type Digital Replica from the Database and unlinks it from the Home.
    Requires a valid JWT token representing the Admin.
    Expects JSON payload: { "dt_id": "string", "door_id": "string" }
    """
    try:
        raw_data = request.get_json()

        if not raw_data or 'dt_id' not in raw_data or 'door_id' not in raw_data:
            return jsonify({'error': 'Missing required fields in payload: dt_id, door_id'}), 400

        dt_id = raw_data['dt_id']
        door_id = raw_data['door_id']
        current_user_id = get_jwt_identity()

        # Protection: Only the admin of the home can remove doors
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the home admin can remove doors.'}), 403

        # 1. Verify if the house (Digital Twin) exists
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found'}), 404

        # 2. Check if the door is actually part of this specific Digital Twin
        door_linked = any(
            replica.get("id") == door_id and replica.get("type") == "door" 
            for replica in dt_exists.get("digital_replicas", [])
        )
        
        if not door_linked:
            return jsonify({'error': 'The specified door is not linked to this Home Environment.'}), 404

        # 3. Remove the specific door document from the MongoDB collection
        current_app.config['DB_SERVICE'].delete_dr(
            dr_type='door', 
            dr_id=door_id
        )

        # 4. Remove the reference of the door from the Digital Twin's array
        current_app.config['DT_FACTORY'].remove_digital_replica(
            dt_id=dt_id,
            dr_type='door',
            dr_id=door_id
        )

        return jsonify({
            'status': 'success',
            'message': f'Door {door_id} successfully deleted and unlinked from Home {dt_id}.'
        }), 200

    except ValueError as ve:
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to delete door: {str(e)}'}), 500


# ----------------- DEVICE AUTHENTICATION (LOGIN) -------------------
@dr_api.route('/rooms/auth', methods=['POST'])
def device_login():
    """
    Endpoint for automatic authentication of IoT devices.
    The device sends its name. The server checks the DB and issues a JWT.
    """
    data = request.get_json()
    if not data or 'room_name' not in data:
        return jsonify({'error': 'Device credentials missing'}), 400

    room_name = data.get('room_name')

    # SQL/NoSQL QUERY (As per your schema): Verify that the device exists in the DB
    db_service = current_app.config['DB_SERVICE']
    query = {"profile.name": room_name}
    rooms = db_service.query_drs("room", query)

    if not rooms:
        return jsonify({'error': 'Unauthorized or nonexistent device'}), 401

    # HTTP 200 {JWT} (As per your schema): Generate a token without expiration (or long-lived)
    # for the device, using "device_<room_name>" as identity
    access_token = create_access_token(identity=f"device_{room_name}")
    
    return jsonify({
        'status': 'success',
        'access_token': access_token
    }), 200


# ----------------- PHOTO RECEPTION (TELEMETRY) FROM ESP32-CAM -------------------
@dr_api.route('/rooms/telemetry', methods=['POST'])
@jwt_required()
def receive_telemetry():
    """
    Receives telemetry (JSON) and photo (JPEG) from ESP32-CAM in multipart/form-data format.
    Requires a valid JWT token (Bearer) for authorization.
    """
    try:
        # 1. Retrieve the textual part (the JSON) from the form-data
        raw_data = request.form.get('data')
        if not raw_data:
            return jsonify({'error': 'JSON data field missing in the payload'}), 400
            
        # Parse the string into a Python dictionary
        try:
            telemetry_data = json.loads(raw_data)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON format'}), 400

        home_id = telemetry_data.get('home_id')
        room_name = telemetry_data.get('room_name')

        if not home_id or not room_name:
            return jsonify({'error': 'home_id or room_name missing in JSON'}), 400

        # 2. Retrieve the image file from the form-data
        if 'image' not in request.files:
            return jsonify({'error': 'Image file missing in the request'}), 400
            
        file = request.files['image']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # 3. Save the image to disk
        if file:
            # Generate a unique name based on the room and current timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = secure_filename(f"{room_name}_{timestamp}.jpg")
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            # Physically save the file
            file.save(filepath)
            
            # OPTIONAL: Here you could query the DB to update the Digital Replica 
            # of the room inserting the path of the last taken photo.

            return jsonify({
                'status': 'success',
                'message': 'Photo received and saved successfully',
                'data': {
                    'room_name': room_name,
                    'saved_path': filepath
                }
            }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error saving telemetry: {str(e)}'}), 500


# ==============================================================================
#                            AUTHENTICATION APIs (user_api)
# ==============================================================================

@user_api.route('/register', methods=['POST'])
def register():
    """Register a new user on the platform using the user.yaml template via DRFactory."""
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required.'}), 400

        username = data['username']
        password = data['password']

        # Encrypt the password: NEVER save passwords in plain text!
        hashed_password = generate_password_hash(password)

        # Ensure the unique index on 'profile.username' is established
        current_app.config['DB_SERVICE']._init_users_collection()

        # 1. Structure the data to make it compatible with user.yaml
        initial_data = {
            "profile": {
                "username": username,
                "password": hashed_password
            },
            "data": {
                "owned_homes": [],
                "viewable_homes": []
            }
        }

        # 2. PYDANTIC VALIDATION: delegate creation to the DRFactory
        validated_user = current_app.config['DR_FACTORY_USER'].create_dr(
            dr_type='user',
            initial_data=initial_data
        )

        # 3. Save the validated replica (the user) to the database
        user_id = current_app.config['DB_SERVICE'].save_dr(
            dr_type='user',
            dr_data=validated_user
        )

        return jsonify({
            'status': 'success',
            'message': 'User registered successfully.',
            'data': {
                'user_id': user_id,
                'username': username
            }
        }), 201

    except ValueError as ve:
        # Catch Pydantic validation errors
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        # Catch duplicate username errors from MongoDB unique index
        if "duplicate key error" in str(e).lower():
            return jsonify({'error': 'This username is already in use.'}), 409
        return jsonify({'error': f'Failed to register user: {str(e)}'}), 500


@user_api.route('/login', methods=['POST'])
def login():
    """Authenticate a user, verify the password, and return a JWT."""
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required.'}), 400

        # Retrieve the user from the database via the nested profile.username
        user = current_app.config['DB_SERVICE'].get_user_by_username(data['username'])

        # Check if the user exists and if the hashed password inside 'profile' matches
        if not user or not check_password_hash(user['profile']['password'], data['password']):
            return jsonify({'error': 'Invalid credentials.'}), 401

        # Generate the token by inserting the user's stringified ID as 'identity'
        user_id_str = str(user['_id'])
        access_token = create_access_token(identity=user_id_str)

        return jsonify({
            'status': 'success',
            'message': 'Login successful.',
            'access_token': access_token,
            'data': {
                'user_id': user_id_str,
                'username': user['profile']['username']
            }
        }), 200

    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500
    

@user_api.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """
    Dummy endpoint to confirm client-side logout.
    In a stateless JWT architecture, the server does not track logged-in users.
    Logout is achieved by the frontend deleting the token from its local storage.
    """
    return jsonify({
        "status": "success", 
        "message": "Logout successful. Please remove the token on the client side."
    }), 200


# ==============================================================================
#                       BLUEPRINTS REGISTRATION UTILITY
# ==============================================================================

def register_api_blueprints(app):
    """Register all API blueprints with the Flask app"""
    app.register_blueprint(dt_api)
    app.register_blueprint(dr_api)
    app.register_blueprint(dt_management_api)
    app.register_blueprint(user_api)