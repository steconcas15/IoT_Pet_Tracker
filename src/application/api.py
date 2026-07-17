# ==============================================================================
#                 MODULE IMPORTS & FLASK BLUEPRINTS SETUP
# ==============================================================================

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
auth_api = Blueprint('auth_api', __name__, url_prefix='/api/auth')

# ==============================================================================
#                            DIGITAL TWIN APIs
# ==============================================================================

# ----------------- HOME ENVIRONMENT CREATION (Main User / Admin) --------------
@dt_api.route('/', methods=['POST'])
@jwt_required()
def create_digital_twin():
    """
    Creates a new virtual Home environment uniquely associated with an Admin.
    Requires a valid JWT token. Uses get_jwt_identity() to securely extract the user ID.
    """
    try:
        # Retrieve the JSON payload
        data = request.get_json()

        # Securely extract the user ID directly from the validated token
        current_user_id = get_jwt_identity()

        # 'user_id' is removed from required_fields because we no longer trust client-side JSON for identity
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

        # 2. Register Admin permissions using the ID securely extracted from the token
        current_app.config['DB_SERVICE'].set_home_admin(dt_id, current_user_id)

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
@dt_api.route('/<string:dt_id>', methods=['DELETE'])
@jwt_required()
def delete_digital_twin(dt_id):
    """
    Completely removes a Home environment, its associated permissions, 
    and cascades the deletion to all associated Digital Replicas.
    Requires Admin authorization via JWT token.
    """
    try:
        # Retrieve the ID of the user making the request from the Token
        current_user_id = get_jwt_identity()

        # Check: Is the requesting user actually the admin of this home?
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({
                'error': 'Unauthorized. Only the administrator can delete this Home Environment.'
            }), 403

        # Check: Does the home actually exist? (We also save its data to dt_exists)
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        # --- CASCADE DELETE: Removal of associated Digital Replicas ---
        # Loop through the array of replicas linked to this home
        for replica in dt_exists.get("digital_replicas", []):
            try:
                # Call the DB Service method to physically destroy the document
                current_app.config['DB_SERVICE'].delete_dr(
                    dr_type=replica["type"], 
                    dr_id=replica["id"]
                )
            except Exception as e:
                # Print a warning in the terminal but continue with the other deletions
                print(f"[WARNING] Failed to delete replica {replica['id']} of type {replica['type']}: {str(e)}")

        # 1. Delete the Digital Twin via the Factory
        current_app.config['DT_FACTORY'].delete_dt(dt_id)

        # 2. Clean the database by removing all associated permissions (Admin and Viewers)
        current_app.config['DB_SERVICE'].remove_home_permissions(dt_id)

        return jsonify({
            'status': 'success',
            'message': f'Home environment {dt_id}, all its permissions, and all associated replicas successfully removed.'
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete Home Environment: {str(e)}'
        }), 500
    

# ==================================================================================================
#--------------------------------------------- USER ROLES & ACCESS ---------------------------------
# ==================================================================================================

# ----------------- ADD VIEWER (by the Admin) -----------------
@dt_api.route('/<string:dt_id>/viewers', methods=['POST'])
@jwt_required()
def add_viewer(dt_id):
    """
    Adds a viewer user to a specific Home Environment via their USERNAME.
    Requires a valid JWT token representing the Admin.
    """
    try:
        data = request.get_json()
        
        # Securely extract the user ID directly from the validated token
        current_user_id = get_jwt_identity()

        # We request 'viewer_username' instead of a hard-to-read MongoDB ID
        if not data or 'viewer_username' not in data:
            return jsonify({
                'error': 'Missing required fields. Please send viewer_username in the JSON body.'
            }), 400

        viewer_username = data['viewer_username']

        # 1. Verify that the user making the request (extracted from the token) is actually the admin
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
            return jsonify({'error': f'The user {viewer_username} is not registered on the platform.'}), 404
        
        # Extract the real MongoDB ID of the viewer
        viewer_id = str(viewer_user['_id'])

        # Prevent the admin from adding themselves as a viewer
        if viewer_id == current_user_id:
            return jsonify({'error': 'The admin is already the owner of this home and cannot also be a viewer.'}), 400

        # 4. Save the permission in the database
        current_app.config['DB_SERVICE'].add_home_viewer(dt_id, viewer_id)

        return jsonify({
            'status': 'success',
            'message': f'User {viewer_username} successfully added as viewer to Home {dt_id}',
            'data': {
                'home_id': dt_id,
                'viewer_id': viewer_id,
                'viewer_username': viewer_username,
                'role': 'viewer'
            }
        }), 201

    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add viewer: {str(e)}'}), 500
    

