from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import os
import uuid
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
# CORS properly configure karo
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

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "contacts": {}, "messages": {}, "chats": {}}
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            # Fix agar list format mein ho
            if isinstance(data, list):
                return {"users": {}, "contacts": {}, "messages": {}, "chats": {}}
            # Fix agar keys missing ho
            for key in ['users', 'contacts', 'messages', 'chats']:
                if key not in data:
                    data[key] = {} if key != 'contacts' else {}
            return data
        except:
            return {"users": {}, "contacts": {}, "messages": {}, "chats": {}}


def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def generate_id():
    return 'ID' + str(uuid.uuid4()).upper().replace('-', '')[:10]


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
    # Don't send password
    safe_user = {k: v for k, v in user.items() if k != 'password'}
    return jsonify(safe_user), 200


@app.route('/api/user/<user_id>', methods=['PUT'])
def update_user(user_id):
    db = load_data()
    user = db['users'].get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    
    # ID can never be changed
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
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if ext not in ALLOWED_IMAGE:
        return jsonify({"success": False, "error": "Invalid image format"}), 400

    filename = f"{user_id}_{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_FOLDER, 'images', filename)
    file.save(filepath)

    db['users'][user_id]['avatar'] = f"/uploads/images/{filename}"
    save_data(db)
    
    return jsonify({"success": True, "avatar": db['users'][user_id]['avatar']}), 200


@app.route('/api/user/<user_id>', methods=['DELETE'])
def delete_account(user_id):
    db = load_data()
    if user_id not in db['users']:
        return jsonify({"error": "User not found"}), 404

    # Delete user
    del db['users'][user_id]
    del db['contacts'][user_id]

    # Delete all related chats and messages
    chats_to_delete = [c for c in db['chats'] if user_id in c.split('_')]
    for chat_id in chats_to_delete:
        del db['chats'][chat_id]
        if chat_id in db['messages']:
            del db['messages'][chat_id]

    save_data(db)
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


@app.route('/api/contacts/<user_id>', methods=['POST'])
def add_contact(user_id):
    data = request.get_json()
    contact_id = data.get('contact_id', '').strip()

    db = load_data()
    
    if contact_id not in db['users']:
        return jsonify({"error": "User not found"}), 404
    if contact_id == user_id:
        return jsonify({"error": "Cannot add yourself"}), 400

    if user_id not in db['contacts']:
        db['contacts'][user_id] = []
    
    if contact_id in db['contacts'][user_id]:
        return jsonify({"error": "Already in contacts"}), 400

    db['contacts'][user_id].append(contact_id)
    save_data(db)
    
    # Auto-create chat
    chat_id = get_chat_id(user_id, contact_id)
    if chat_id not in db['chats']:
        db['chats'][chat_id] = {
            "participants": [user_id, contact_id],
            "lastMessage": None,
            "unread": 0
        }
        save_data(db)

    return jsonify({"success": True}), 200


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

    # Update chat
    participants = chat_id.split('_')
    other = [p for p in participants if p != data['sender']][0]
    
    db['chats'][chat_id] = {
        "participants": participants,
        "lastMessage": msg,
        "unread": db['chats'].get(chat_id, {}).get('unread', 0) + 1
    }
    
    save_data(db)

    # Emit real-time
    socketio.emit('new_message', {"chat_id": chat_id, "message": msg}, room=chat_id)

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
            
            socketio.emit('message_edited', {"chat_id": chat_id, "message": msg}, room=chat_id)
            return jsonify({"success": True}), 200

    return jsonify({"error": "Message not found"}), 404


@app.route('/api/messages/<chat_id>/<msg_id>', methods=['DELETE'])
def delete_message(chat_id, msg_id):
    data = request.get_json()
    db = load_data()

    messages = db['messages'].get(chat_id, [])
    db['messages'][chat_id] = [m for m in messages if not (m['id'] == msg_id and m['sender'] == data['sender'])]
    
    save_data(db)
    socketio.emit('message_deleted', {"chat_id": chat_id, "msg_id": msg_id}, room=chat_id)
    
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
        return jsonify({"error": "Invalid type"}), 400

    if 'file' not in request.files:
        return jsonify({"error": "No file"}), 400

    file = request.files['file']
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

    allowed = ALLOWED_IMAGE if media_type == 'image' else ALLOWED_VIDEO if media_type == 'video' else ALLOWED_AUDIO
    if ext not in allowed:
        return jsonify({"error": "Invalid format"}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    folder = f"{UPLOAD_FOLDER}/{media_type}s"
    filepath = os.path.join(folder, filename)
    file.save(filepath)

    return jsonify({"success": True, "url": f"/uploads/{media_type}s/{filename}"}), 200


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ==================== SOCKET.IO ====================

@socketio.on('join')
def on_join(data):
    room = data['chat_id']
    join_room(room)

@socketio.on('leave')
def on_leave(data):
    room = data['chat_id']
    leave_room(room)

@socketio.on('typing')
def on_typing(data):
    emit('typing', {"user_id": data['user_id']}, room=data['chat_id'], include_self=False)


# ==================== RUN ====================

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
