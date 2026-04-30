from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import os
import uuid
import random
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)

# CORS properly configured
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Config
DATA_FILE = 'userchat.json'
UPLOAD_FOLDER = 'uploads'
ALLOWED_IMAGE = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEO = {'mp4', 'webm', 'mov'}
ALLOWED_AUDIO = {'webm', 'mp3', 'wav'}

os.makedirs(f"{UPLOAD_FOLDER}/images", exist_ok=True)
os.makedirs(f"{UPLOAD_FOLDER}/videos", exist_ok=True)
os.makedirs(f"{UPLOAD_FOLDER}/audio", exist_ok=True)


# ==================== DATABASE HELPERS ====================

def init_db():
    """Initialize database file if it doesn't exist"""
    if not os.path.exists(DATA_FILE):
        default_data = {
            "users": {},
            "contacts": {},
            "messages": {},
            "chats": {},
            "requests": {}  # Contact requests
        }
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, indent=2, ensure_ascii=False)
        print("[INIT] Created new userchat.json database")


def load_data():
    if not os.path.exists(DATA_FILE):
        init_db()
        return {"users": {}, "contacts": {}, "messages": {}, "chats": {}, "requests": {}}

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            if isinstance(data, list):
                return {"users": {}, "contacts": {}, "messages": {}, "chats": {}, "requests": {}}
            for key in ['users', 'contacts', 'messages', 'chats', 'requests']:
                if key not in data:
                    data[key] = {}
            return data
        except json.JSONDecodeError:
            return {"users": {}, "contacts": {}, "messages": {}, "chats": {}, "requests": {}}


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_id():
    """Generate numeric user ID (10 digits)"""
    return str(random.randint(1000000000, 9999999999))


def get_chat_id(user1, user2):
    return '_'.join(sorted([user1, user2]))


# ==================== AUTH ROUTES ====================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    name = data.get('name', '').strip()
    username = data.get('username', '').strip()
    about = data.get('about', 'Hey there! I am using ChatApp').strip()
    password = data.get('password', '')

    if not name or not username or not password or len(password) < 6:
        return jsonify({"success": False, "error": "Invalid input"}), 400

    db = load_data()

    # Check username unique
    for u in db['users'].values():
        if u['username'] == username:
            return jsonify({"success": False, "error": "Username already taken"}), 400

    user_id = generate_id()
    db['users'][user_id] = {
        "id": user_id,
        "name": name,
        "username": username,
        "about": about,
        "password": password,
        "avatar": None,
        "theme": "light",
        "created": datetime.now().isoformat()
    }
    db['contacts'][user_id] = []
    db['requests'][user_id] = {"sent": [], "received": []}

    save_data(db)
    return jsonify({"success": True, "user": db['users'][user_id]}), 201


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user_id = data.get('id', '').strip()
    password = data.get('password', '')

    db = load_data()
    user = db['users'].get(user_id)

    if not user or user['password'] != password:
        return jsonify({"success": False, "error": "Invalid ID or password"}), 401

    return jsonify({"success": True, "user": user}), 200


# ==================== USER ROUTES ====================

@app.route('/api/user/<user_id>', methods=['GET'])
def get_user(user_id):
    db = load_data()
    user = db['users'].get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    safe_user = {k: v for k, v in user.items() if k != 'password'}
    return jsonify(safe_user), 200


@app.route('/api/user/<user_id>', methods=['PUT'])
def update_user(user_id):
    db = load_data()
    user = db['users'].get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()

    user['name'] = data.get('name', user['name'])
    user['username'] = data.get('username', user['username'])
    user['about'] = data.get('about', user['about'])
    user['theme'] = data.get('theme', user['theme'])

    save_data(db)
    return jsonify({"success": True, "user": user}), 200


@app.route('/api/user/<user_id>/avatar', methods=['POST'])
def upload_avatar(user_id):
    db = load_data()
    if user_id not in db['users']:
        return jsonify({"success": False, "error": "User not found"}), 404

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    if ext not in ALLOWED_IMAGE:
        return jsonify({"success": False, "error": "Invalid image format"}), 400

    # Delete old avatar if exists
    old_avatar = db['users'][user_id].get('avatar')
    if old_avatar:
        old_path = os.path.join(UPLOAD_FOLDER, old_avatar.replace('/uploads/', ''))
        if os.path.exists(old_path):
            os.remove(old_path)

    filename = f"{user_id}_{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, 'images', filename)
    file.save(filepath)

    db['users'][user_id]['avatar'] = f"/uploads/images/{filename}"
    save_data(db)

    return jsonify({"success": True, "avatar": db['users'][user_id]['avatar']}), 200


