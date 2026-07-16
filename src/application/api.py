# ==============================================================================
#                 MODULE IMPORTS & FLASK BLUEPRINTS SETUP
# ==============================================================================

# Import Flask dependencies for routing, requests, JSON responses, and application context
from flask import Blueprint, request, jsonify, current_app

# Import datetime for handling timestamps
from datetime import datetime

# Import ObjectId for handling MongoDB document identifiers
from bson import ObjectId

# Create a blueprint for Digital Twin (DT) specific APIs with a base URL prefix
dt_api = Blueprint('dt_api', __name__, url_prefix='/api/dt')

# Create a blueprint for Digital Replica (DR) specific APIs with a base URL prefix
dr_api = Blueprint('dr_api', __name__, url_prefix='/api/dr')

# Create a blueprint for Digital Twin management and orchestration APIs with a base URL prefix
dt_management_api = Blueprint('dt_management_api', __name__, url_prefix='/api/dt-management')


# ==============================================================================
#                            DIGITAL TWIN APIs
# ==============================================================================

# ----------------- HOME ENVIRONMENT CREATION (Main User / Admin) --------------
@dt_api.route('/', methods=['POST'])
def create_digital_twin():
    """
    Create a new virtual Home environment uniquely associated with an Admin.
    """
    try:
        # Retrieve the sent payload
        data = request.get_json()

        # Validation of mandatory fields for the Pet Tracker
        required_fields = ['name', 'description', 'user_id']
        if not data or not all(field in data for field in required_fields):
            return jsonify({
                'error': 'Missing required fields. Torna su Postman e controlla di aver inserito: name, description, user_id'
            }), 400

        # 1. Call the DTFactory
        # This will generate the unique _id using ObjectId() and save the twin to MongoDB
        dt_id = current_app.config['DT_FACTORY'].create_dt(
            name=data['name'],
            description=data['description']
        )

        # 2. Record the unique relationship between this specific home and the Admin user ('set_home_admin' defined in src/services/database_service.py)
        current_app.config['DB_SERVICE'].set_home_admin(dt_id, data['user_id'])

        # Successful response with the generated UNIQUE ID
        return jsonify({
            'status': 'success',
            'message': 'Home environment created successfully',
            'data': {
                'home_id': dt_id,
                'home_name': data['name'],
                'admin_user_id': data['user_id'],
                'role_assigned': 'admin'
            }
        }), 201

    except Exception as e:
        # For example, if you try to enter a duplicate name, MongoDB's unique index will throw an error here
        return jsonify({
            'status': 'error',
            'message': f'Failed to create Home Environment: {str(e)}'
        }), 500


# ----------------- HOME ENVIRONMENT REMOVAL (Admin) -----------------
@dt_api.route('/<string:dt_id>', methods=['DELETE'])
def delete_digital_twin(dt_id):
    """
    Completely removes a Home environment and its associated permissions.
    """
    try:
        # 1. We eliminate the Digital Twin via the Factory. ('delete_dt' defined in src/digital_twin/dt_factory.py)
        current_app.config['DT_FACTORY'].delete_dt(dt_id)

        # 2. Let's clean up the database by removing the permissions associated with that house ('remove_home_permissions' defined in src/services/database_service.py).
        #    home_permissions is a collection inside the MONGOdb dataset
        current_app.config['DB_SERVICE'].remove_home_permissions(dt_id)

        return jsonify({
            'status': 'success',
            'message': f'Home environment {dt_id} and all its permissions successfully removed.'
        }), 200

    except ValueError as ve:
        # This triggers if you try to delete an ID that does not exist in the DB.
        return jsonify({
            'status': 'error',
            'message': str(ve)
        }), 404
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to delete Home Environment: {str(e)}'
        }), 500



# ------------- Route to fetch a specific Digital Twin's details by its ID using HTTP GET (Digital Twin -> Home Environment) -------------
@dt_api.route('/<dt_id>', methods=['GET'])
def get_digital_twin(dt_id):
    """Get Digital Twin details"""
    try:
        # Retrieve the Digital Twin metadata from the factory using the provided ID
        dt = current_app.config['DT_FACTORY'].get_dt(dt_id)

        # If the Digital Twin does not exist, return a 404 Not Found error
        if not dt:
            return jsonify({'error': 'Digital Twin not found'}), 404

        # Return the Digital Twin data with a 200 OK status code
        return jsonify(dt), 200
    except Exception as e:
        # Catch any unexpected exceptions and return a 500 Internal Server Error
        return jsonify({'error': str(e)}), 500



