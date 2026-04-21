from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Contact, Message
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chatapp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== ROUTES ====================

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        
        # Validation
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Create user
        user = User(
            username=data['username'],
            email=data['email'],
            password_hash=generate_password_hash(data['password']),
            display_name=data.get('display_name', data['username'])
        )
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'message': 'Account created successfully!',
            'user_id': user.user_id,
            'username': user.username
        }), 201
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        user = User.query.filter_by(username=data['username']).first()
        
        if user and check_password_hash(user.password_hash, data['password']):
            login_user(user)
            return jsonify({
                'message': 'Login successful',
                'user_id': user.user_id,
                'display_name': user.display_name
            }), 200
        
        return jsonify({'error': 'Invalid username or password'}), 401
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/chat/<contact_user_id>')
@login_required
def chat(contact_user_id):
    return render_template('chat.html', contact_user_id=contact_user_id)

# ==================== API ENDPOINTS ====================

@app.route('/api/me')
@login_required
def get_current_user():
    return jsonify({
        'user_id': current_user.user_id,
        'username': current_user.username,
        'display_name': current_user.display_name,
        'email': current_user.email
    })

@app.route('/api/contacts', methods=['GET', 'POST'])
@login_required
def contacts():
    if request.method == 'POST':
        data = request.get_json()
        target_user_id = data.get('user_id')
        
        # Find user by their public ID
        target_user = User.query.filter_by(user_id=target_user_id).first()
        if not target_user:
            return jsonify({'error': 'User not found with this ID'}), 404
        
        if target_user.id == current_user.id:
            return jsonify({'error': 'You cannot add yourself'}), 400
        
        # Check if already in contacts
        existing = Contact.query.filter_by(
            user_id=current_user.id, 
            contact_id=target_user.id
        ).first()
        if existing:
            return jsonify({'error': 'Contact already exists'}), 400
        
        # Add contact (bidirectional - adds both ways like WhatsApp)
        contact1 = Contact(user_id=current_user.id, contact_id=target_user.id)
        contact2 = Contact(user_id=target_user.id, contact_id=current_user.id)
        db.session.add_all([contact1, contact2])
        db.session.commit()
        
        return jsonify({
            'message': 'Contact added successfully',
            'contact': {
                'user_id': target_user.user_id,
                'display_name': target_user.display_name,
                'username': target_user.username
            }
        }), 201
    
    # GET - List contacts
    user_contacts = Contact.query.filter_by(user_id=current_user.id).all()
    contacts_list = [{
        'user_id': c.contact_user.user_id,
        'display_name': c.contact_user.display_name,
        'username': c.contact_user.username,
        'nickname': c.nickname,
        'added_at': c.added_at.isoformat()
    } for c in user_contacts]
    
    return jsonify(contacts_list)

@app.route('/api/messages/<contact_user_id>')
@login_required
def get_messages(contact_user_id):
    contact = User.query.filter_by(user_id=contact_user_id).first_or_404()
    
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == contact.id)) |
        ((Message.sender_id == contact.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    return jsonify([{
        'id': m.id,
        'content': m.content,
        'sender_id': User.query.get(m.sender_id).user_id,
        'timestamp': m.timestamp.isoformat(),
        'is_read': m.is_read,
        'is_mine': m.sender_id == current_user.id
    } for m in messages])

# ==================== WEBSOCKET (Real-time Chat) ====================

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        # Join a room with their user ID for direct messaging
        join_room(f"user_{current_user.id}")
        print(f"User {current_user.username} connected")

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        leave_room(f"user_{current_user.id}")
        print(f"User {current_user.username} disconnected")

@socketio.on('send_message')
@login_required
def handle_message(data):
    receiver_user_id = data.get('receiver_id')
    content = data.get('content', '').strip()
    
    if not content:
        return
    
    receiver = User.query.filter_by(user_id=receiver_user_id).first()
    if not receiver:
        emit('error', {'message': 'Receiver not found'})
        return
    
    # Save message to database
    msg = Message(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        content=content
    )
    db.session.add(msg)
    db.session.commit()
    
    message_data = {
        'id': msg.id,
        'content': msg.content,
        'sender_id': current_user.user_id,
        'sender_name': current_user.display_name,
        'timestamp': msg.timestamp.isoformat(),
        'is_read': False
    }
    
    # Send to receiver's room
    emit('new_message', message_data, room=f"user_{receiver.id}")
    # Confirm to sender
    emit('message_sent', {**message_data, 'is_mine': True}, room=f"user_{current_user.id}")

@socketio.on('typing')
@login_required
def handle_typing(data):
    receiver_user_id = data.get('receiver_id')
    receiver = User.query.filter_by(user_id=receiver_user_id).first()
    if receiver:
        emit('user_typing', {
            'user_id': current_user.user_id,
            'display_name': current_user.display_name
        }, room=f"user_{receiver.id}")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)