@app.route('/api/user/<user_id>/avatar', methods=['DELETE'])
def remove_avatar(user_id):
    db = load_data()
    if user_id not in db['users']:
        return jsonify({"success": False, "error": "User not found"}), 404

    # Delete avatar file
    old_avatar = db['users'][user_id].get('avatar')
    if old_avatar:
        old_path = os.path.join(UPLOAD_FOLDER, old_avatar.replace('/uploads/', ''))
        if os.path.exists(old_path):
            os.remove(old_path)

    db['users'][user_id]['avatar'] = None
    save_data(db)

    return jsonify({"success": True}), 200


@app.route('/api/user/<user_id>', methods=['DELETE'])
def delete_account(user_id):
    db = load_data()
    if user_id not in db['users']:
        return jsonify({"error": "User not found"}), 404

    # Delete avatar file if exists
    old_avatar = db['users'][user_id].get('avatar')
    if old_avatar:
        old_path = os.path.join(UPLOAD_FOLDER, old_avatar.replace('/uploads/', ''))
        if os.path.exists(old_path):
            os.remove(old_path)

    del db['users'][user_id]
    if user_id in db['contacts']:
        del db['contacts'][user_id]
    if user_id in db['requests']:
        # Remove from other users' request lists
        for uid, reqs in db['requests'].items():
            if uid != user_id:
                reqs['sent'] = [r for r in reqs['sent'] if r.get('to') != user_id]
                reqs['received'] = [r for r in reqs['received'] if r.get('from') != user_id]
        del db['requests'][user_id]

    chats_to_delete = [c for c in db['chats'] if user_id in c.split('_')]
    for chat_id in chats_to_delete:
        del db['chats'][chat_id]
        if chat_id in db['messages']:
            del db['messages'][chat_id]

    save_data(db)
    return jsonify({"success": True}), 200


# ==================== CONTACT REQUEST ROUTES ====================

@app.route('/api/requests/<user_id>', methods=['GET'])
def get_requests(user_id):
    db = load_data()
    if user_id not in db['users']:
        return jsonify({"error": "User not found"}), 404

    if user_id not in db['requests']:
        db['requests'][user_id] = {"sent": [], "received": []}
        save_data(db)

    requests = db['requests'][user_id]
    # Enrich with user details
    enriched_received = []
    for req in requests.get('received', []):
        user = db['users'].get(req['from'])
        if user:
            enriched_received.append({
                **req,
                "user": {k: v for k, v in user.items() if k != 'password'}
            })

    enriched_sent = []
    for req in requests.get('sent', []):
        user = db['users'].get(req['to'])
        if user:
            enriched_sent.append({
                **req,
                "user": {k: v for k, v in user.items() if k != 'password'}
            })

    return jsonify({
        "received": enriched_received,
        "sent": enriched_sent
    }), 200


@app.route('/api/requests/<user_id>', methods=['POST'])
def send_request(user_id):
    data = request.get_json()
    to_id = data.get('to_id', '').strip()

    db = load_data()

    if to_id not in db['users']:
        return jsonify({"success": False, "error": "User not found"}), 404
    if to_id == user_id:
        return jsonify({"success": False, "error": "Cannot send request to yourself"}), 400

    # Check if already contacts
    if user_id in db['contacts'].get(to_id, []) or to_id in db['contacts'].get(user_id, []):
        return jsonify({"success": False, "error": "Already in contacts"}), 400

    # Check if request already pending
    received = db['requests'].get(to_id, {}).get('received', [])
    for req in received:
        if req['from'] == user_id and req['status'] == 'pending':
            return jsonify({"success": False, "error": "Request already sent"}), 400

    request_id = f"req_{uuid.uuid4().hex}"
    request_data = {
        "id": request_id,
        "from": user_id,
        "to": to_id,
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }

    # Add to sender's sent
    if user_id not in db['requests']:
        db['requests'][user_id] = {"sent": [], "received": []}
    db['requests'][user_id]['sent'].append(request_data)

    # Add to receiver's received
    if to_id not in db['requests']:
        db['requests'][to_id] = {"sent": [], "received": []}
    db['requests'][to_id]['received'].append(request_data)

    save_data(db)

    # Emit notification to receiver
    sender = db['users'][user_id]
    socketio.emit('new_request', {
        "request": request_data,
        "from_user": {k: v for k, v in sender.items() if k != 'password'}
    }, room=f"user_{to_id}")

    return jsonify({"success": True, "request": request_data}), 201


