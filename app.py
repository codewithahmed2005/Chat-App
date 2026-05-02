from flask import Flask, request, send_from_directory, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
import sqlite3
import random
import string
import os
import base64
from datetime import datetime
import re
import uuid

app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = 'secret!'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# create folders
BASE_DIR = os.path.dirname(__file__)
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
PROFILE_FOLDER = os.path.join(BASE_DIR, 'profile_pics')

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(PROFILE_FOLDER):
    os.makedirs(PROFILE_FOLDER)

def generate_user_id():
    while True:
        user_id = ''.join(random.choices(string.digits, k=10))
        conn = sqlite3.connect('chat.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        if not c.fetchone():
            conn.close()
            return user_id
        conn.close()

def init_db():
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        fullname TEXT,
        password TEXT,
        profile_pic TEXT,
        dark_mode INTEGER DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS friend_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_id TEXT,
        to_id TEXT,
        status TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id TEXT UNIQUE,
        from_id TEXT,
        to_id TEXT,
        content TEXT,
        message_type TEXT,
        file_name TEXT,
        is_edited INTEGER DEFAULT 0,
        is_deleted INTEGER DEFAULT 0,
        reply_to TEXT,
        timestamp TEXT
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Database ready")

init_db()

def save_file(file_data, file_name):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    clean_name = re.sub(r'[^a-zA-Z0-9._-]', '_', file_name)
    unique_name = f"{timestamp}_{clean_name}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_name)
    
    with open(file_path, 'wb') as f:
        f.write(base64.b64decode(file_data))
    
    return f"/uploads/{unique_name}"

def save_profile_pic(file_data, user_id):
    old_files = [f for f in os.listdir(PROFILE_FOLDER) if f.startswith(f"{user_id}_")]
    for old in old_files:
        try:
            os.remove(os.path.join(PROFILE_FOLDER, old))
        except:
            pass
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_path = os.path.join(PROFILE_FOLDER, f"{user_id}_{timestamp}.jpg")
    with open(file_path, 'wb') as f:
        f.write(base64.b64decode(file_data))
    
    return f"/profile_pics/{os.path.basename(file_path)}"

# ============ SERVE FRONTEND ============
@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/profile_pics/<filename>')
def profile_pic(filename):
    return send_from_directory(PROFILE_FOLDER, filename)

# ============ API ROUTES ============
@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        username = data.get('username')
        fullname = data.get('fullname')
        password = data.get('password')
        
        if not username or not fullname or not password:
            return jsonify({'status': 'error', 'message': 'All fields required'})
        
        conn = sqlite3.connect('chat.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        if c.fetchone():
            conn.close()
            return jsonify({'status': 'error', 'message': 'Username already taken'})
        
        user_id = generate_user_id()
        
        c.execute("INSERT INTO users (user_id, username, fullname, password) VALUES (?, ?, ?, ?)", 
                  (user_id, username, fullname, password))
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'user_id': user_id, 'username': username})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        user_id = data.get('user_id')
        password = data.get('password')
        
        conn = sqlite3.connect('chat.db')
        c = conn.cursor()
        c.execute("SELECT user_id, username, fullname, profile_pic, dark_mode FROM users WHERE user_id=? AND password=?", 
                  (user_id, password))
        user = c.fetchone()
        conn.close()
        
        if user:
            return jsonify({
                'status': 'success', 
                'user_id': user[0], 
                'username': user[1], 
                'fullname': user[2],
                'profile_pic': user[3],
                'dark_mode': user[4] if user[4] else 0
            })
        else:
            return jsonify({'status': 'error', 'message': 'Invalid credentials'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/get_profile/<user_id>', methods=['GET'])
def get_profile(user_id):
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, fullname, profile_pic FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return jsonify({
            'status': 'success',
            'user_id': user[0],
            'username': user[1],
            'fullname': user[2],
            'profile_pic': user[3] if user[3] else None
        })
    else:
        return jsonify({'status': 'error', 'message': 'User not found'})

@app.route('/update_profile', methods=['POST'])
def update_profile():
    try:
        data = request.json
        user_id = data.get('user_id')
        username = data.get('username')
        fullname = data.get('fullname')
        profile_pic = data.get('profile_pic')
        
        conn = sqlite3.connect('chat.db')
        c = conn.cursor()
        
        c.execute("SELECT * FROM users WHERE username=? AND user_id!=?", (username, user_id))
        if c.fetchone():
            conn.close()
            return jsonify({'status': 'error', 'message': 'Username already taken'})
        
        if profile_pic is not None:
            if profile_pic == '':
                c.execute("UPDATE users SET username=?, fullname=?, profile_pic=? WHERE user_id=?", 
                          (username, fullname, None, user_id))
            else:
                pic_path = save_profile_pic(profile_pic, user_id)
                c.execute("UPDATE users SET username=?, fullname=?, profile_pic=? WHERE user_id=?", 
                          (username, fullname, pic_path, user_id))
        else:
            c.execute("UPDATE users SET username=?, fullname=? WHERE user_id=?", 
                      (username, fullname, user_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'username': username, 'fullname': fullname})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/search_user/<user_id>', methods=['GET'])
def search_user(user_id):
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, fullname FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    
    if user:
        return jsonify({'status': 'success', 'user_id': user[0], 'username': user[1], 'fullname': user[2]})
    else:
        return jsonify({'status': 'error', 'message': 'User not found'})

@app.route('/send_request', methods=['POST'])
def send_request():
    data = request.json
    from_id = data.get('from_id')
    to_id = data.get('to_id')
    
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("SELECT * FROM friend_requests WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)", 
              (from_id, to_id, to_id, from_id))
    if c.fetchone():
        conn.close()
        return jsonify({'status': 'error', 'message': 'Request already sent'})
    
    c.execute("INSERT INTO friend_requests (from_id, to_id, status) VALUES (?, ?, 'pending')", (from_id, to_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/get_requests/<user_id>', methods=['GET'])
def get_requests(user_id):
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("SELECT from_id FROM friend_requests WHERE to_id=? AND status='pending'", (user_id,))
    requests = c.fetchall()
    conn.close()
    return jsonify({'requests': [r[0] for r in requests]})

@app.route('/accept_request', methods=['POST'])
def accept_request():
    data = request.json
    from_id = data.get('from_id')
    to_id = data.get('to_id')
    
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("UPDATE friend_requests SET status='accepted' WHERE from_id=? AND to_id=?", (from_id, to_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/get_friends/<user_id>', methods=['GET'])
def get_friends(user_id):
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("SELECT from_id FROM friend_requests WHERE to_id=? AND status='accepted'", (user_id,))
    friends1 = c.fetchall()
    c.execute("SELECT to_id FROM friend_requests WHERE from_id=? AND status='accepted'", (user_id,))
    friends2 = c.fetchall()
    conn.close()
    
    friends = [f[0] for f in friends1] + [f[0] for f in friends2]
    return jsonify({'friends': friends})

@app.route('/get_messages/<user_id>/<friend_id>', methods=['GET'])
def get_messages(user_id, friend_id):
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("""SELECT message_id, from_id, content, message_type, file_name, is_edited, is_deleted, reply_to, timestamp 
                 FROM messages 
                 WHERE (from_id=? AND to_id=?) OR (from_id=? AND to_id=?)
                 AND is_deleted=0
                 ORDER BY timestamp ASC""", 
              (user_id, friend_id, friend_id, user_id))
    messages = c.fetchall()
    conn.close()
    
    result = []
    for msg in messages:
        result.append({
            'message_id': msg[0],
            'from_id': msg[1],
            'content': msg[2],
            'message_type': msg[3],
            'file_name': msg[4],
            'is_edited': msg[5],
            'is_deleted': msg[6],
            'reply_to': msg[7],
            'timestamp': msg[8]
        })
    print(f"📥 Loaded {len(result)} messages for {user_id} and {friend_id}")
    return jsonify({'messages': result})

@app.route('/toggle_dark_mode', methods=['POST'])
def toggle_dark_mode():
    data = request.json
    user_id = data.get('user_id')
    dark_mode = data.get('dark_mode')
    
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("UPDATE users SET dark_mode=? WHERE user_id=?", (1 if dark_mode else 0, user_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

# ============ SOCKET EVENTS ============
@socketio.on('join')
def handle_join(data):
    user_id = data['user_id']
    join_room(user_id)
    print(f'✅ {user_id} joined')

@socketio.on('typing')
def handle_typing(data):
    to_id = data['to_id']
    from_id = data['from_id']
    is_typing = data.get('is_typing', True)
    
    emit('user_typing', {
        'from_id': from_id,
        'is_typing': is_typing
    }, room=to_id)

@socketio.on('private_message')
def handle_private_message(data):
    message_id = str(uuid.uuid4())[:8]
    to_id = data['to_id']
    from_id = data['from_id']
    content = data['content']
    message_type = data.get('message_type', 'text')
    file_name = data.get('file_name', '')
    reply_to = data.get('reply_to', None)
    timestamp = datetime.now().strftime("%I:%M %p")
    
    file_path = None
    if message_type in ['image', 'video', 'audio', 'document']:
        file_data = data.get('file_data')
        if file_data:
            file_path = save_file(file_data, file_name)
            content = file_path
    
    # Save to database
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("""INSERT INTO messages (message_id, from_id, to_id, content, message_type, file_name, reply_to, timestamp) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
              (message_id, from_id, to_id, content, message_type, file_name, reply_to, timestamp))
    conn.commit()
    conn.close()
    
    print(f"💾 Message saved: {message_id} from {from_id} to {to_id}")
    
    # Send to receiver
    emit('private_message', {
        'message_id': message_id,
        'from_id': from_id,
        'content': content,
        'message_type': message_type,
        'file_name': file_name,
        'reply_to': reply_to,
        'timestamp': timestamp
    }, room=to_id)
    
    # Also send back to sender for confirmation
    emit('private_message', {
        'message_id': message_id,
        'from_id': from_id,
        'content': content,
        'message_type': message_type,
        'file_name': file_name,
        'reply_to': reply_to,
        'timestamp': timestamp
    }, room=from_id)

@socketio.on('edit_message')
def handle_edit_message(data):
    message_id = data['message_id']
    new_content = data['new_content']
    user_id = data['user_id']
    
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute("UPDATE messages SET content=?, is_edited=1 WHERE message_id=? AND from_id=?", 
              (new_content, message_id, user_id))
    conn.commit()
    conn.close()
    
    emit('message_edited', {
        'message_id': message_id,
        'new_content': new_content
    }, broadcast=True)

@socketio.on('delete_message')
def handle_delete_message(data):
    message_id = data['message_id']
    user_id = data['user_id']
    delete_for_everyone = data.get('delete_for_everyone', True)
    
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    
    if delete_for_everyone:
        c.execute("UPDATE messages SET is_deleted=1 WHERE message_id=? AND from_id=?", (message_id, user_id))
    
    conn.commit()
    conn.close()
    
    emit('message_deleted', {
        'message_id': message_id,
        'delete_for_everyone': delete_for_everyone
    }, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
