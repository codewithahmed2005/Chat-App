from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import uuid

db = SQLAlchemy()

def generate_user_id():
    """Generate a unique 10-digit user ID."""
    return str(uuid.uuid4().int)[:10]

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(10), unique=True, nullable=False, default=generate_user_id)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(100))
    about = db.Column(db.String(500), default='Hey there! I am using ChatApp.')
    profile_pic = db.Column(db.String(200), default='default.png')
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    
    # Relationships
    contacts = db.relationship('Contact', foreign_keys='Contact.user_id', backref='owner', lazy='dynamic')
    messages_sent = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    messages_received = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy='dynamic')

class Contact(db.Model):
    __tablename__ = 'contact'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    nickname = db.Column(db.String(100))
    added_at = db.Column(db.DateTime, server_default=db.func.now())
    
    contact_user = db.relationship('User', foreign_keys=[contact_id], lazy='joined')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'contact_id', name='uix_user_contact'),
        db.Index('idx_contact_user', 'user_id'),
    )

class Message(db.Model):
    __tablename__ = 'message'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    is_read = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    edited_at = db.Column(db.DateTime, nullable=True)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('message.id'), nullable=True)
    
    reply_to = db.relationship('Message', remote_side=[id], backref='replies', lazy='joined')
    
    __table_args__ = (
        db.Index('idx_message_conversation', 'sender_id', 'receiver_id'),
        db.Index('idx_message_timestamp', 'timestamp'),
        db.Index('idx_message_unread', 'receiver_id', 'is_read'),
    )
