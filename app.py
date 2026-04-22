import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Contact, Message
import os
from datetime import datetime

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-dev-key-only')
    
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chatapp.db'
    
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
    
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')
    
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
            return redirect(url_for('app_page'))
        return redirect(url_for('login'))
    
    @app.route('/login')
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('app_page'))
        return render_template('login.html')
    
    @app.route('/register')
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('app_page'))
        return render_template('register.html')
    
    @app.route('/app')
    @login_required
    def app_page():
        return render_template('app.html')
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))
    
    # ==================== API AUTH ====================
    
    @app.route('/api/register', methods=['POST'])
    def api_register():
        data = request.get_json()
        
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': 'Username already exists'}), 400
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        user = User(
            username=data['username'],
            email=data['email'],
            password_hash=generate_password_hash(data['password']),
            display_name=data.get('display_name', data['username']),
            about='Hey there! I am using ChatApp.'
        )
        db.session.add(user)
        db.session.commit()
        
        return jsonify({
            'message': 'Account created!',
            'user_id': user.user_id,
            'username': user.username
        }), 201
    
    @app.route('/api/login', methods=['POST'])
    def api_login():
        data = request.get_json()
        user = User.query.filter_by(username=data['username']).first()
        
        if user and check_password_hash(user.password_hash, data['password']):
            login_user(user)
            return jsonify({
                'user_id': user.user_id,
                'display_name': user.display_name,
                'username': user.username
            }), 200
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # ==================== API USER / PROFILE ====================
    
    @app.route('/api/me')
    @login_required
    def get_me():
        return jsonify({
            'id': current_user.id,
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
        data = request.get_json()
        
        # Check username uniqueness if changed
        if data.get('username') and data['username'] != current_user.username:
            if User.query.filter_by(username=data['username']).first():
                return jsonify({'error': 'Username already taken'}), 400
            current_user.username = data['username']
        
        # Update fields
        if data.get('display_name'):
            current_user.display_name = data['display_name']
        if data.get('about') is not None:
            current_user.about = data['about']
        if data.get('profile_pic'):
            current_user.profile_pic = data['profile_pic']
        
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated',
            'user_id': current_user.user_id,
            'username': current_user.username,
            'display_name': current_user.display_name,
            'about': current_user.about
        })
    
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
            data = request.get_json()
            target_user = User.query.filter_by(user_id=data.get('user_id')).first()
            
            if not target_user:
                return jsonify({'error': 'User not found'}), 404
            if target_user.id == current_user.id:
                return jsonify({'error': 'Cannot add yourself'}), 400
            
            existing = Contact.query.filter_by(
                user_id=current_user.id, 
                contact_id=target_user.id
            ).first()
            if existing:
                return jsonify({'error': 'Already in contacts'}), 400
            
            c1 = Contact(user_id=current_user.id, contact_id=target_user.id)
            c2 = Contact(user_id=target_user.id, contact_id=current_user.id)
            db.session.add_all([c1, c2])
            db.session.commit()
            
            last_msg = get_last_message(current_user.id, target_user.id)
            
            return jsonify({
                'user_id': target_user.user_id,
                'display_name': target_user.display_name,
                'username': target_user.username,
                'about': target_user.about,
                'last_message': last_msg
            }), 201
        
        user_contacts = Contact.query.filter_by(user_id=current_user.id).all()
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
        
        result.sort(key=lambda x: x['last_message']['timestamp'] if x['last_message'] else '', reverse=True)
        return jsonify(result)
    
    def get_last_message(user1_id, user2_id):
        msg = Message.query.filter(
            ((Message.sender_id == user1_id) & (Message.receiver_id == user2_id)) |
            ((Message.sender_id == user2_id) & (Message.receiver_id == user1_id)),
            Message.is_deleted == False
        ).order_by(Message.timestamp.desc()).first()
        
        if msg:
            return {
                'content': msg.content if not msg.is_deleted else 'This message was deleted',
                'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                'is_mine': msg.sender_id == user1_id
            }
        return None
    
    # ==================== API MESSAGES ====================
    
    @app.route('/api/messages/<contact_user_id>')
    @login_required
    def get_messages(contact_user_id):
        contact = User.query.filter_by(user_id=contact_user_id).first_or_404()
        
        unread = Message.query.filter_by(
            sender_id=contact.id,
            receiver_id=current_user.id,
            is_read=False
        ).all()
        for msg in unread:
            msg.is_read = True
        db.session.commit()
        
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == contact.id)) |
            ((Message.sender_id == contact.id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.timestamp.asc()).all()
        
        return jsonify([{
            'id': m.id,
            'content': 'This message was deleted' if m.is_deleted else m.content,
            'sender_id': User.query.get(m.sender_id).user_id,
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
    
    @app.route('/api/messages/<int:message_id>/edit', methods=['PUT'])
    @login_required
    def edit_message(message_id):
        msg = Message.query.get_or_404(message_id)
        
        if msg.sender_id != current_user.id:
            return jsonify({'error': 'Cannot edit others messages'}), 403
        
        if msg.is_deleted:
            return jsonify({'error': 'Cannot edit deleted message'}), 400
        
        data = request.get_json()
        new_content = data.get('content', '').strip()
        
        if not new_content:
            return jsonify({'error': 'Content required'}), 400
        
        msg.content = new_content
        msg.edited_at = datetime.utcnow()
        db.session.commit()
        
        receiver = User.query.get(msg.receiver_id)
        emit('message_edited', {
            'id': msg.id,
            'content': msg.content,
            'edited_at': msg.edited_at.isoformat()
        }, room=f"user_{receiver.id}", namespace='/')
        
        return jsonify({'message': 'Edited successfully'})
    
    @app.route('/api/messages/<int:message_id>', methods=['DELETE'])
    @login_required
    def delete_message(message_id):
        msg = Message.query.get_or_404(message_id)
        
        if msg.sender_id != current_user.id:
            return jsonify({'error': 'Cannot delete others messages'}), 403
        
        msg.is_deleted = True
        db.session.commit()
        
        receiver = User.query.get(msg.receiver_id)
        emit('message_deleted', {
            'id': msg.id
        }, room=f"user_{receiver.id}", namespace='/')
        
        return jsonify({'message': 'Deleted successfully'})
    
    # ==================== WEBSOCKET ====================
    
    @socketio.on('connect')
    def handle_connect():
        if current_user.is_authenticated:
            join_room(f"user_{current_user.id}")
            print(f"User {current_user.username} connected")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        if current_user.is_authenticated:
            leave_room(f"user_{current_user.id}")
    
    @socketio.on('send_message')
    @login_required
    def handle_message(data):
        receiver_user_id = data.get('receiver_id')
        content = data.get('content', '').strip()
        reply_to_id = data.get('reply_to_id')
        
        if not content:
            return
        
        receiver = User.query.filter_by(user_id=receiver_user_id).first()
        if not receiver:
            emit('error', {'message': 'Receiver not found'})
            return
        
        reply_msg = None
        if reply_to_id:
            reply_msg = Message.query.get(reply_to_id)
            if not reply_msg or reply_msg.is_deleted:
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
    
    return app, socketio

app, socketio = create_app()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
