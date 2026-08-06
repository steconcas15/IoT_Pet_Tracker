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
import random
from datetime import datetime, timezone, timedelta
from bot.notifier import send_otp_to_telegram

# Import ObjectId for handling MongoDB document identifiers
from bson import ObjectId

# Import JWT tools for authentication and route protection
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity

# Create a blueprint for Digital Twin (DT) specific APIs with a base URL prefix
dt_api = Blueprint('dt_api', __name__, url_prefix='/api/dt')

# Create a blueprint for Digital Replica (DR) specific APIs with a base URL prefix
dr_api = Blueprint('dr_api', __name__, url_prefix='/api/dr')

# Create a blueprint for Users APIs with a base URL prefix (Plurale, nessun verbo)
users_api = Blueprint('users_api', __name__, url_prefix='/api/users')

# Create a blueprint for Authentication APIs with a base URL prefix
auth_api = Blueprint('auth_api', __name__, url_prefix='/api/auth')

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
    Expects JSON payload: { "name": "...", "description": "..." }
    """
    try:
        data = request.get_json()
        current_user_id = get_jwt_identity()

        required_fields = ['name', 'description']
        if not data or not all(field in data for field in required_fields):
            return jsonify({'error': 'Missing required fields: name, description'}), 400

        dt_id = current_app.config['DT_FACTORY'].create_dt(
            name=data['name'],
            description=data['description'],
        )

        current_app.config['DT_FACTORY'].add_service(dt_id=dt_id, service_name='PetDetectionService')
        current_app.config['DT_FACTORY'].add_service(dt_id=dt_id, service_name='RoomStatisticsService')
        current_app.config['DT_FACTORY'].add_service(dt_id=dt_id, service_name='PetStatisticsService')

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
    Completely removes a Home environment and cascades the deletion to all associated 
    Digital Replicas. ID is passed in the URL.
    """
    try:
        current_user_id = get_jwt_identity()

        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the administrator can delete this Home Environment.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        for replica in dt_exists.get("digital_replicas", []):
            try:
                current_app.config['DB_SERVICE'].delete_dr(dr_type=replica["type"], dr_id=replica["id"])
            except Exception as e:
                print(f"[WARNING] Failed to delete replica {replica['id']} of type {replica['type']}: {str(e)}")

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
    Adds a viewer user to a specific Home Environment via their USERNAME.
    Expects JSON payload: { "viewer_username": "string" }
    """
    try:
        data = request.get_json()
        if not data or 'viewer_username' not in data:
            return jsonify({'error': 'Missing required fields: viewer_username'}), 400

        viewer_username = data['viewer_username']
        current_user_id = get_jwt_identity()

        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the administrator can add viewers.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': 'Home Environment not found'}), 404

        viewer_user = current_app.config['DB_SERVICE'].get_user_by_username(viewer_username)
        if not viewer_user:
            return jsonify({'error': f'The user {viewer_username} is not registered.'}), 404
        
        viewer_id = str(viewer_user['_id'])

        if viewer_id == current_user_id:
            return jsonify({'error': 'The admin cannot also be a viewer.'}), 400

        if dt_id in viewer_user.get('data', {}).get('viewable_homes', []):
            return jsonify({'error': 'The user is already a viewer of this home.'}), 400

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
@dt_api.route('/<dt_id>/viewers/<viewer_id>', methods=['DELETE'])
@jwt_required()
def remove_viewer(dt_id, viewer_id):
    """
    Removes a specific user's viewer access via their ID.
    Both IDs are passed in the URL path.
    """
    try:
        current_user_id = get_jwt_identity()

        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Unauthorized. Only the admin can remove viewers.'}), 403
             
        current_app.config['DB_SERVICE'].remove_viewable_home(viewer_id, dt_id)

        return jsonify({
            'status': 'success',
            'message': f'Viewer con ID {viewer_id} rimosso con successo dalla Home {dt_id}'
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
    Crea una Digital Replica e la associa al Digital Twin. 
    L'ID del DT è nell'URL, il body contiene solo i dati della replica.
    """
    try:
        raw_data = request.get_json() or {}

        if 'name' not in raw_data:
            return jsonify({'error': 'Campi obbligatori mancanti: name'}), 400

        dr_name = raw_data['name']
        current_user_id = get_jwt_identity()

        factory_key = f'DR_FACTORY_{dr_type.upper()}'
        dr_factory = current_app.config.get(factory_key)
        
        if not dr_factory:
            return jsonify({'error': f'Tipo di Digital Replica non supportato: {dr_type}'}), 400

        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Non autorizzato. Solo l\'amministratore può aggiungere repliche.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment con ID {dt_id} non trovato'}), 404

        for replica in dt_exists.get("digital_replicas", []):
            if replica.get("type") == dr_type:
                if dr_type == 'pet':
                    return jsonify({'error': 'Questa casa ha già un pet associato.'}), 409
                existing_dr = current_app.config['DB_SERVICE'].get_dr(dr_type, replica["id"])
                if existing_dr and existing_dr.get("profile", {}).get("name") == dr_name:
                    return jsonify({'error': f'Un(a) {dr_type} con il nome "{dr_name}" esiste già.'}), 409

        initial_data = {
            "profile": {
                "name": dr_name,
                "description": raw_data.get("description", "")
            }
        }
        
        for key, value in raw_data.items():
            if key not in ['name', 'description']:
                initial_data["profile"][key] = value

        validated_dr = dr_factory.create_dr(dr_type=dr_type, initial_data=initial_data)
        dr_id = current_app.config['DB_SERVICE'].save_dr(dr_type=dr_type, dr_data=validated_dr)
        
        current_app.config['DT_FACTORY'].add_digital_replica(dt_id=dt_id, dr_type=dr_type, dr_id=dr_id)

        return jsonify({
            'status': 'success',
            'message': f'{dr_type.capitalize()} creato(a) e collegato(a) con successo.',
            'data': {
                'home_id': dt_id,
                f'{dr_type}_id': dr_id,
                'name': dr_name
            }
        }), 201

    except ValueError as ve:
        return jsonify({'error': f'Validazione fallita: {str(ve)}'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Errore durante la creazione: {str(e)}'}), 500

    
@dr_api.route('/<dt_id>/replicas/<dr_type>/<dr_id>', methods=['DELETE'])
@jwt_required()
def remove_digital_replica(dt_id, dr_type, dr_id):
    """
    Rimuove una Digital Replica specifica. Mantiene il dr_type per instradamento db.
    """
    try:
        factory_key = f'DR_FACTORY_{dr_type.upper()}'
        if factory_key not in current_app.config:
            return jsonify({'error': f'Tipo di Digital Replica non supportato: {dr_type}'}), 400

        current_user_id = get_jwt_identity()

        is_admin = current_app.config['DB_SERVICE'].is_home_admin(dt_id, current_user_id)
        if not is_admin:
            return jsonify({'error': 'Non autorizzato. Solo l\'admin può rimuovere i componenti.'}), 403

        dt_exists = current_app.config['DT_FACTORY'].get_dt(dt_id)
        if not dt_exists:
            return jsonify({'error': f'Home Environment con ID {dt_id} non trovato'}), 404

        dr_linked = any(
            replica.get("id") == dr_id and replica.get("type") == dr_type 
            for replica in dt_exists.get("digital_replicas", [])
        )
        
        if not dr_linked:
            return jsonify({'error': f'{dr_type.capitalize()} non è collegato a questa Casa.'}), 404

        current_app.config['DB_SERVICE'].delete_dr(dr_type=dr_type, dr_id=dr_id)
        current_app.config['DT_FACTORY'].remove_digital_replica(dt_id=dt_id, dr_id=dr_id)

        return jsonify({
            'status': 'success',
            'message': f'{dr_type.capitalize()} {dr_id} eliminato(a) e scollegato(a) da Home {dt_id}.'
        }), 200

    except ValueError as ve:
        return jsonify({'error': f'Validazione fallita: {str(ve)}'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Errore durante l\'eliminazione: {str(e)}'}), 500        


# ----------------- CAMERA DEVICE AUTHENTICATION -------------------
@dr_api.route('/devices/tokens', methods=['POST'])
def device_login():
    """
    Endpoint for automatic authentication of IoT devices.
    """
    data = request.get_json()
    if not data or 'room_name' not in data:
        return jsonify({'error': 'Device credentials missing'}), 400

    room_name = data.get('room_name')
    db_service = current_app.config['DB_SERVICE']
    
    query = {"profile.name": room_name}
    rooms = db_service.query_drs("room", query)

    if not rooms:
        return jsonify({'error': 'Unauthorized or nonexistent device'}), 401

    access_token = create_access_token(identity=f"device_{room_name}")
    
    return jsonify({'status': 'success', 'access_token': access_token}), 200


# ----------------- PHOTO RECEPTION (TELEMETRY) FROM ESP32-CAM -------------------
@dr_api.route('/<dt_id>/rooms/<room_id>/telemetry', methods=['POST'])
@jwt_required()
def receive_telemetry(dt_id, room_id):
    """
    Receives telemetry and photo from ESP32-CAM.
    Hierarchy uses IDs: /api/dr/<dt_id>/rooms/<room_id>/telemetry
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
            
            # Fetch room details using the ID
            room_dr = db_service.get_dr("room", room_id)
            if not room_dr:
                return jsonify({'error': 'Stanza non trovata'}), 404
                
            room_name = room_dr.get("profile", {}).get("name", "Unknown")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = secure_filename(f"{room_name}_{timestamp}.jpg")
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            file.save(filepath)
            
            try:
                dt_factory = current_app.config['DT_FACTORY']
                pet_detector = current_app.config.get('PET_DETECTOR')
                
                dt_instance = dt_factory.get_dt_instance(home_id)
                
                if not dt_instance:
                    print(f"[TELEMETRY] ERRORE: La casa con ID '{home_id}' non esiste nel database!")
                else:
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
                print(f"[TELEMETRY ERROR] Eccezione durante esecuzione servizio: {str(service_error)}")

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
    """Register a new user on the platform."""
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
    """Authenticate a user and create a JWT token."""
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
    """Delete the JWT token / session."""
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
    """Recupera le statistiche aggiornate in tempo reale delle stanze."""
    try:
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'Utente non trovato'}), 404

        owned_homes = user.get('data', {}).get('owned_homes', [])
        viewable_homes = user.get('data', {}).get('viewable_homes', [])

        if dt_id not in owned_homes and dt_id not in viewable_homes:
            return jsonify({'error': 'Accesso negato. Non sei admin né viewer di questa casa.'}), 403

        dt_data = dt_factory.get_dt(dt_id)
        if not dt_data:
            return jsonify({'error': 'Home Environment non trovato'}), 404

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
                    if isinstance(last_entry_time, str):
                        last_entry_time = datetime.fromisoformat(last_entry_time.replace("Z", "+00:00"))
                    elif isinstance(last_entry_time, datetime) and last_entry_time.tzinfo is None:
                        last_entry_time = last_entry_time.replace(tzinfo=timezone.utc)
                        
                    time_diff = datetime.now(timezone.utc) - last_entry_time
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
        return jsonify({'status': 'error', 'message': f'Errore nel recupero statistiche: {str(e)}'}), 500
    

@dt_api.route('/<dt_id>/pet/statistics', methods=['GET'])
@jwt_required()
def get_pet_statistics(dt_id):
    """
    Recupera le statistiche del pet al singolare: /<dt_id>/pet/statistics
    Include lo storico completo (fino a 30 giorni) aggiornato in tempo reale.
    """
    try:
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'Utente non trovato'}), 404

        owned_homes = user.get('data', {}).get('owned_homes', [])
        viewable_homes = user.get('data', {}).get('viewable_homes', [])

        if dt_id not in owned_homes and dt_id not in viewable_homes:
            return jsonify({'error': 'Accesso negato. Non sei admin né viewer di questa casa.'}), 403

        dt_data = dt_factory.get_dt(dt_id)
        if not dt_data:
            return jsonify({'error': 'Home Environment non trovato'}), 404

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
                
                # --- 1. CALCOLO DELLA SESSIONE IN TEMPO REALE ---
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
                
                # --- 2. AGGIORNAMENTO STORICO ---
                if daily_buzzer_stats:
                    # Assumiamo che il primo elemento (indice 0) sia la giornata di oggi
                    today_stats = daily_buzzer_stats[0]
                    today_stats["auto_duration_mins"] = round(today_stats.get("auto_duration_mins", 0.0) + current_session_mins, 2)
                    today_stats["auto_violations_count"] = today_stats.get("auto_violations_count", 0) + current_violation
                else:
                    # Se l'array è vuoto, creiamo noi l'elemento di oggi
                    daily_buzzer_stats = [{
                        "date": datetime.now(timezone.utc).isoformat(),
                        "auto_duration_mins": round(current_session_mins, 2),
                        "auto_violations_count": current_violation
                    }]

                # --- 3. SANITIZZAZIONE DATE PER JSON ---
                # Evita crash di jsonify se PyMongo restituisce date in formato non standard
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
                    "buzzer_status": pet_data.get("buzzer_status", ""),
                    "is_buzzer_active_now": bool(last_buzzer_start),
                    "daily_buzzer_stats": daily_buzzer_stats  # Restituiamo tutto l'array
                }
                
                # Dato che c'è solo un pet per casa, interrompiamo il ciclo
                break 

        if not pet_stats:
            return jsonify({'error': 'Nessun pet associato a questa casa.'}), 404

        return jsonify({
            'status': 'success',
            'data': {
                'home_id': dt_id,
                'pet': pet_stats
            }
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'Errore nel recupero statistiche pet: {str(e)}'}), 500
    

# ----------------- GET USER HOMES (Admin & Viewer) -----------------
@dt_api.route('/', methods=['GET'])
@jwt_required()
def get_user_homes():
    """
    Recupera tutte le case (Digital Twins) associate all'utente autenticato,
    suddividendole tra quelle di cui è proprietario (admin) e quelle di cui è viewer.
    """
    try:
        # Estrae l'ID dell'utente dal token JWT
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        # Recupera il documento utente dal database
        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'Utente non trovato'}), 404

        # Estrae gli array degli ID delle case
        owned_home_ids = user.get('data', {}).get('owned_homes', [])
        viewable_home_ids = user.get('data', {}).get('viewable_homes', [])

        owned_homes = []
        viewable_homes = []

        # Recupera i dettagli per le case di proprietà
        for dt_id in owned_home_ids:
            dt = dt_factory.get_dt(dt_id)
            if dt:
                owned_homes.append({
                    'home_id': dt_id,
                    'name': dt.get('name', 'Unknown'),
                    'description': dt.get('description', ''),
                    'role': 'admin'
                })

        # Recupera i dettagli per le case visibili come viewer
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
            'message': f'Errore nel recupero delle case: {str(e)}'
        }), 500
    

# ----------------- GET HOME MANAGEMENT DATA (Admin) -----------------
@dt_api.route('/<dt_id>/management', methods=['GET'])
@jwt_required()
def get_home_management(dt_id):
    """Recupera tutti i componenti e i viewer per la gestione admin."""
    try:
        current_user_id = get_jwt_identity()
        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'Utente non trovato'}), 404

        owned_homes = user.get('data', {}).get('owned_homes', [])
        if dt_id not in owned_homes:
            return jsonify({'error': 'Accesso negato. Solo l\'admin può gestire la casa.'}), 403

        dt_data = dt_factory.get_dt(dt_id)
        if not dt_data: return jsonify({'error': 'Casa non trovata'}), 404

        rooms, doors, pets, viewers = [], [], [], []

        for replica in dt_data.get("digital_replicas", []):
            # Convertiamo l'ID in stringa per sicurezza
            raw_id = replica.get("id")
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

        # Recupera i viewer cercando gli utenti che hanno questo dt_id nei viewable_homes
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
    Elimina l'account di un utente.
    Requisito di sicurezza: Un utente può eliminare SOLO il proprio account.
    Esegue un'eliminazione a cascata di tutte le case di cui è amministratore.
    """
    try:
        # Estraiamo l'identità dal token di chi sta facendo la richiesta
        current_user_id = get_jwt_identity()

        # SICUREZZA: Controlliamo che l'ID nell'URL corrisponda a quello del token
        if str(current_user_id) != str(user_id):
            return jsonify({
                'error': 'Azione non autorizzata. Puoi eliminare esclusivamente il tuo account.'
            }), 403

        db_service = current_app.config['DB_SERVICE']
        dt_factory = current_app.config['DT_FACTORY']

        # Recuperiamo i dati dell'utente per scoprire quali case possiede
        user = db_service.get_user_by_id(user_id)
        if not user:
            return jsonify({'error': 'Utente non trovato.'}), 404

        # 1. ELIMINAZIONE A CASCATA: Rimuoviamo tutte le case di cui è amministratore
        owned_homes = user.get('data', {}).get('owned_homes', [])
        
        for home_id in owned_homes:
            dt_exists = dt_factory.get_dt(home_id)
            if dt_exists:
                # 1A. Elimina tutte le repliche (stanze, pet, etc.) associate alla casa
                for replica in dt_exists.get("digital_replicas", []):
                    try:
                        db_service.delete_dr(dr_type=replica["type"], dr_id=replica["id"])
                    except Exception as e:
                        print(f"[WARNING] Errore eliminazione replica {replica['id']}: {str(e)}")

                # 1B. Elimina il Digital Twin della casa
                dt_factory.delete_dt(home_id)
                
                # 1C. Rimuove la casa dalle liste "viewable_homes" di eventuali altri utenti viewer
                db_service.remove_home_from_all_users(home_id)

        # 2. ELIMINAZIONE UTENTE: Infine, cancelliamo il documento dell'utente stesso
        db_service.delete_dr(dr_type='user', dr_id=user_id)

        return jsonify({
            'status': 'success',
            'message': 'Account e tutti gli ambienti associati eliminati con successo.'
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': f'Errore durante l\'eliminazione dell\'account: {str(e)}'
        }), 500


@auth_api.route('/otp/generate', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True) # Mettiamo optional=True per evitare che il blocco OPTIONS fallisca
def generate_otp():
    """Genera un OTP e lo invia direttamente su Telegram all'utente loggato"""
    if request.method == 'OPTIONS':
        return '', 200

    try:
        current_user_id = get_jwt_identity()
        if not current_user_id:
            return jsonify({'error': 'Token mancante o non valido.'}), 401

        db_service = current_app.config['DB_SERVICE']
        
        # Genera OTP a 6 cifre
        otp_code = str(random.randint(100000, 999999))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        
        # Salva l'OTP e resetta lo stato di verifica nel database
        db_service.update_dr(
            dr_type='user',
            dr_id=current_user_id,
            update_data={
                "data.otp_code": otp_code,
                "data.otp_expires_at": expires_at.isoformat(),
                "data.otp_verified": False
            }
        )
        
        # Invia il messaggio su Telegram
        sent = send_otp_to_telegram(current_user_id, otp_code)
        
        if not sent:
            return jsonify({
                'status': 'error', 
                'message': 'Impossibile inviare l\'OTP su Telegram. Assicurati di aver fatto il /login sul bot.'
            }), 400

        return jsonify({
            'status': 'success',
            'message': 'Codice OTP inviato con successo sul tuo Telegram!'
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@auth_api.route('/otp/verify', methods=['POST', 'OPTIONS'])
@jwt_required(optional=True)
def verify_otp():
    """Verifica il codice OTP inviato dall'utente via web"""
    if request.method == 'OPTIONS':
        return '', 200

    try:
        current_user_id = get_jwt_identity()
        if not current_user_id:
            return jsonify({'error': 'Token mancante o non valido.'}), 401

        data = request.get_json()
        if not data or 'otp_code' not in data:
            return jsonify({'error': 'Codice OTP mancante.'}), 400

        user_otp = str(data['otp_code']).strip()
        db_service = current_app.config['DB_SERVICE']

        # Recupera i dati dell'utente dal DB
        user = db_service.get_user_by_id(current_user_id)
        if not user:
            return jsonify({'error': 'Utente non trovato.'}), 404

        user_data = user.get('data', {})
        saved_otp = user_data.get('otp_code')
        expires_at_str = user_data.get('otp_expires_at')

        # Controlla se esiste un OTP attivo e se corrisponde
        if not saved_otp or saved_otp != user_otp:
            return jsonify({'error': 'Codice OTP non valido.'}), 400

        # Verifica la scadenza (5 minuti)
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires_at:
                return jsonify({'error': 'Codice OTP scaduto. Generane uno nuovo.'}), 400

        # OTP corretto: puliamo l'OTP dal DB per sicurezza e segniamo l'ok
        db_service.update_dr(
            dr_type='user',
            dr_id=current_user_id,
            update_data={
                "data.otp_code": None,
                "data.otp_expires_at": None,
                "data.otp_verified": True
            }
        )

        return jsonify({
            'status': 'success',
            'message': 'OTP verificato con successo.'
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
            
# ==============================================================================
#                       BLUEPRINTS REGISTRATION UTILITY
# ==============================================================================

def register_api_blueprints(app):
    """Register all API blueprints with the Flask app"""
    app.register_blueprint(dt_api)
    app.register_blueprint(dr_api)
    app.register_blueprint(users_api)
    app.register_blueprint(auth_api)