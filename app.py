import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Contact, Message
import os
import re
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validation helpers
USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]{3,80}$')
EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def validate_username(username):
    if not username or not USERNAME_REGEX.match(username):
        return "Username must be 3-80 characters, alphanumeric and underscores only"
    return None

def validate_email(email):
    if not email or not EMAIL_REGEX.match(email):
        return "Invalid email format"
    return None

def validate_password(password):
    if not password or len(password) < 6 or len(password) > 128:
        return "Password must be 6-128 characters"
    return None

def validate_display_name(name):
    if name and len(name) > 100:
        return "Display name must be under 100 characters"
    return None

def validate_about(about):
    if about and len(about) > 500:
        return "About must be under 500 characters"
    return None

def validate_message_content(content):
    if not content or not content.strip():
        return "Message content cannot be empty"
    if len(content) > 5000:
        return "Message too long (max 5000 characters)"
    return None

def create_app():
    app = Flask(__name__)
    
    # Security: Require SECRET_KEY in production, no hardcoded fallback
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        if os.environ.get('FLASK_ENV') == 'production':
            raise ValueError("SECRET_KEY environment variable is required in production")
        secret_key = os.urandom(32).hex()
    app.config['SECRET_KEY'] = secret_key
    
    # Database configuration
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chatapp.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
    
    # SocketIO with restricted CORS for production
    cors_origins = os.environ.get('CORS_ORIGINS', '*')
    if cors_origins != '*':
        cors_origins = cors_origins.split(',')
    
    socketio = SocketIO(
        app, 
        cors_allowed_origins=cors_origins, 
        async_mode='eventlet',
        ping_timeout=60,
        ping_interval=25
    )
    
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # ==================== AUTH ROUTES ====================
    
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('chat_page'))
        return redirect(url_for('login'))
    
    @app.route('/login')
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('chat_page'))
        return render_template('login.html')
    
    @app.route('/register')
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('chat_page'))
        return render_template('register.html')
    
    @app.route('/app')
    @login_required
    def chat_page():
        return render_template('app.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
    # ==================== API AUTH ====================
    
    @app.route('/api/register', methods=['POST'])
    def api_register():
        try:
            data = request.get_json() or {}
            
            # Validation
            username = data.get('username', '').strip()
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')
            display_name = data.get('display_name', '').strip() or username
            
            errors = []
            err = validate_username(username)
            if err: errors.append(err)
            err = validate_email(email)
            if err: errors.append(err)
            err = validate_password(password)
            if err: errors.append(err)
            err = validate_display_name(display_name)
            if err: errors.append(err)
            
            if errors:
                return jsonify({'error': ' | '.join(errors)}), 400
            
            # Check uniqueness
            if User.query.filter_by(username=username).first():
                return jsonify({'error': 'Username already exists'}), 409
            if User.query.filter_by(email=email).first():
                return jsonify({'error': 'Email already exists'}), 409
            
            # Generate unique user_id with retry
            max_retries = 5
            user_id = None
            for _ in range(max_retries):
                candidate = generate_user_id()
                if not User.query.filter_by(user_id=candidate).first():
                    user_id = candidate
                    break
            
            if not user_id:
                return jsonify({'error': 'Failed to generate unique ID'}), 500
            
            user = User(
                user_id=user_id,
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                display_name=display_name,
                about='Hey there! I am using ChatApp.'
            )
            db.session.add(user)
            db.session.commit()
            
            logger.info(f"New user registered: {username} ({user_id})")
            
            return jsonify({
                'message': 'Account created successfully!',
                'user_id': user.user_id,
                'username': user.username
            }), 201
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Registration error: {str(e)}")
            return jsonify({'error': 'Registration failed'}), 500
    
    @app.route('/api/login', methods=['POST'])
    def api_login():
        try:
            data = request.get_json() or {}
            username = data.get('username', '').strip()
            password = data.get('password', '')
            
            if not username or not password:
                return jsonify({'error': 'Username and password required'}), 400
            
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password):
                login_user(user, remember=True)
                logger.info(f"User logged in: {username}")
                return jsonify({
                    'user_id': user.user_id,
                    'display_name': user.display_name,
                    'username': user.username
                }), 200
            
            return jsonify({'error': 'Invalid credentials'}), 401
            
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return jsonify({'error': 'Login failed'}), 500
    
    # ==================== API USER / PROFILE ====================
    
    @app.route('/api/me')
    @login_required
    def get_me():
        return jsonify({
            'user_id': current_user.user_id,
            'username': current_user.username,
            'display_name': current_user.display_name,
            'email': current_user.email,
            'about': current_user.about or 'Hey there! I am using ChatApp.',
            'profile_pic': current_user.profile_pic or 'default.png'
        })
    
    @app.route('/api/me', methods=['PUT'])
    @login_required
    def update_profile():
        try:
            data = request.get_json() or {}
            
            # Validate inputs
            display_name = data.get('display_name', '').strip()
            username = data.get('username', '').strip()
            about = data.get('about', '').strip()
            profile_pic = data.get('profile_pic', '').strip()
            
            errors = []
            if display_name:
                err = validate_display_name(display_name)
                if err: errors.append(err)
            if username:
                err = validate_username(username)
                if err: errors.append(err)
            if about:
                err = validate_about(about)
                if err: errors.append(err)
            
            if errors:
                return jsonify({'error': ' | '.join(errors)}), 400
            
            # Check username uniqueness if changed
            if username and username != current_user.username:
                if User.query.filter_by(username=username).first():
                    return jsonify({'error': 'Username already taken'}), 409
                current_user.username = username
            
            # Update fields
            if display_name:
                current_user.display_name = display_name
            if about is not None:
                current_user.about = about
            if profile_pic:
                # Security: Prevent path traversal
                safe_pic = os.path.basename(profile_pic)
                if safe_pic and re.match(r'^[a-zA-Z0-9_\-\.]+\.(jpg|jpeg|png|gif|webp)$', safe_pic, re.I):
                    current_user.profile_pic = safe_pic
            
            db.session.commit()
            
            return jsonify({
                'message': 'Profile updated',
                'user_id': current_user.user_id,
                'username': current_user.username,
                'display_name': current_user.display_name,
                'about': current_user.about
            })
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Profile update error: {str(e)}")
            return jsonify({'error': 'Update failed'}), 500
    
    @app.route('/api/users/<user_id>')
    @login_required
    def get_user_profile(user_id):
        user = User.query.filter_by(user_id=user_id).first_or_404()
        return jsonify({
            'user_id': user.user_id,
            'display_name': user.display_name,
            'username': user.username,
            'about': user.about or 'Hey there! I am using ChatApp.',
            'profile_pic': user.profile_pic or 'default.png'
        })
    
    # ==================== API CONTACTS ====================
    
    @app.route('/api/contacts', methods=['GET', 'POST'])
    @login_required
    def contacts_api():
        if request.method == 'POST':
            return add_contact()
        return get_contacts()
    
    def add_contact():
        try:
            data = request.get_json() or {}
            target_user_id = data.get('user_id', '').strip()
            
            if not target_user_id or len(target_user_id) != 10:
                return jsonify({'error': 'Valid 10-digit User ID required'}), 400
            
            target_user = User.query.filter_by(user_id=target_user_id).first()
            
            if not target_user:
                return jsonify({'error': 'User not found'}), 404
            if target_user.id == current_user.id:
                return jsonify({'error': 'Cannot add yourself'}), 400
            
            existing = Contact.query.filter_by(
                user_id=current_user.id, 
                contact_id=target_user.id
            ).first()
            if existing:
                return jsonify({'error': 'Already in contacts'}), 409
            
            c1 = Contact(user_id=current_user.id, contact_id=target_user.id)
            c2 = Contact(user_id=target_user.id, contact_id=current_user.id)
            db.session.add_all([c1, c2])
            db.session.commit()
            
            last_msg = get_last_message(current_user.id, target_user.id)
            
            logger.info(f"Contact added: {current_user.username} -> {target_user.username}")
            
            return jsonify({
                'user_id': target_user.user_id,
                'display_name': target_user.display_name,
                'username': target_user.username,
                'about': target_user.about,
                'last_message': last_msg
            }), 201
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Add contact error: {str(e)}")
            return jsonify({'error': 'Failed to add contact'}), 500
    
    def get_contacts():
        try:
            # Optimized: Single query for contacts with user info
            user_contacts = Contact.query.filter_by(user_id=current_user.id).all()
            
            if not user_contacts:
                return jsonify([])
            
            contact_ids = [c.contact_id for c in user_contacts]
            
            # Batch fetch last messages using a more efficient approach
            result = []
            for c in user_contacts:
                last_msg = get_last_message(current_user.id, c.contact_id)
                unread_count = Message.query.filter_by(
                    sender_id=c.contact_id,
                    receiver_id=current_user.id,
                    is_read=False
                ).count()
                
                result.append({
                    'user_id': c.contact_user.user_id,
                    'display_name': c.contact_user.display_name,
                    'username': c.contact_user.username,
                    'about': c.contact_user.about,
                    'last_message': last_msg,
                    'unread_count': unread_count
                })
            
            result.sort(
                key=lambda x: x['last_message']['timestamp'] if x['last_message'] else '1970-01-01T00:00:00',
                reverse=True
            )
            return jsonify(result)
            
        except Exception as e:
            logger.error(f"Get contacts error: {str(e)}")
            return jsonify({'error': 'Failed to load contacts'}), 500
    
    def get_last_message(user1_id, user2_id):
        try:
            msg = Message.query.filter(
                ((Message.sender_id == user1_id) & (Message.receiver_id == user2_id)) |
                ((Message.sender_id == user2_id) & (Message.receiver_id == user1_id)),
                Message.is_deleted == False
            ).order_by(Message.timestamp.desc()).first()
            
            if msg:
                return {
                    'content': msg.content,
                    'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                    'is_mine': msg.sender_id == user1_id
                }
            return None
        except Exception:
            return None
    
    # ==================== API MESSAGES ====================
    
    @app.route('/api/messages/<contact_user_id>')
    @login_required
    def get_messages(contact_user_id):
        try:
            contact = User.query.filter_by(user_id=contact_user_id).first_or_404()
            
            # Mark unread messages as read
            unread = Message.query.filter_by(
                sender_id=contact.id,
                receiver_id=current_user.id,
                is_read=False
            ).all()
            for msg in unread:
                msg.is_read = True
            db.session.commit()
            
            # Get messages with pagination (default last 100)
            limit = request.args.get('limit', 100, type=int)
            offset = request.args.get('offset', 0, type=int)
            
            messages = Message.query.filter(
                ((Message.sender_id == current_user.id) & (Message.receiver_id == contact.id)) |
                ((Message.sender_id == contact.id) & (Message.receiver_id == current_user.id))
            ).order_by(Message.timestamp.desc()).limit(limit).offset(offset).all()
            
            # Reverse to show oldest first
            messages = list(reversed(messages))
            
            return jsonify([{
                'id': m.id,
                'content': 'This message was deleted' if m.is_deleted else m.content,
                'sender_id': m.sender.user_id,
                'timestamp': m.timestamp.isoformat() if m.timestamp else None,
                'is_read': m.is_read,
                'is_mine': m.sender_id == current_user.id,
                'is_deleted': m.is_deleted,
                'edited_at': m.edited_at.isoformat() if m.edited_at else None,
                'reply_to': {
                    'id': m.reply_to.id,
                    'content': m.reply_to.content[:50] + '...' if m.reply_to and len(m.reply_to.content) > 50 else (m.reply_to.content if m.reply_to else None)
                } if m.reply_to else None
            } for m in messages])
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Get messages error: {str(e)}")
            return jsonify({'error': 'Failed to load messages'}), 500
    
    @app.route('/api/messages/<int:message_id>/edit', methods=['PUT'])
    @login_required
    def edit_message(message_id):
        try:
            msg = Message.query.get_or_404(message_id)
            
            if msg.sender_id != current_user.id:
                return jsonify({'error': 'Cannot edit others messages'}), 403
            
            if msg.is_deleted:
                return jsonify({'error': 'Cannot edit deleted message'}), 400
            
            data = request.get_json() or {}
            new_content = data.get('content', '').strip()
            
            err = validate_message_content(new_content)
            if err:
                return jsonify({'error': err}), 400
            
            msg.content = new_content
            msg.edited_at = datetime.utcnow()
            db.session.commit()
            
            # FIX: Emit to both sender and receiver
            receiver = User.query.get(msg.receiver_id)
            sender = User.query.get(msg.sender_id)
            
            event_data = {
                'id': msg.id,
                'content': msg.content,
                'edited_at': msg.edited_at.isoformat()
            }
            
            emit('message_edited', event_data, room=f"user_{receiver.id}", namespace='/')
            emit('message_edited', event_data, room=f"user_{sender.id}", namespace='/')
            
            logger.info(f"Message {message_id} edited by {current_user.username}")
            
            return jsonify({'message': 'Edited successfully'})
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Edit message error: {str(e)}")
            return jsonify({'error': 'Edit failed'}), 500
    
    @app.route('/api/messages/<int:message_id>', methods=['DELETE'])
    @login_required
    def delete_message(message_id):
        try:
            msg = Message.query.get_or_404(message_id)
            
            if msg.sender_id != current_user.id:
                return jsonify({'error': 'Cannot delete others messages'}), 403
            
            msg.is_deleted = True
            db.session.commit()
            
            # FIX: Emit to both sender and receiver
            receiver = User.query.get(msg.receiver_id)
            sender = User.query.get(msg.sender_id)
            
            event_data = {'id': msg.id}
            
            emit('message_deleted', event_data, room=f"user_{receiver.id}", namespace='/')
            emit('message_deleted', event_data, room=f"user_{sender.id}", namespace='/')
            
            logger.info(f"Message {message_id} deleted by {current_user.username}")
            
            return jsonify({'message': 'Deleted successfully'})
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Delete message error: {str(e)}")
            return jsonify({'error': 'Delete failed'}), 500
    
    # ==================== WEBSOCKET ====================
    
    @socketio.on('connect')
    def handle_connect():
        if current_user.is_authenticated:
            join_room(f"user_{current_user.id}")
            logger.info(f"User {current_user.username} connected (Socket ID: {request.sid})")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        if current_user.is_authenticated:
            leave_room(f"user_{current_user.id}")
            logger.info(f"User {current_user.username} disconnected")
    
    @socketio.on('send_message')
    @login_required
    def handle_message(data):
        try:
            receiver_user_id = data.get('receiver_id')
            content = data.get('content', '').strip()
            reply_to_id = data.get('reply_to_id')
            
            # Validation
            err = validate_message_content(content)
            if err:
                emit('error', {'message': err})
                return
            
            receiver = User.query.filter_by(user_id=receiver_user_id).first()
            if not receiver:
                emit('error', {'message': 'Receiver not found'})
                return
            
            # Verify contact relationship exists
            contact_exists = Contact.query.filter_by(
                user_id=current_user.id,
                contact_id=receiver.id
            ).first()
            
            if not contact_exists:
                emit('error', {'message': 'Not in contacts'})
                return
            
            # Validate reply_to
            reply_msg = None
            if reply_to_id:
                reply_msg = Message.query.get(reply_to_id)
                if not reply_msg or reply_msg.is_deleted:
                    reply_msg = None
                elif reply_msg.sender_id not in [current_user.id, receiver.id] or \
                     reply_msg.receiver_id not in [current_user.id, receiver.id]:
                    # Security: Ensure replied message belongs to this conversation
                    reply_msg = None
            
            msg = Message(
                sender_id=current_user.id,
                receiver_id=receiver.id,
                content=content,
                reply_to_id=reply_msg.id if reply_msg else None
            )
            db.session.add(msg)
            db.session.commit()
            
            message_data = {
                'id': msg.id,
                'content': msg.content,
                'sender_id': current_user.user_id,
                'sender_name': current_user.display_name,
                'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                'is_read': False,
                'reply_to': {
                    'id': reply_msg.id,
                    'content': reply_msg.content[:50] + '...' if len(reply_msg.content) > 50 else reply_msg.content
                } if reply_msg else None
            }
            
            emit('new_message', message_data, room=f"user_{receiver.id}")
            emit('message_sent', {**message_data, 'is_mine': True}, room=f"user_{current_user.id}")
            
            logger.info(f"Message sent from {current_user.username} to {receiver.username}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Send message error: {str(e)}")
            emit('error', {'message': 'Failed to send message'})
    
    @socketio.on('typing')
    @login_required
    def handle_typing(data):
        try:
            receiver_user_id = data.get('receiver_id')
            receiver = User.query.filter_by(user_id=receiver_user_id).first()
            if receiver:
                emit('user_typing', {
                    'user_id': current_user.user_id,
                    'display_name': current_user.display_name
                }, room=f"user_{receiver.id}")
        except Exception as e:
            logger.error(f"Typing indicator error: {str(e)}")
    
    return app, socketio

app, socketio = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
