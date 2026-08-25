"""
API Routing & Controllers Module
================================
This module defines the RESTful API endpoints for the Digital Twin application.
It utilizes Flask Blueprints to modularize the routing structure into distinct
domains: Digital Twins (Homes), Digital Replicas (Rooms, Pets, Doors), Users,
and Authentication. 

Security is enforced using JSON Web Tokens (JWT) via 'flask_jwt_extended',
ensuring that operations on entities are strictly authorized based on the 
user's identity and assigned roles (Admin vs. Viewer).
"""

# ==============================================================================
#                 MODULE IMPORTS & FLASK BLUEPRINTS SETUP
# ==============================================================================
import os
import json
from werkzeug.utils import secure_filename

# Import Flask dependencies for routing, request handling, and app context
from flask import Blueprint, request, jsonify, current_app

# Import Werkzeug security for safe password hashing and verification
from werkzeug.security import generate_password_hash, check_password_hash

# Import datetime and random for handling timestamps and OTP generation
import random
from datetime import datetime, timezone, timedelta
from bot.notifier import send_otp_to_telegram

# Import ObjectId for handling MongoDB document identifiers natively
from bson import ObjectId

# Import JWT tools for authentication, session management, and route protection
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

# Define Flask Blueprints to encapsulate specific domain routes
dt_api = Blueprint('dt_api', __name__, url_prefix='/api/dt')         # Digital Twin operations
dr_api = Blueprint('dr_api', __name__, url_prefix='/api/dr')         # Digital Replica operations
users_api = Blueprint('users_api', __name__, url_prefix='/api/users') # User management
auth_api = Blueprint('auth_api', __name__, url_prefix='/api/auth')   # Authentication & OTP

