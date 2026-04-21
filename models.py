from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import uuid

db = SQLAlchemy()

def generate_user_id():
    """Generate a unique 10-digit ID like a phone number"""
    return str(uuid.uuid4().int)[:10]

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(10), unique=True, default=generate_user_id)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100))
    profile_pic = db.Column(db.String(200), default='default.png')
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Relationships
    contacts = db.relationship('Contact', foreign_keys='Contact.user_id', backref='owner')
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender')
    messages_received = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver')

class Contact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nickname = db.Column(db.String(100))
    added_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Relationship to the actual user
    contact_user = db.relationship('User', foreign_keys=[contact_id])

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    is_read = db.Column(db.Boolean, default=False)