# --------------- Route to retrieve a list of all existing Digital Twins (Home Environments) using HTTP GET --------------
@dt_api.route('/', methods=['GET'])
def list_digital_twins():
    """List all Digital Twins"""
    try:
        # Call the factory to list all registered Digital Twins
        dts = current_app.config['DT_FACTORY'].list_dts()

        # Return the list of Digital Twins with a 200 OK status code
        return jsonify(dts), 200
    except Exception as e:
        # Catch any unexpected exceptions and return a 500 Internal Server Error
        return jsonify({'error': str(e)}), 500


# ---------------- Route to register a new service configuration to an existing Twin using HTTP POST
@dt_api.route('/<dt_id>/services', methods=['POST'])
def add_service_to_dt(dt_id):
    """Add a service to Digital Twin"""
    try:

        # Extract JSON data containing service details from the request
        data = request.get_json()

        # Ensure the request contains JSON data and includes the service name
        if not data or 'name' not in data:
            return jsonify({'error': 'Missing service name'}), 400

        # Register the service configuration on the target Digital Twin via the factory
        current_app.config['DT_FACTORY'].add_service(
            dt_id=dt_id,                              # Target Digital Twin ID
            service_name=data['name'],                # Class name of the service to add
            service_config=data.get('config', {})     # Pass configuration dictionary or empty dict if not provided
        )

        # Return success status with a descriptive message and a 200 OK response
        return jsonify({'status': 'success', 'message': f"Service {data['name']} added"}), 200
    except Exception as e:
        # Catch any unexpected exceptions and return a 500 Internal Server Error
        return jsonify({'error': str(e)}), 500

# ==============================================================================
#                          DIGITAL REPLICA APIs
# ==============================================================================

# -------------- Route to get specific Digital Replica details by type and ID using HTTP GET ----------------
@dr_api.route('/<dr_type>/<dr_id>', methods=['GET'])
def get_digital_replica(dr_type, dr_id):
    """Get Digital Replica details"""
    try:

        # Query the DB service directly to fetch the replica data
        dr = current_app.config['DB_SERVICE'].get_dr(dr_type, dr_id)

        # If the Digital Replica is not found, return a 404 Not Found error
        if not dr:
            return jsonify({'error': 'Digital Replica not found'}), 404

        # Return the Digital Replica document with a 200 OK status code
        return jsonify(dr), 200
    except Exception as e:
        # Catch any unexpected exceptions and return a 500 Internal Server Error
        return jsonify({'error': str(e)}), 500

# ==============================================================================
#                        DIGITAL TWIN MANAGEMENT APIs
# ==============================================================================

# --------------- Route to associate/assign a Digital Replica to a Digital Twin using HTTP POST -----------
@dt_management_api.route('/assign/<dt_id>', methods=['POST'])
def assign_dr_to_dt(dt_id):
    """Assign a Digital Replica to a Digital Twin"""
    try:

        # Extract JSON payload containing mapping details from the request
        data = request.get_json()

        # Define the required fields to perform the mapping assignment
        required_fields = ['dr_type', 'dr_id']

        # Verify that both replica type and replica ID are supplied
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        # Execute the assignment operation via the Digital Twin Factory
        current_app.config['DT_FACTORY'].add_digital_replica(
            dt_id,              # Target Digital Twin ID     
            data['dr_type'],    # Type of the Digital Replica to assign
            data['dr_id']       # Identifier of the Digital Replica to assign
        )

        # Return a success status indicator with a 200 OK response
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        # Catch any unexpected exceptions and return a 500 Internal Server Error
        return jsonify({'error': str(e)}), 500

# ------------- Route to fetch statistics and aggregate data from a Twin's services using HTTP GET ------------------
@dt_management_api.route('/stats/<dt_id>', methods=['GET'])
def get_dt_stats(dt_id):
    """Get statistics from a Digital Twin's services"""
    try:

        # Verify if the requested Digital Twin exists in the database
        dt = current_app.config['DT_FACTORY'].get_dt(dt_id)

        # If the Twin is not found, return a 404 Not Found error
        if not dt:
            return jsonify({'error': 'Digital Twin not found'}), 404

        params = request.args.to_dict()                      # Parse query string parameters from the request URL
        dr_type = params.get('dr_type')                      # Retrieve the optional replica type from the query parameters
        measure_type = params.get('measure_type')            # Retrieve the optional measurement attribute from the query parameters

        # Obtain the live in-memory instance of the Twin and execute the AggregationService
        stats = current_app.config['DT_FACTORY'].get_dt_instance(dt_id).execute_service(
            'AggregationService',              # Target service to run
            dr_type=dr_type,                   # Pass the filtered replica type
            attribute=measure_type             # Pass the target measure/attribute 
        )

        # Return the calculated statistics with a 200 OK response
        return jsonify(stats), 200
    except Exception as e:
        # Catch any unexpected exceptions and return a 500 Internal Server Error
        return jsonify({'error': str(e)}), 500