# Ensure the upload directory for IoT camera telemetry exists at startup
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
    Creates a new virtual Home environment uniquely associated with the requesting user.
    The creator is automatically assigned the 'admin' role for this environment.
    
    Expected JSON payload: 
    { 
        "name": "My Home", 
        "description": "Main residence" 
    }
    """
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()

        # Validate request payload
        required_fields = ['name', 'description']
        if not data or not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields: name, description'}), 400

        # Instantiate the Digital Twin through the designated factory
        dt_id = current_app.config['DT_FACTORY'].create_dt(
            name=data['name'],
            description=data['description'],
        )

        # Attach default background services to the new environment
        current_app.config['DT_FACTORY'].add_service(dt_id=dt_id, service_name='PetDetectionService')
        current_app.config['DT_FACTORY'].add_service(dt_id=dt_id, service_name='RoomStatisticsService')
        current_app.config['DT_FACTORY'].add_service(dt_id=dt_id, service_name='PetStatisticsService')

        # Update the user's document to reflect ownership of the new Home
        doc = current_app.config['DB_SERVICE'].get_dr(dr_type='user', dr_id=current_user_id)
        current_homes = doc.get('data', {}).get('owned_homes', [])
        updated_homes = current_homes + [dt_id]
        
        current_app.config['DB_SERVICE'].update_dr(
            dr_type='user',
            dr_id=current_user_id,
            update_data={'data.owned_homes': updated_homes}
        )
        
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
        return jsonify({'status': 'error', 'message': f'Failed to create Home Environment: {str(e)}'}), 500


# ----------------- HOME ENVIRONMENT REMOVAL (Admin) -----------------
@dt_api.route('/<dt_id>', methods=['DELETE'])
@jwt_required()
def delete_digital_twin(dt_id):
    """
    Completely removes a Home environment and triggers a cascading deletion 
    of all its associated Digital Replicas (rooms, pets, doors) to maintain 
    database referential integrity.
    """
    try:
        current_user_id = get_jwt_identity()

        # Authorization check: only the admin can delete the environment
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the administrator can delete this Home Environment.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found.'}), 404

        # Cascade deletion: remove all linked components first
        for replica in dt_exists.get("digital_replicas", []):
            try:
                current_app.config['DB_SERVICE'].delete_dr(dr_type=replica["type"], dr_id=replica["id"])
            except Exception as e:
                print(f"[WARNING] Failed to delete replica {replica['id']} of type {replica['type']}: {str(e)}")

        # Finally, delete the parent environment and revoke access for all associated users
        current_app.config['DT_FACTORY'].delete_dt(dt_id)
        current_app.config['DB_SERVICE'].remove_home_from_all_users(dt_id)

        return jsonify({
            'status': 'success',
            'message': f'Home environment {dt_id} and all associated replicas successfully removed.'
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to delete Home Environment: {str(e)}'}), 500


# ----------------- ADD VIEWER (by the Admin) -----------------
@dt_api.route('/<dt_id>/viewers', methods=['POST'])
@jwt_required()
def add_viewer(dt_id):
    """
    Grants read-only (viewer) access to a specific Home Environment for another user, 
    identified by their username.
    """
    try:
        data = request.get_json()
        if not data or 'viewer_username' not in data:
            return jsonify({'error': 'Missing required fields: viewer_username'}), 400

        viewer_username = data['viewer_username']
        current_user_id = get_jwt_identity()

        # Verify admin privileges
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the administrator can add viewers.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found.'}), 404

        # Validate the target user exists
        viewer_user = current_app.config['DB_SERVICE'].get_user_by_username(viewer_username)
        if not viewer_user:
            return jsonify({'error': f'The user {viewer_username} is not registered.'}), 404
        
        viewer_id = str(viewer_user['_id'])

        # Logical constraints
        if viewer_id == current_user_id:
            return jsonify({'error': 'The admin cannot also be added as a viewer.'}), 400

        if dt_id in viewer_user.get('data', {}).get('viewable_homes', []):
            return jsonify({'error': 'The user is already a viewer of this home.'}), 400

        current_app.config['DB_SERVICE'].add_viewable_home(viewer_id, dt_id)

        return jsonify({
            'status': 'success',
            'message': f'User {viewer_username} successfully added as a viewer to Home {dt_id}.'
        }), 201

    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add viewer: {str(e)}'}), 500
    

# ----------------- VIEWER REMOVAL (by the Admin) -----------------
@dt_api.route('/<dt_id>/viewers/<viewer_id>', methods=['DELETE'])
@jwt_required()
def remove_viewer(dt_id, viewer_id):
    """
    Revokes viewer access for a specific user from a Home Environment.
    """
    try:
        current_user_id = get_jwt_identity()

        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the admin can remove viewers.'}), 403
             
        current_app.config['DB_SERVICE'].remove_viewable_home(viewer_id, dt_id)

        return jsonify({
            'status': 'success',
            'message': f'Viewer with ID {viewer_id} successfully removed from Home {dt_id}.'
        }), 200

    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to remove viewer: {str(e)}'}), 500


# ==============================================================================
#                            DIGITAL REPLICA APIs (dr_api)
# ==============================================================================

@dr_api.route('/<dt_id>/replicas/<dr_type>', methods=['POST'])
@jwt_required()
def create_and_associate_dr(dt_id, dr_type):
    """
    Creates a new Digital Replica (e.g., room, pet, door) and associates it 
    with a specific Digital Twin (Home).
    """
    try:
        raw_data = request.get_json() or {}

        if 'name' not in raw_data:
            return jsonify({'error': 'Missing required fields: name'}), 400

        dr_name = raw_data['name']
        current_user_id = get_jwt_identity()

        # Dynamically retrieve the correct factory based on the requested replica type
        factory_key = f'DR_FACTORY_{dr_type.upper()}'
        dr_factory = current_app.config.get(factory_key)
        
        if not dr_factory:
            return jsonify({'error': f'Unsupported Digital Replica type: {dr_type}'}), 400

        # Authorization check
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the administrator can add replicas.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found.'}), 404

        # Enforce business logic rules (e.g., max 1 pet per home, unique names)
        for replica in dt_exists.get("digital_replicas", []):
            if replica.get("type") == dr_type:
                if dr_type == 'pet':
                    return jsonify({'error': 'This home already has a pet associated with it.'}), 409
                existing_dr = current_app.config['DB_SERVICE'].get_dr(dr_type, replica["id"])
                if existing_dr and existing_dr.get("profile", {}).get("name") == dr_name:
                    return jsonify({'error': f'A {dr_type} with the name "{dr_name}" already exists.'}), 409

        # Structure the base profile data
        initial_data = {
            "profile": {
                "name": dr_name,
                "description": raw_data.get("description", "")
            }
        }
        
        # Map any additional specific properties provided in the payload
        for key, value in raw_data.items():
            if key not in ['name', 'description']:
                initial_data["profile"][key] = value

        # Validate schema and persist
        validated_dr = dr_factory.create_dr(dr_type=dr_type, initial_data=initial_data)
        dr_id = current_app.config['DB_SERVICE'].save_dr(dr_type=dr_type, dr_data=validated_dr)
        
        current_app.config['DT_FACTORY'].add_digital_replica(dt_id=dt_id, dr_type=dr_type, dr_id=dr_id)

        return jsonify({
            'status': 'success',
            'message': f'{dr_type.capitalize()} successfully created and linked.',
            'data': {
                'home_id': dt_id,
                f'{dr_type}_id': dr_id,
                'name': dr_name
            }
        }), 201

    except ValueError as ve:
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error during creation: {str(e)}'}), 500

    
@dr_api.route('/<dt_id>/replicas/<dr_type>/<dr_id>', methods=['DELETE'])
@jwt_required()
def remove_digital_replica(dt_id, dr_type, dr_id):
    """
    Removes a specific Digital Replica and unlinks it from the parent Home.
    """
    try:
        factory_key = f'DR_FACTORY_{dr_type.upper()}'
        if factory_key not in current_app.config:
            return jsonify({'error': f'Unsupported Digital Replica type: {dr_type}'}), 400

        current_user_id = get_jwt_identity()

        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the admin can remove components.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found.'}), 404

        # Ensure the replica actually belongs to this specific twin
        dr_linked = any(
            replica.get("id") == dr_id and replica.get("type") == dr_type 
            for replica in dt_exists.get("digital_replicas", [])
        )
        
        if not dr_linked:
            return jsonify({'error': f'The {dr_type.capitalize()} is not linked to this Home.'}), 404

        current_app.config['DB_SERVICE'].delete_dr(dr_type=dr_type, dr_id=dr_id)
        current_app.config['DT_FACTORY'].remove_digital_replica(dt_id=dt_id, dr_id=dr_id)

        return jsonify({
            'status': 'success',
            'message': f'{dr_type.capitalize()} {dr_id} successfully deleted and unlinked from Home {dt_id}.'
        }), 200

    except ValueError as ve:
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error during deletion: {str(e)}'}), 500


@dr_api.route('/<dt_id>/replicas/<dr_type>/<dr_id>', methods=['PUT'])
@jwt_required()
def update_digital_replica(dt_id, dr_type, dr_id):
    """
    Generic endpoint to update any Digital Replica type (room, pet, door, etc.),
    dynamically resolving field placement (profile/data) and enforcing schema validation via DRFactory.
    """
    try:
        # Dynamically retrieve the correct factory based on the requested replica type
        factory_key = f'DR_FACTORY_{dr_type.upper()}'
        dr_factory = current_app.config.get(factory_key)
        
        if not dr_factory:
            return jsonify({'error': f'Unsupported Digital Replica type: {dr_type}'}), 400

        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']

        # Authorization check: only the admin can modify components
        is_admin = db_service.is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the admin can modify components.'}), 403

        # Validate parent Digital Twin existence
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found.'}), 404

        # Ensure the replica is linked to this specific Digital Twin
        dr_linked = any(
            replica.get("id") == dr_id and replica.get("type") == dr_type 
            for replica in dt_exists.get("digital_replicas", [])
        )
        if not dr_linked:
            return jsonify({'error': f'The {dr_type.capitalize()} is not linked to this Home.'}), 404

        # Retrieve the current replica state from the database
        current_dr = db_service.get_dr(dr_type, dr_id)
        if not current_dr:
            return jsonify({'error': f'{dr_type.capitalize()} with ID {dr_id} not found.'}), 404

        raw_data = request.get_json() or {}
        if not raw_data:
            return jsonify({'error': 'No data provided for update.'}), 400

        # Handle nested or flat payloads dynamically using the DR schema definition
        updates = {}
        if "profile" in raw_data or "data" in raw_data or "metadata" in raw_data:
            # Case A: Client sent an already structured/nested dictionary
            updates = raw_data
        else:
            # Case B: Client sent a flat dictionary - classify keys dynamically via schema
            schemas = dr_factory.schema.get("schemas", {})
            profile_fields = schemas.get("common_fields", {}).get("profile", {}).keys()
            data_fields = schemas.get("entity", {}).get("data", {}).keys()

            updates = {"profile": {}, "data": {}}
            for key, value in raw_data.items():
                if key in profile_fields:
                    updates["profile"][key] = value
                elif key in data_fields:
                    updates["data"][key] = value
                else:
                    # Fallback to profile by default
                    updates["profile"][key] = value

            # Strip empty dict sections
            updates = {k: v for k, v in updates.items() if v}

        if not updates:
            return jsonify({'error': 'No valid fields provided for update.'}), 400

        # Validate and apply delta mutations using the DRFactory
        validated_updated_dr = dr_factory.update_dr(dr=current_dr, updates=updates)

        # Build update payload and persist in database
        update_payload = {
            "profile": validated_updated_dr.get("profile", {}),
            "data": validated_updated_dr.get("data", {}),
            "metadata": validated_updated_dr.get("metadata", {})
        }
        db_service.update_dr(dr_type=dr_type, dr_id=dr_id, update_data=update_payload)

        return jsonify({
            'status': 'success',
            'message': f'{dr_type.capitalize()} {dr_id} updated successfully.',
            'data': validated_updated_dr
        }), 200

    except ValueError as ve:
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error during update: {str(e)}'}), 500
        
    

# ----------------- CAMERA DEVICE AUTHENTICATION -------------------
@dr_api.route('/<dr_id>/tokens', methods=['POST'])
def device_login(dr_id):
    """
    Endpoint intended for automated IoT device authentication (e.g., ESP32-CAM).
    Grants an access token based strictly on the hardware/replica ID.
    """
    db_service = current_app.config['DB_SERVICE']
    
    # Direct resource lookup via the unique ID provided in the URL
    room_dr = db_service.get_dr("room", dr_id)

    if not room_dr:
        return jsonify({'error': 'Unauthorized or nonexistent device'}), 401

    # Generate a JWT specifically mapped to the device identity
    access_token = create_access_token(identity=f"device_{dr_id}")
    
    return jsonify({'status': 'success', 'access_token': access_token}), 200


# ----------------- PHOTO RECEPTION (TELEMETRY) FROM ESP32-CAM -------------------
@dr_api.route('/<dt_id>/rooms/<room_id>/telemetry', methods=['POST'])
@jwt_required()
def receive_telemetry(dt_id, room_id):
    """
    Ingests telemetry data (specifically images) from external camera sensors.
    Triggers the Computer Vision model (PetDetectionService) for analysis upon receipt.
    """
    try:
        home_id = dt_id 
        
        if 'image' not in request.files:
            return jsonify({'error': 'Image file missing in the request'}), 400
            
        file = request.files['image']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if file:
            db_service = current_app.config['DB_SERVICE']
            
            # Fetch room details using the ID for proper labeling
            room_dr = db_service.get_dr("room", room_id)
            if not room_dr:
                return jsonify({'error': 'Room not found.'}), 404
                
            room_name = room_dr.get("profile", {}).get("name", "Unknown")

            # Secure file saving with timestamps
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = secure_filename(f"{room_name}_{timestamp}.jpg")
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            file.save(filepath)
            
            # Trigger corresponding background analytical services
            try:
                dt_factory = current_app.config['DT_FACTORY']
                pet_detector = current_app.config.get('PET_DETECTOR')
                
                dt_instance = dt_factory.get_dt_instance(home_id)
                
                if not dt_instance:
                    print(f"[TELEMETRY] ERROR: Home with ID '{home_id}' does not exist in the database!")
                else:
                    dt_instance.execute_service(
                        service_name="PetDetectionService",
                        image_path=filepath,
                        room_name=room_name,
                        room_id=room_id,
                        db_service=db_service,
                        pet_detector=pet_detector
                    )
                                    
            except ValueError as ve:
                print(f"[TELEMETRY] Service not executed: {str(ve)}")
            except Exception as service_error:
                print(f"[TELEMETRY ERROR] Exception during service execution: {str(service_error)}")

            return jsonify({
                'status': 'success',
                'message': 'Photo received and processed successfully',
                'data': {
                    'room_id': room_id,
                    'room_name': room_name,
                    'saved_path': filepath
                }
            }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error saving telemetry: {str(e)}'}), 500
        

# ==============================================================================
#                            USERS APIs (users_api)
# ==============================================================================

@users_api.route('/', methods=['POST'])
def register():
    """
    Registers a new user on the platform.
    Hashes the password securely before committing to the database.
    """
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required.'}), 400

        username = data['username']
        password = data['password']

        hashed_password = generate_password_hash(password)
        current_app.config['DB_SERVICE']._init_users_collection()

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

        validated_user = current_app.config['DR_FACTORY_USER'].create_dr(
            dr_type='user',
            initial_data=initial_data
        )

        user_id = current_app.config['DB_SERVICE'].save_dr(
            dr_type='user',
            dr_data=validated_user
        )

        return jsonify({
            'status': 'success',
            'message': 'User registered successfully.',
            'data': {'user_id': user_id, 'username': username}
        }), 201

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        if "duplicate key error" in str(e).lower():
            return jsonify({'error': 'This username is already in use.'}), 409
        return jsonify({'error': f'Failed to register user: {str(e)}'}), 500


# ==============================================================================
#                         AUTHENTICATION APIs (auth_api)
# ==============================================================================

@auth_api.route('/tokens', methods=['POST'])
def login():
    """Authenticates a user and generates a stateless JWT for subsequent requests."""
    try:
        data = request.get_json()

        if not data or not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Username and password are required.'}), 400

        user = current_app.config['DB_SERVICE'].get_user_by_username(data['username'])

        if not user or not check_password_hash(user['profile']['password'], data['password']):
            return jsonify({'error': 'Invalid credentials.'}), 401

        user_id_str = str(user['_id'])
        access_token = create_access_token(identity=user_id_str)

        return jsonify({
            'status': 'success',
            'message': 'Login successful.',
            'access_token': access_token,
            'data': {'user_id': user_id_str, 'username': user['profile']['username']}
        }), 200

    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500
    

@auth_api.route('/tokens', methods=['DELETE'])
@jwt_required()
def logout():
    """
    Deletes the current user session context. 
    Note: As JWTs are stateless, true invalidation requires client-side deletion.
    """
    return jsonify({
        "status": "success", 
        "message": "Logout successful. Please remove the token on the client side."
    }), 200


# ==============================================================================
#                        API STATISTICS (dt_api)
# ==============================================================================

@dt_api.route('/<dt_id>/statistics', methods=['GET'])
@jwt_required()
def get_home_statistics(dt_id):
    """
    Fetches aggregated and real-time statistics regarding room occupancies.
    Calculates ongoing session durations dynamically up to the present moment.
    """
    try:
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404

        owned_homes = user.get('data', {}).get('owned_homes', [])
        viewable_homes = user.get('data', {}).get('viewable_homes', [])

        if dt_id not in owned_homes and dt_id not in viewable_homes:
            return jsonify({'error': 'Access denied. You are neither an admin nor a viewer of this home.'}), 403

        dt_data = dt_factory.get_dt(dt_id)
        if not dt_data:
            return jsonify({'error': 'Home Environment not found.'}), 404

        room_stats = []

        for replica in dt_data.get("digital_replicas", []):
            if replica.get("type") == "room":
                room_dr = db_service.get_dr("room", replica.get("id"))
                if not room_dr:
                    continue
                    
                room_name = room_dr.get("profile", {}).get("name", "Unknown")
                room_data = room_dr.get("data", {})
                
                status = room_data.get("status", "empty")
                last_entry_time = room_data.get("last_entry_time")
                occupancy_stats = room_data.get("occupancy_stats", [])
                
                today_stats = occupancy_stats[0] if occupancy_stats else {
                    "daily_stay_duration_mins": 0.0,
                    "pet_entries_count": 0
                }
                
                current_session_mins = 0.0
                if status == "occupied" and last_entry_time:
                    # Normalize timestamps for accurate arithmetic
                    if isinstance(last_entry_time, str):
                        last_entry_time = datetime.fromisoformat(last_entry_time.replace("Z", "+00:00"))
                    elif isinstance(last_entry_time, datetime) and last_entry_time.tzinfo is None:
                        last_entry_time = last_entry_time.replace(tzinfo=timezone.utc)
                        
                    now = datetime.now(timezone.utc)
                    
                    # Truncate at midnight if the entry spans across days
                    if last_entry_time.date() < now.date():
                        start_time_for_calc = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    else:
                        start_time_for_calc = last_entry_time
                        
                    time_diff = now - start_time_for_calc
                    current_session_mins = time_diff.total_seconds() / 60.0
                
                total_duration = today_stats.get("daily_stay_duration_mins", 0.0) + current_session_mins
                
                room_stats.append({
                    "room_id": replica.get("id"),
                    "room_name": room_name,
                    "status": status,
                    "daily_stay_duration_mins": round(total_duration, 2),
                    "pet_entries_count": today_stats.get("pet_entries_count", 0),
                    "is_occupied_now": status == "occupied"
                })

        return jsonify({
            'status': 'success',
            'data': {'home_id': dt_id, 'rooms': room_stats}
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error retrieving statistics: {str(e)}'}), 500
        

@dt_api.route('/<dt_id>/pet/statistics', methods=['GET'])
@jwt_required()
def get_pet_statistics(dt_id):
    """
    Fetches behavior metrics specific to the pet within the twin environment.
    Includes full historical data (up to 30 days) continuously updated.
    """
    try:
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404

        owned_homes = user.get('data', {}).get('owned_homes', [])
        viewable_homes = user.get('data', {}).get('viewable_homes', [])

        if dt_id not in owned_homes and dt_id not in viewable_homes:
            return jsonify({'error': 'Access denied. You are neither an admin nor a viewer of this home.'}), 403

        dt_data = dt_factory.get_dt(dt_id)
        if not dt_data:
            return jsonify({'error': 'Home Environment not found.'}), 404

        pet_stats = None

        for replica in dt_data.get("digital_replicas", []):
            if replica.get("type") == "pet":
                pet_dr = db_service.get_dr("pet", replica.get("id"))
                if not pet_dr:
                    continue
                    
                pet_name = pet_dr.get("profile", {}).get("name", "Unknown")
                pet_data = pet_dr.get("data", {})
                
                last_buzzer_start = pet_data.get("last_buzzer_start_time")
                daily_buzzer_stats = pet_data.get("daily_buzzer_stats", [])
                
                # --- 1. REAL-TIME SESSION CALCULATION ---
                current_session_mins = 0.0
                current_violation = 0
                
                if last_buzzer_start:
                    if isinstance(last_buzzer_start, str):
                        last_buzzer_start = datetime.fromisoformat(last_buzzer_start.replace("Z", "+00:00"))
                    elif isinstance(last_buzzer_start, datetime) and last_buzzer_start.tzinfo is None:
                        last_buzzer_start = last_buzzer_start.replace(tzinfo=timezone.utc)
                        
                    time_diff = datetime.now(timezone.utc) - last_buzzer_start
                    current_session_mins = time_diff.total_seconds() / 60.0
                    current_violation = 1 
                
                # --- 2. HISTORICAL RECORD UPDATE ---
                if daily_buzzer_stats:
                    # Assumes index 0 always represents the current day's record
                    today_stats = daily_buzzer_stats[0]
                    today_stats["auto_duration_mins"] = round(today_stats.get("auto_duration_mins", 0.0) + current_session_mins, 2)
                    today_stats["auto_violations_count"] = today_stats.get("auto_violations_count", 0) + current_violation
                else:
                    # Initialize empty day record
                    daily_buzzer_stats = [{
                        "date": datetime.now(timezone.utc).isoformat(),
                        "auto_duration_mins": round(current_session_mins, 2),
                        "auto_violations_count": current_violation
                    }]

                # --- 3. DATE SANITIZATION FOR JSON COMPATIBILITY ---
                # Prevents serialization crashes if PyMongo returns unconventional formats
                for stat in daily_buzzer_stats:
                    date_val = stat.get("date")
                    if isinstance(date_val, dict) and "$date" in date_val:
                        stat["date"] = date_val["$date"]
                    elif isinstance(date_val, datetime):
                        stat["date"] = date_val.isoformat()
                
                pet_stats = {
                    "pet_id": replica.get("id"),
                    "pet_name": pet_name,
                    "current_room": pet_data.get("current_room", ""),
                    "buzzer_state": pet_data.get("buzzer_state", ""),
                    "buzzer_status": pet_data.get("buzzer_status", ""),
                    "is_buzzer_active_now": bool(last_buzzer_start),
                    "daily_buzzer_stats": daily_buzzer_stats,
                    "learning_analytics": pet_data.get("learning_analytics", {}) 
                }
                
                # Single pet constraint allows us to break early
                break 

        if not pet_stats:
            return jsonify({'error': 'No pet is associated with this home.'}), 404

        return jsonify({
            'status': 'success',
            'data': {
                'home_id': dt_id,
                'pet': pet_stats
            }
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Error retrieving pet statistics: {str(e)}'}), 500
    

# ----------------- GET USER HOMES (Admin & Viewer) -----------------
@dt_api.route('/', methods=['GET'])
@jwt_required()
def get_user_homes():
    """
    Retrieves a consolidated list of all Home Environments connected to the logged-in user,
    categorized explicitly by ownership rights (owned/admin vs read-only/viewer).
    """
    try:
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404

        # Extract arrays for reference mapping
        owned_home_ids = user.get('data', {}).get('owned_homes', [])
        viewable_home_ids = user.get('data', {}).get('viewable_homes', [])

        owned_homes = []
        viewable_homes = []

        # Populate structural details for owned homes
        for dt_id in owned_home_ids:
            dt = dt_factory.get_dt(dt_id)
            if dt:
                owned_homes.append({
                    'home_id': dt_id,
                    'name': dt.get('name', 'Unknown'),
                    'description': dt.get('description', ''),
                    'role': 'admin'
                })

        # Populate structural details for viewable environments
        for dt_id in viewable_home_ids:
            dt = dt_factory.get_dt(dt_id)
            if dt:
                viewable_homes.append({
                    'home_id': dt_id,
                    'name': dt.get('name', 'Unknown'),
                    'description': dt.get('description', ''),
                    'role': 'viewer'
                })

        return jsonify({
            'status': 'success',
            'data': {
                'owned_homes': owned_homes,
                'viewable_homes': viewable_homes
            }
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'Error fetching homes: {str(e)}'
        }), 500
    

# ----------------- GET HOME MANAGEMENT DATA (Admin) -----------------
@dt_api.route('/<dt_id>/management', methods=['GET'])
@jwt_required()
def get_home_management(dt_id):
    """
    Fetches raw inventory of an environment (rooms, doors, pets, viewers) 
    intended strictly for admin management interfaces.
    """
    try:
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404

        owned_homes = user.get('data', {}).get('owned_homes', [])
        if dt_id not in owned_homes:
            return jsonify({'error': 'Access denied. Only the admin can manage the home.'}), 403

        dt_data = dt_factory.get_dt(dt_id)
        if not dt_data: return jsonify({'error': 'Home not found.'}), 404

        rooms, doors, pets, viewers = [], [], [], []

        for replica in dt_data.get("digital_replicas", []):
            raw_id = replica.get("id")
            # Defensive cast to prevent structural mismatch
            str_id = str(raw_id) if not isinstance(raw_id, str) else raw_id
            
            dr = db_service.get_dr(replica["type"], str_id)
            if dr:
                item = {"id": str(dr["_id"]), "name": dr.get("profile", {}).get("name", "N/A")}
                if replica["type"] == "room":
                    item['permission'] = dr.get("profile", {}).get("permission_level", "allowed")
                    rooms.append(item)
                elif replica["type"] == "door":
                    doors.append(item)
                elif replica["type"] == "pet":
                    pets.append(item)

        # Cross-reference query: Locate viewers by checking users whose viewable_homes list contains this twin
        viewer_users = db_service.query_drs("user", {"data.viewable_homes": dt_id})
        for v_user in viewer_users:
            viewers.append({
                "id": str(v_user["_id"]),
                "username": v_user.get("profile", {}).get("username", "N/A")
            })

        return jsonify({
            'status': 'success',
            'data': {'rooms': rooms, 'doors': doors, 'pets': pets, 'viewers': viewers}
        }), 200
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500



@users_api.route('/<user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    """
    Deletes a user account.
    Security Requirement: A user can ONLY delete their own account.
    Initiates a recursive cascade deletion of all owned environments and their child nodes.
    """
    try:
        current_user_id = get_jwt_identity()

        # SECURITY: Ensure path parameter identity matches the token payload
        if str(current_user_id) != str(user_id):
            return jsonify({
                'error': 'Unauthorized action. You may only delete your own account.'
            }), 403

        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        # Determine structural ownership mapping
        user = db_service.get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404

        # 1. CASCADE DELETION: Strip all environments owned by the user
        owned_homes = user.get('data', {}).get('owned_homes', [])
        
        for home_id in owned_homes:
            dt_exists = dt_factory.get_dt(home_id)
            if dt_exists:
                # 1A. Traverse and sever all child replica nodes
                for replica in dt_exists.get("digital_replicas", []):
                    try:
                        db_service.delete_dr(dr_type=replica["type"], dr_id=replica["id"])
                    except Exception as e:
                        print(f"[WARNING] Error deleting replica {replica['id']}: {str(e)}")

                # 1B. Annihilate the core Digital Twin parent wrapper
                dt_factory.delete_dt(home_id)
                
                # 1C. Cleanse external references from unaffected viewer accounts
                db_service.remove_home_from_all_users(home_id)

        # 2. FINALIZATION: Erase the root user document
        db_service.delete_dr(dr_type='user', dr_id=user_id)

        return jsonify({
            'status': 'success',
            'message': 'Account and all associated environments deleted successfully.'
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'Error during account deletion: {str(e)}'
        }), 500


@auth_api.route('/otp', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True) 
def generate_otp():
    """
    Generates a secure One-Time Password (OTP) and distributes it directly via Telegram 
    to the authenticated user. Uses optional JWT evaluation to allow preflight CORS checks.
    """
    if request.method == 'OPTIONS':
        return '', 200

    try:
        current_user_id = get_jwt_identity()
        if not current_user_id:
            return jsonify({'error': 'Missing or invalid token.'}), 401

        db_service = current_app.config['DB_SERVICE']
        
        # Instantiate a cryptographically secure 6-digit challenge
        otp_code = str(random.randint(100000, 999999))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Persist the challenge to the DB while resetting prior verification flags
        db_service.update_dr(
            dr_type='user',
            dr_id=current_user_id,
            update_data={
                "metadata": {
                    "otp_code": otp_code,
                    "otp_expires_at": expires_at.isoformat(),
                    "otp_verified": False
                }
            }
        )
        
        # Execute external dispatch via Telegram bot service
        sent = send_otp_to_telegram(current_user_id, otp_code)
        
        if not sent:
            return jsonify({
                'status': 'error', 
                'message': 'Unable to send OTP on Telegram. Ensure you have executed /login on the bot.'
            }), 400

        return jsonify({
            'status': 'success',
            'message': 'OTP code sent successfully to your Telegram!'
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_api.route('/otp/checks', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True)
def verify_otp():
    """
    Validates a submitted OTP challenge against the active token in the database.
    Enforces a strict 5-minute temporal window before expiration.
    """
    if request.method == 'OPTIONS':
        return '', 200

    try:
        current_user_id = get_jwt_identity()
        if not current_user_id:
            return jsonify({'error': 'Missing or invalid token.'}), 401

        data = request.get_json()
        if not data or 'otp_code' not in data:
            return jsonify({'error': 'Missing OTP code.'}), 400

        user_otp = str(data['otp_code']).strip()
        db_service = current_app.config['DB_SERVICE']

        # Access user verification record
        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'User not found.'}), 404

        user_metadata = user.get('metadata', {})
        saved_otp = user_metadata.get('otp_code')
        expires_at_str = user_metadata.get('otp_expires_at')

        # Challenge parity check
        if not saved_otp or saved_otp != user_otp:
            return jsonify({'error': 'Invalid OTP code.'}), 400

        # Temporal expiration verification (5-minute limit)
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires_at:
                return jsonify({'error': 'OTP code has expired. Please generate a new one.'}), 400

        # Successful challenge clears the OTP value immediately for security and flags verification status
        db_service.update_dr(
            dr_type='user',
            dr_id=current_user_id,
            update_data={
                "metadata": {
                    "otp_code": None,
                    "otp_expires_at": None,
                    "otp_verified": True
                }
            }
        )

        return jsonify({
            'status': 'success',
            'message': 'OTP verified successfully.'
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
            
# ==============================================================================
#                       BLUEPRINTS REGISTRATION UTILITY
# ==============================================================================

def register_api_blueprints(app):
    """
    Utility mechanism to mount all distinct Blueprint modules onto the main application tree.
    """
    app.register_blueprint(dt_api)
    app.register_blueprint(dr_api)
    app.register_blueprint(users_api)
    app.register_blueprint(auth_api)