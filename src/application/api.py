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

# ---------------- Route to create a new Digital Twin instance using HTTP POST -------------
@dt_api.route('/', methods=['POST'])
def create_digital_twin():
    """Create a new Digital Twin"""
    try:
        # Extract JSON data from the incoming request payload
        data = request.get_json()

        # Define the list of fields required to create a Digital Twin
        required_fields = ['name', 'description']

        # Check if all required fields are present in the parsed JSON data
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields'}), 400

        # Invoke the Digital Twin Factory from current_app config to create the twin
        dt_id = current_app.config['DT_FACTORY'].create_dt(
            name=data['name'],
            description=data['description']
        )
        # Return the generated Digital Twin ID with a 201 Created status code
        return jsonify({'dt_id': dt_id}), 201
    except Exception as e:
        # Catch any unexpected exceptions and return a 500 Internal Server Error
        return jsonify({'error': str(e)}), 500

# ------------- Route to fetch a specific Digital Twin's details by its ID using HTTP GET -------------
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

# --------------- Route to retrieve a list of all existing Digital Twins using HTTP GET --------------
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

