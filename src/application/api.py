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
            description=data['description'],
        )

        current_app.config['DT_FACTORY'].add_service(dt_id=dt_id, service_name='PetDetectionService')

        # 2. Update the user profile by adding the home to owned_homes
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

@dr_api.route('/<dr_type>', methods=['POST'])
@jwt_required()
def create_and_associate_dr(dr_type):
    """
    Crea una Digital Replica universale in base al dr_type fornito nell'URL 
    e la associa istantaneamente al Digital Twin (Home Environment).
    """
    try:
        raw_data = request.get_json() or {}

        # 1. Validazione di Base
        if 'dt_id' not in raw_data or 'name' not in raw_data:
            return jsonify({'error': 'Campi obbligatori mancanti: dt_id, name'}), 400

        dt_id = raw_data['dt_id']
        dr_name = raw_data['name']
        current_user_id = get_jwt_identity()

        # 2. Controllo Esistenza Factory Dinamica
        factory_key = f'DR_FACTORY_{dr_type.upper()}'
        dr_factory = current_app.config.get(factory_key)
        
        if not dr_factory:
            return jsonify({'error': f'Tipo di Digital Replica non supportato o configurazione mancante: {dr_type}'}), 400

        # 3. Controllo Autorizzazioni (Solo Admin)
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Non autorizzato. Solo l\'amministratore può aggiungere repliche.'}), 403

        # 4. Verifica Esistenza Digital Twin
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment con ID {dt_id} non trovato'}), 404

        # 5. Controllo Duplicati e Vincoli Specifici
        for replica in dt_exists.get("digital_replicas", []):
            if replica.get("type") == dr_type:
                
                # --- NUOVO VINCOLO: Massimo 1 Pet per Casa ---
                if dr_type == 'pet':
                    return jsonify({'error': 'Questa casa ha già un pet associato. È consentito un solo pet per Home Environment.'}), 409
                # ---------------------------------------------
                
                # Controllo nome duplicato (es. due "Cucina" o due "Porta Principale")
                existing_dr = current_app.config['DB_SERVICE'].get_dr(dr_type, replica["id"])
                if existing_dr and existing_dr.get("profile", {}).get("name") == dr_name:
                    return jsonify({'error': f'Un(a) {dr_type} con il nome "{dr_name}" esiste già in questa casa.'}), 409

        # 6. Costruzione Dinamica del Payload Iniziale
        initial_data = {
            "profile": {
                "name": dr_name,
                "description": raw_data.get("description", "")
            }
        }
        
        # Travaso dati dinamico per la validazione di Pydantic
        for key, value in raw_data.items():
            if key not in ['dt_id', 'name', 'description']:
                initial_data["profile"][key] = value

        # 7. Validazione Pydantic
        validated_dr = dr_factory.create_dr(
            dr_type=dr_type,
            initial_data=initial_data
        )

        # 8. Salvataggio nel Database
        dr_id = current_app.config['DB_SERVICE'].save_dr(
            dr_type=dr_type,
            dr_data=validated_dr
        )

        # 9. Associazione al Digital Twin
        current_app.config['DT_FACTORY'].add_digital_replica(
            dt_id=dt_id,
            dr_type=dr_type,
            dr_id=dr_id
        )

        return jsonify({
            'status': 'success',
            'message': f'{dr_type.capitalize()} validato(a), creato(a) e collegato(a) con successo.',
            'data': {
                'home_id': dt_id,
                f'{dr_type}_id': dr_id,
                'name': dr_name
            }
        }), 201

    except ValueError as ve:
        return jsonify({'error': f'Validazione fallita: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Errore durante la creazione di {dr_type}: {str(e)}'}), 500

    

@dr_api.route('/<dr_type>', methods=['DELETE'])
@jwt_required()
def remove_digital_replica(dr_type):
    """
    Rimuove una Digital Replica specifica dal Database e la scollega dall'Home Environment.
    Supporta dinamicamente tutti i tipi di DR registrati nel sistema.
    """
    try:
        # 1. Verifica dinamica se il tipo di DR è supportato
        factory_key = f'DR_FACTORY_{dr_type.upper()}'
        if factory_key not in current_app.config:
            return jsonify({'error': f'Tipo di Digital Replica non supportato: {dr_type}'}), 400

        raw_data = request.get_json() or {}

        # 2. Controllo campi base
        if 'dt_id' not in raw_data or 'dr_id' not in raw_data:
            return jsonify({'error': 'Campi obbligatori mancanti: dt_id, dr_id'}), 400

        dt_id = raw_data['dt_id']
        dr_id = raw_data['dr_id']
        current_user_id = get_jwt_identity()

        # 3. Controllo Autorizzazioni (Solo Admin)
        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Non autorizzato. Solo l\'admin può rimuovere i componenti.'}), 403

        # 4. Verifica esistenza Digital Twin
        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment con ID {dt_id} non trovato'}), 404

        # 5. Verifica che la replica appartenga effettivamente a questo Digital Twin
        dr_linked = any(
            replica.get("id") == dr_id and replica.get("type") == dr_type 
            for replica in dt_exists.get("digital_replicas", [])
        )
        
        if not dr_linked:
            return jsonify({'error': f'{dr_type.capitalize()} specificato non è collegato a questa Casa.'}), 404

        # 6. Rimozione dal Database
        current_app.config['DB_SERVICE'].delete_dr(
            dr_type=dr_type, 
            dr_id=dr_id
        )

        # 7. Disassociazione dal Digital Twin
        current_app.config['DT_FACTORY'].remove_digital_replica(
            dt_id=dt_id,
            dr_id=dr_id
        )

        return jsonify({
            'status': 'success',
            'message': f'{dr_type.capitalize()} {dr_id} eliminato(a) e scollegato(a) da Home {dt_id}.'
        }), 200

    except ValueError as ve:
        return jsonify({'error': f'Validazione fallita: {str(ve)}'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Errore durante l\'eliminazione: {str(e)}'}), 500        

# ----------------- CAMERA DEVICE AUTHENTICATION -------------------
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
            
            # --- NUOVA INTEGRAZIONE YOLO TRAMITE DIGITAL TWIN SERVICE ---
            try:
                dt_factory = current_app.config['DT_FACTORY']
                db_service = current_app.config['DB_SERVICE']
                pet_detector = current_app.config.get('PET_DETECTOR')
                
                # Recupera l'istanza del Digital Twin completamente inizializzata (DR + Servizi)
                dt_instance = dt_factory.get_dt_instance(home_id)
                
                if not dt_instance:
                    print(f"[TELEMETRY] ERRORE: La casa con ID '{home_id}' non esiste nel database!")
                else:
                    # Chiediamo al Digital Twin di eseguire il servizio di rilevamento
                    dt_instance.execute_service(
                        service_name="PetDetectionService",
                        image_path=filepath,
                        room_name=room_name,
                        db_service=db_service,
                        pet_detector=pet_detector
                    )
                                    
            except ValueError as ve:
                print(f"[TELEMETRY] Servizio non eseguito: {str(ve)}")
            except Exception as service_error:
                print(f"[TELEMETRY ERROR] Eccezione durante l'esecuzione del servizio: {str(service_error)}")
            # --------------------------------------------------

            return jsonify({
                'status': 'success',
                'message': 'Photo received and processed successfully',
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