# ==============================================================================
#                       BLUEPRINTS REGISTRATION UTILITY
# ==============================================================================

# Utility function to register all blueprints to a Flask application instance
def register_api_blueprints(app):
    """Register all API blueprints with the Flask app"""

    # Register Digital Twin API routes
    app.register_blueprint(dt_api)

    # Register Digital Replica API routes
    app.register_blueprint(dr_api)

    # Register Digital Twin Management and Aggregation API routes
    app.register_blueprint(dt_management_api)

# ==================================================================================================
#--------------------------------------------- Nuove Robe -----------------------------------------
# ==================================================================================================

# ----------------- ADD VIEWER (by the Admin) -----------------
@dt_api.route('/<string:dt_id>/viewers', methods=['POST'])
def add_viewer(dt_id):
    """
    Adds a viewer user to a specific Home Environment.
    """
    try:
        data = request.get_json()

        # Input validation
        if not data or 'viewer_id' not in data:
            return jsonify({
                'error': 'Missing viewer_id in request body'
            }), 400

        viewer_id = data['viewer_id']

        # 1. Let's verify that the house exists before adding permissions at random.
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        # 2. Let's save the permission to the database.
        current_app.config['DB_SERVICE'].add_home_viewer(dt_id, viewer_id)

        return jsonify({
            'status': 'success',
            'message': f'User {viewer_id} successfully added as viewer to Home {dt_id}',
            'data': {
                'home_id': dt_id,
                'viewer_id': viewer_id,
                'role': 'viewer'
            }
        }), 201

    except ValueError as ve:
        # Catch the error if the user had already been added
        return jsonify({'status': 'error', 'message': str(ve)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add viewer: {str(e)}'}), 500


# ----------------- VIEWER REMOVAL (by the Admin) -----------------
@dt_api.route('/<string:dt_id>/viewers/<string:viewer_id>', methods=['DELETE'])
def remove_viewer(dt_id, viewer_id):
    """
    Removes a specific user's viewer access to a Home Environment.
    """
    try:
        # 1. First, let's verify that the house exists.
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        # 2. Remove the permission from the database
        current_app.config['DB_SERVICE'].remove_home_viewer(dt_id, viewer_id)

        return jsonify({
            'status': 'success',
            'message': f'User {viewer_id} successfully removed from viewers of Home {dt_id}'
        }), 200

    except ValueError as ve:
        return jsonify({'status': 'error', 'message': str(ve)}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to remove viewer: {str(e)}'}), 500


# ----------------- AGGIUNTA STANZA A UNA SPECIFICA HOME -------------------
@dt_api.route('/<string:dt_id>/rooms', methods=['POST'])
def create_and_associate_room(dt_id):
    """
    Crea una Digital Replica di tipo Room validando i campi con la DRFactory
    e la associa istantaneamente all'Home Environment.
    """
    try:
        raw_data = request.get_json()

        # 1. Verifichiamo subito se la casa (Digital Twin) esiste tramite la factory
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment with ID {dt_id} not found'}), 404

        # 2. Strutturiamo i dati flat di Postman per renderli compatibili con DRFactory
        initial_data = {
            "profile": {
                "name": raw_data.get("name"),
                "description": raw_data.get("description", ""),
                "floor": raw_data.get("floor"),
                # Inseriamo il permission_level nel profilo (default a "allowed" se non fornito)
                "permission_level": raw_data.get("permission_level", "allowed")
            },
            "data": {
                "esp32cam_device": raw_data.get("esp32cam_mac", ""),
                "ultrasonic_sensors": raw_data.get("ultrasonic_sensors", [])
            }
        }

        # Gestiamo opzionalmente il permission_level nei metadata se inviato
        if "permission_level" in raw_data:
            initial_data["metadata"] = {"permission_level": raw_data["permission_level"]}

        # 3. VALIDAZIONE PYDANTIC: deleghiamo la creazione e il controllo dello YAML alla DRFactory
        # Se un campo obbligatorio manca o è fuori range (es. floor > 2), Pydantic lancerà un ValueError.
        validated_room = current_app.config['DR_FACTORY_ROOM'].create_dr(
            dr_type='room',
            initial_data=initial_data
        )

        # 4. Salvataggio della replica validata nel database
        room_id = current_app.config['DB_SERVICE'].save_dr(
            dr_type='room',
            dr_data=validated_room
        )

        # 5. ASSOCIAZIONE NATURALE
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
        # Pydantic lancerà un ValueError se le regole in room.yaml non sono rispettate
        return jsonify({'error': f'Validation failed: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Failed to add room: {str(e)}'}), 500