@app.route('/api/requests/<user_id>/<request_id>/accept', methods=['POST'])
def accept_request(user_id, request_id):
    db = load_data()

    # Find request in received
    requests = db['requests'].get(user_id, {}).get('received', [])
    request_obj = None
    for req in requests:
        if req['id'] == request_id and req['status'] == 'pending':
            request_obj = req
            break

    if not request_obj:
        return jsonify({"success": False, "error": "Request not found"}), 404

    from_id = request_obj['from']

    # Update request status
    request_obj['status'] = 'accepted'
    request_obj['accepted_at'] = datetime.now().isoformat()

    # Update in sender's sent list too
    sent_requests = db['requests'].get(from_id, {}).get('sent', [])
    for req in sent_requests:
        if req['id'] == request_id:
            req['status'] = 'accepted'
            req['accepted_at'] = datetime.now().isoformat()
            break

    # Add to contacts (both sides)
    if user_id not in db['contacts']:
        db['contacts'][user_id] = []
    if from_id not in db['contacts']:
        db['contacts'][from_id] = []

    if from_id not in db['contacts'][user_id]:
        db['contacts'][user_id].append(from_id)
    if user_id not in db['contacts'][from_id]:
        db['contacts'][from_id].append(user_id)

    # Create chat
    chat_id = get_chat_id(user_id, from_id)
    if chat_id not in db['chats']:
        db['chats'][chat_id] = {
            "participants": [user_id, from_id],
            "lastMessage": None,
            "unread": 0
        }

    save_data(db)

    # Notify both users
    socketio.emit('request_accepted', {
        "request_id": request_id,
        "contact_id": from_id
    }, room=f"user_{user_id}")

    socketio.emit('request_accepted', {
        "request_id": request_id,
        "contact_id": user_id
    }, room=f"user_{from_id}")

    return jsonify({"success": True}), 200


@app.route('/api/requests/<user_id>/<request_id>/reject', methods=['POST'])
def reject_request(user_id, request_id):
    db = load_data()

    # Find request in received
    requests = db['requests'].get(user_id, {}).get('received', [])
    request_obj = None
    for req in requests:
        if req['id'] == request_id and req['status'] == 'pending':
            request_obj = req
            break

    if not request_obj:
        return jsonify({"success": False, "error": "Request not found"}), 404

    from_id = request_obj['from']

    # Update request status
    request_obj['status'] = 'rejected'
    request_obj['rejected_at'] = datetime.now().isoformat()

    # Update in sender's sent list
    sent_requests = db['requests'].get(from_id, {}).get('sent', [])
    for req in sent_requests:
        if req['id'] == request_id:
            req['status'] = 'rejected'
            req['rejected_at'] = datetime.now().isoformat()
            break

    save_data(db)

    socketio.emit('request_rejected', {
        "request_id": request_id
    }, room=f"user_{from_id}")

    return jsonify({"success": True}), 200


# ==================== CONTACT ROUTES ====================

@app.route('/api/contacts/<user_id>', methods=['GET'])
def get_contacts(user_id):
    db = load_data()
    contacts = db['contacts'].get(user_id, [])
    contact_list = []
    for cid in contacts:
        user = db['users'].get(cid)
        if user:
            safe = {k: v for k, v in user.items() if k != 'password'}
            contact_list.append(safe)
    return jsonify(contact_list), 200


# ==================== MESSAGE ROUTES ====================

@app.route('/api/messages/<chat_id>', methods=['GET'])
def get_messages(chat_id):
    db = load_data()
    messages = db['messages'].get(chat_id, [])
    return jsonify(messages), 200