# ----------------- VIEWER REMOVAL (by the Admin) -----------------
@dt_api.route('/<string:dt_id>/viewers/<string:viewer_username>', methods=['DELETE'])
@jwt_required()
def remove_viewer(dt_id, viewer_username):
    """
    Removes a specific user's viewer access via their USERNAME.
    Requires a valid JWT token representing the Admin.
    """
    try:
        # Securely extract the requesting user's ID from the token
        current_user_id = get_jwt_identity()

        # Check: Is the requesting user actually the admin of this home?
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the admin can remove viewers.'}), 403

        # Check: Does the home exist?
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        # Search the database to find the viewer's ID starting from their username
        viewer_user = current_app.config['DB_SERVICE'].get_user_by_username(viewer_username)
        if not viewer_user:
             return jsonify({'error': f'The user {viewer_username} is not registered.'}), 404
             
        viewer_id = str(viewer_user['_id'])

        # Remove the permission from the database
        current_app.config['DB_SERVICE'].remove_home_viewer(dt_id, viewer_id)

        return jsonify({
            'status': 'success',
            'message': f'User {viewer_username} successfully removed from viewers of Home {dt_id}'
        }), 200

    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to remove viewer: {str(e)}'}), 500
    

# ----------------- Adding a room to a specific home -------------------
@dt_api.route('/<string:dt_id>/rooms', methods=['POST'])
@jwt_required()
def create_and_associate_room(dt_id):
    """
    Creates a "Room" type Digital Replica, validating the fields using DRFactory,
    and instantly associates it with the Home Environment.
    Requires a valid JWT token representing the Admin.
    """
    try:
        # Extract the ID of the user attempting to create the room
        current_user_id = get_jwt_identity()

        # Protection: Only the admin of the home can add rooms to it
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the home admin can add rooms.'}), 403

        raw_data = request.get_json()

        # 1. Verify if the house (Digital Twin) exists via the factory.
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found'}), 404

        # 2. Structure flat data to make it compatible with DRFactory.
        initial_data = {
            "profile": {
                "name": raw_data.get("name"),
                "description": raw_data.get("description", ""),
                "floor": raw_data.get("floor"),
                # Set permission_level in the profile (defaults to "allowed" if not provided)
                "permission_level": raw_data.get("permission_level", "allowed")
            },
            "data": {
                "esp32cam_device": raw_data.get("esp32cam_mac", ""),
                "ultrasonic_sensors": raw_data.get("ultrasonic_sensors", [])
            }
        }

        # Optionally handle permission_level in metadata if provided (legacy support)
        if "permission_level" in raw_data:
            initial_data["metadata"] = {"permission_level": raw_data["permission_level"]}

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
            'message': f'Room successfully validated, created and linked to Home {dt_id}.',
            'data': {
                'home_id': dt_id,
                'room_id': room_id,
                'room_data': validated_room
            }
        }), 201

    except ValueError as ve:
        # Pydantic will raise a ValueError if the rules in room.yaml are not met.
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add room: {str(e)}'}), 500


# ==============================================================================
#                            AUTHENTICATION APIs
# ==============================================================================

@auth_api.route('/register', methods=['POST'])
def register():
    """Register a new user on the platform."""
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required.'}), 400

        username = data['username']
        password = data['password']

        # Encrypt the password: NEVER save passwords in plain text!
        hashed_password = generate_password_hash(password)

        # Save the user to the database
        user_id = current_app.config['DB_SERVICE'].create_user(username, hashed_password)

        return jsonify({
            'status': 'success',
            'message': 'User registered successfully.',
            'data': {
                'user_id': user_id,
                'username': username
            }
        }), 201

    except ValueError as ve:
        # Catch the error if the username already exists (duplicate key)
        return jsonify({'error': str(ve)}), 409
    except Exception as e:
        return jsonify({'error': f'Failed to register user: {str(e)}'}), 500


@auth_api.route('/login', methods=['POST'])
def login():
    """Authenticate a user, verify the password, and return a JWT."""
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required.'}), 400

        # Retrieve the user from the database
        user = current_app.config['DB_SERVICE'].get_user_by_username(data['username'])

        # Check if the user exists and if the hashed password matches
        if not user or not check_password_hash(user['password_hash'], data['password']):
            return jsonify({'error': 'Invalid credentials.'}), 401

        # Generate the token by inserting the user's stringified ID as 'identity'
        user_id_str = str(user['_id'])
        access_token = create_access_token(identity=user_id_str)

        return jsonify({
            'status': 'success',
            'message': 'Login successful.',
            'access_token': access_token,  # The token to send to the frontend for future requests
            'data': {
                'user_id': user_id_str,
                'username': user['username']
            }
        }), 200

    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500
    

@auth_api.route('/logout', methods=['POST'])
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
    app.register_blueprint(auth_api)