@app.route('/api/messages/<chat_id>', methods=['POST'])
def send_message(chat_id):
    data = request.get_json()
    db = load_data()

    msg = {
        "id": f"msg_{uuid.uuid4().hex}",
        "sender": data['sender'],
        "type": data.get('type', 'text'),
        "content": data['content'],
        "timestamp": datetime.now().isoformat(),
        "read": False,
        "delivered": True,
        "replyTo": data.get('replyTo'),
        "edited": False
    }

    if chat_id not in db['messages']:
        db['messages'][chat_id] = []
    db['messages'][chat_id].append(msg)

    participants = chat_id.split('_')
    other = [p for p in participants if p != data['sender']][0]

    db['chats'][chat_id] = {
        "participants": participants,
        "lastMessage": msg,
        "unread": db['chats'].get(chat_id, {}).get('unread', 0) + 1
    }

    save_data(db)

    # Emit real-time to both users' rooms
    socketio.emit('new_message', {"chat_id": chat_id, "message": msg}, room=f"user_{other}")
    socketio.emit('new_message', {"chat_id": chat_id, "message": msg}, room=f"user_{data['sender']}")

    return jsonify({"success": True, "message": msg}), 201


@app.route('/api/messages/<chat_id>/<msg_id>', methods=['PUT'])
def edit_message(chat_id, msg_id):
    data = request.get_json()
    db = load_data()

    messages = db['messages'].get(chat_id, [])
    for msg in messages:
        if msg['id'] == msg_id and msg['sender'] == data['sender']:
            msg['content'] = data['content']
            msg['edited'] = True
            msg['editTimestamp'] = datetime.now().isoformat()
            save_data(db)

            participants = chat_id.split('_')
            for p in participants:
                socketio.emit('message_edited', {"chat_id": chat_id, "message": msg}, room=f"user_{p}")
            return jsonify({"success": True}), 200

    return jsonify({"error": "Message not found"}), 404


@app.route('/api/messages/<chat_id>/<msg_id>', methods=['DELETE'])
def delete_message(chat_id, msg_id):
    data = request.get_json()
    db = load_data()

    messages = db['messages'].get(chat_id, [])
    db['messages'][chat_id] = [m for m in messages if not (m['id'] == msg_id and m['sender'] == data['sender'])]

    save_data(db)

    participants = chat_id.split('_')
    for p in participants:
        socketio.emit('message_deleted', {"chat_id": chat_id, "msg_id": msg_id}, room=f"user_{p}")

    return jsonify({"success": True}), 200


@app.route('/api/messages/<chat_id>/read', methods=['POST'])
def mark_read(chat_id):
    data = request.get_json()
    user_id = data['user_id']
    db = load_data()

    messages = db['messages'].get(chat_id, [])
    for msg in messages:
        if msg['sender'] != user_id:
            msg['read'] = True

    if chat_id in db['chats']:
        db['chats'][chat_id]['unread'] = 0

    save_data(db)
    return jsonify({"success": True}), 200


# ==================== MEDIA UPLOAD ====================

@app.route('/api/upload/<media_type>', methods=['POST'])
def upload_media(media_type):
    if media_type not in ['image', 'video', 'audio']:
        return jsonify({"success": False, "error": "Invalid type"}), 400

    if 'file' not in request.files:
        return jsonify({"success": False, "error": "No file"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "No file selected"}), 400

    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    allowed = ALLOWED_IMAGE if media_type == 'image' else ALLOWED_VIDEO if media_type == 'video' else ALLOWED_AUDIO
    if ext not in allowed:
        return jsonify({"success": False, "error": "Invalid format"}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    folder = f"{UPLOAD_FOLDER}/{media_type}s"
    filepath = os.path.join(folder, filename)
    file.save(filepath)

    return jsonify({"success": True, "url": f"/uploads/{media_type}s/{filename}"}), 200


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ==================== SOCKET.IO ====================

@socketio.on('connect')
def on_connect():
    print('Client connected')

@socketio.on('disconnect')
def on_disconnect():
    print('Client disconnected')

@socketio.on('join_user')
def on_join_user(data):
    room = f"user_{data['user_id']}"
    join_room(room)
    print(f'User {data["user_id"]} joined room {room}')

@socketio.on('leave_user')
def on_leave_user(data):
    room = f"user_{data['user_id']}"
    leave_room(room)

@socketio.on('join_chat')
def on_join_chat(data):
    room = data['chat_id']
    join_room(room)

@socketio.on('leave_chat')
def on_leave_chat(data):
    room = data['chat_id']
    leave_room(room)

@socketio.on('typing')
def on_typing(data):
    emit('typing', {"user_id": data['user_id']}, room=data['chat_id'], include_self=False)


# ==================== RUN ====================

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
