from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

import os
import json
import uuid
import secrets
import threading
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"

CORS(app, supports_credentials=True)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "userchat.json")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

UPLOAD_FOLDERS = {
    "images": os.path.join(UPLOAD_DIR, "images"),
    "videos": os.path.join(UPLOAD_DIR, "videos"),
    "voice": os.path.join(UPLOAD_DIR, "voice"),
    "profiles": os.path.join(UPLOAD_DIR, "profiles")
}

DB_LOCK = threading.Lock()
SID_USERS = {}

for folder in UPLOAD_FOLDERS.values():
    os.makedirs(folder, exist_ok=True)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_db():
    return {
        "users": [],
        "contacts": [],
        "messages": [],
        "settings": []
    }


def init_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(default_db(), f, indent=4)


def read_db():
    init_db()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def write_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)


def public_user(user):
    if not user:
        return None

    return {
        "chat_id": user["chat_id"],
        "name": user["name"],
        "username": user["username"],
        "about": user.get("about", ""),
        "profile_image": user.get("profile_image"),
        "created_at": user.get("created_at")
    }


def get_auth_token():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.replace("Bearer ", "").strip()
    return None


def find_user_by_token(db, token):
    if not token:
        return None

    for user in db["users"]:
        if user.get("token") == token:
            return user

    return None


def current_user():
    token = get_auth_token()

    db = read_db()
    user = find_user_by_token(db, token)

    return db, user


def require_auth():
    db, user = current_user()

    if not user:
        return db, None, jsonify({"error": "Unauthorized"}), 401

    return db, user, None, None


def generate_chat_id(db):
    while True:
        chat_id = "ID" + str(secrets.randbelow(90000000) + 10000000)

        exists = any(u["chat_id"] == chat_id for u in db["users"])

        if not exists:
            return chat_id


def generate_msg_id():
    return "MSG" + uuid.uuid4().hex[:12].upper()


def find_user_by_chat_id(db, chat_id):
    for user in db["users"]:
        if user["chat_id"] == chat_id:
            return user
    return None


def conversation_messages(db, user1, user2):
    result = []

    for msg in db["messages"]:
        if user1 in msg.get("deleted_for", []):
            continue

        condition1 = msg["sender_id"] == user1 and msg["receiver_id"] == user2
        condition2 = msg["sender_id"] == user2 and msg["receiver_id"] == user1

        if condition1 or condition2:
            result.append(msg)

    result.sort(key=lambda x: x["created_at"])
    return result


def create_message(db, sender_id, receiver_id, msg_type="text", text="", file_url=None, reply_to=None):
    msg = {
        "id": generate_msg_id(),
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "type": msg_type,
        "text": text or "",
        "file_url": file_url,
        "reply_to": reply_to,
        "edited": False,
        "deleted": False,
        "deleted_for": [],
        "created_at": now(),
        "updated_at": None
    }

    db["messages"].append(msg)
    return msg


@app.route("/")
def home():
    return jsonify({"message": "Backend is running"})


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()

    name = data.get("name", "").strip()
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    if not name or not username or not password:
        return jsonify({"error": "Name, username and password are required"}), 400

    with DB_LOCK:
        db = read_db()

        if any(u["username"] == username for u in db["users"]):
            return jsonify({"error": "Username already exists"}), 400

        chat_id = generate_chat_id(db)
        token = secrets.token_urlsafe(32)

        user = {
            "chat_id": chat_id,
            "name": name,
            "username": username,
            "password_hash": generate_password_hash(password),
            "about": "Hey there! I am using IDChat.",
            "profile_image": None,
            "token": token,
            "created_at": now()
        }

        db["users"].append(user)

        db["settings"].append({
            "chat_id": chat_id,
            "theme": "light"
        })

        write_db(db)

    return jsonify({
        "message": "Account created successfully",
        "token": token,
        "user": public_user(user)
    })


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()

    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    with DB_LOCK:
        db = read_db()

        user = None

        for u in db["users"]:
            if u["username"] == username:
                user = u
                break

        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid username or password"}), 401

        token = secrets.token_urlsafe(32)
        user["token"] = token

        write_db(db)

    return jsonify({
        "message": "Login successful",
        "token": token,
        "user": public_user(user)
    })


@app.route("/api/me", methods=["GET"])
def me():
    db, user, error, status = require_auth()

    if error:
        return error, status

    return jsonify(public_user(user))


@app.route("/api/profile/update", methods=["PUT"])
def update_profile():
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json()

    name = data.get("name", "").strip()
    username = data.get("username", "").strip().lower()
    about = data.get("about", "").strip()

    if not name or not username:
        return jsonify({"error": "Name and username are required"}), 400

    with DB_LOCK:
        db = read_db()
        user = find_user_by_chat_id(db, user["chat_id"])

        for u in db["users"]:
            if u["username"] == username and u["chat_id"] != user["chat_id"]:
                return jsonify({"error": "Username already taken"}), 400

        user["name"] = name
        user["username"] = username
        user["about"] = about

        write_db(db)

    return jsonify({
        "message": "Profile updated",
        "user": public_user(user)
    })

@app.route("/api/upload/profile", methods=["POST"])
def upload_profile():
    db, user, error, status = require_auth()

    if error:
        return error, status

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    allowed_ext = [".jpg", ".jpeg", ".png", ".webp", ".gif"]
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in allowed_ext:
        return jsonify({"error": "Only image files are allowed"}), 400

    filename = secure_filename(user["chat_id"] + "_" + uuid.uuid4().hex + ext)

    path = os.path.join(UPLOAD_FOLDERS["profiles"], filename)
    file.save(path)

    file_url = f"/uploads/profiles/{filename}"

    with DB_LOCK:
        db = read_db()
        db_user = find_user_by_chat_id(db, user["chat_id"])

        if not db_user:
            return jsonify({"error": "User not found"}), 404

        db_user["profile_image"] = file_url
        write_db(db)

    return jsonify({
        "message": "Profile image uploaded",
        "file_url": file_url
    })

@app.route("/api/profile/remove-dp", methods=["DELETE"])
def remove_profile_dp():
    db, user, error, status = require_auth()

    if error:
        return error, status

    with DB_LOCK:
        db = read_db()
        db_user = find_user_by_chat_id(db, user["chat_id"])

        if not db_user:
            return jsonify({"error": "User not found"}), 404

        old_image = db_user.get("profile_image")

        # Remove DP from user data
        db_user["profile_image"] = None

        write_db(db)

    # Optional: delete old image file from uploads folder
    if old_image:
        try:
            # old_image example: /uploads/profiles/file.png
            relative_path = old_image.replace("/uploads/", "")
            file_path = os.path.join(UPLOAD_DIR, relative_path)

            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print("Could not delete old profile image:", e)

    return jsonify({
        "message": "Profile image removed"
    })

@app.route("/api/contacts/add", methods=["POST"])
def add_contact():
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json()
    contact_id = data.get("chat_id", "").strip()

    if not contact_id:
        return jsonify({"error": "Contact ID is required"}), 400

    with DB_LOCK:
        db = read_db()

        if contact_id == user["chat_id"]:
            return jsonify({"error": "You cannot add yourself"}), 400

        contact_user = find_user_by_chat_id(db, contact_id)

        if not contact_user:
            return jsonify({"error": "User not found"}), 404

        exists = any(
            c["user_chat_id"] == user["chat_id"] and c["contact_chat_id"] == contact_id
            for c in db["contacts"]
        )

        if exists:
            return jsonify({"error": "Contact already added"}), 400

        db["contacts"].append({
            "user_chat_id": user["chat_id"],
            "contact_chat_id": contact_id,
            "created_at": now()
        })

        write_db(db)

    return jsonify({
        "message": "Contact added",
        "contact": public_user(contact_user)
    })


@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    db, user, error, status = require_auth()

    if error:
        return error, status

    contacts = []

    for contact in db["contacts"]:
        if contact["user_chat_id"] == user["chat_id"]:
            contact_user = find_user_by_chat_id(db, contact["contact_chat_id"])

            if contact_user:
                msgs = conversation_messages(db, user["chat_id"], contact_user["chat_id"])
                last_msg = msgs[-1] if msgs else None

                contacts.append({
                    "user": public_user(contact_user),
                    "last_message": last_msg
                })

    return jsonify(contacts)


@app.route("/api/messages/<contact_id>", methods=["GET"])
def get_messages(contact_id):
    db, user, error, status = require_auth()

    if error:
        return error, status

    contact_user = find_user_by_chat_id(db, contact_id)

    if not contact_user:
        return jsonify({"error": "Contact not found"}), 404

    messages = conversation_messages(db, user["chat_id"], contact_id)

    return jsonify(messages)


@app.route("/api/messages/send", methods=["POST"])
def send_message_api():
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json()

    receiver_id = data.get("receiver_id")
    msg_type = data.get("type", "text")
    text = data.get("text", "")
    file_url = data.get("file_url")
    reply_to = data.get("reply_to")

    with DB_LOCK:
        db = read_db()

        receiver = find_user_by_chat_id(db, receiver_id)

        if not receiver:
            return jsonify({"error": "Receiver not found"}), 404

        msg = create_message(db, user["chat_id"], receiver_id, msg_type, text, file_url, reply_to)

        write_db(db)

    socketio.emit("receive_message", msg, room=user["chat_id"])
    socketio.emit("receive_message", msg, room=receiver_id)

    return jsonify(msg)


@app.route("/api/messages/<message_id>/edit", methods=["PUT"])
def edit_message(message_id):
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json()
    new_text = data.get("text", "").strip()

    if not new_text:
        return jsonify({"error": "Text is required"}), 400

    with DB_LOCK:
        db = read_db()

        msg = next((m for m in db["messages"] if m["id"] == message_id), None)

        if not msg:
            return jsonify({"error": "Message not found"}), 404

        if msg["sender_id"] != user["chat_id"]:
            return jsonify({"error": "You can edit only your own message"}), 403

        if msg["deleted"]:
            return jsonify({"error": "Cannot edit deleted message"}), 400

        if msg["type"] != "text":
            return jsonify({"error": "Only text messages can be edited"}), 400

        msg["text"] = new_text
        msg["edited"] = True
        msg["updated_at"] = now()

        write_db(db)

    socketio.emit("message_edited", msg, room=msg["sender_id"])
    socketio.emit("message_edited", msg, room=msg["receiver_id"])

    return jsonify(msg)


@app.route("/api/messages/<message_id>/delete", methods=["DELETE"])
def delete_message(message_id):
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "everyone")

    with DB_LOCK:
        db = read_db()

        msg = next((m for m in db["messages"] if m["id"] == message_id), None)

        if not msg:
            return jsonify({"error": "Message not found"}), 404

        if mode == "me":
            if user["chat_id"] not in msg["deleted_for"]:
                msg["deleted_for"].append(user["chat_id"])
        else:
            if msg["sender_id"] != user["chat_id"]:
                return jsonify({"error": "Only sender can delete for everyone"}), 403

            msg["deleted"] = True
            msg["text"] = "This message was deleted"
            msg["file_url"] = None
            msg["updated_at"] = now()

        write_db(db)

    socketio.emit("message_deleted", msg, room=msg["sender_id"])
    socketio.emit("message_deleted", msg, room=msg["receiver_id"])

    return jsonify({
        "message": "Message deleted",
        "data": msg
    })


@app.route("/api/upload/<kind>", methods=["POST"])
def upload_file(kind):
    db, user, error, status = require_auth()

    if error:
        return error, status

    if kind not in ["images", "videos", "voice"]:
        return jsonify({"error": "Invalid upload type"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    filename = secure_filename(user["chat_id"] + "_" + uuid.uuid4().hex + ext)

    path = os.path.join(UPLOAD_FOLDERS[kind], filename)
    file.save(path)

    file_url = f"/uploads/{kind}/{filename}"

    return jsonify({
        "message": "File uploaded",
        "file_url": file_url
    })


@app.route("/api/settings", methods=["GET"])
def get_settings():
    db, user, error, status = require_auth()

    if error:
        return error, status

    setting = next((s for s in db["settings"] if s["chat_id"] == user["chat_id"]), None)

    if not setting:
        setting = {
            "chat_id": user["chat_id"],
            "theme": "light"
        }

    return jsonify(setting)


@app.route("/api/settings/theme", methods=["PUT"])
def update_theme():
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json()
    theme = data.get("theme", "light")

    with DB_LOCK:
        db = read_db()

        setting = next((s for s in db["settings"] if s["chat_id"] == user["chat_id"]), None)

        if not setting:
            db["settings"].append({
                "chat_id": user["chat_id"],
                "theme": theme
            })
        else:
            setting["theme"] = theme

        write_db(db)

    return jsonify({
        "message": "Theme updated",
        "theme": theme
    })


@app.route("/api/account/delete", methods=["DELETE"])
def delete_account():
    db, user, error, status = require_auth()

    if error:
        return error, status

    with DB_LOCK:
        db = read_db()
        chat_id = user["chat_id"]

        db["users"] = [u for u in db["users"] if u["chat_id"] != chat_id]

        db["contacts"] = [
            c for c in db["contacts"]
            if c["user_chat_id"] != chat_id and c["contact_chat_id"] != chat_id
        ]

        db["messages"] = [
            m for m in db["messages"]
            if m["sender_id"] != chat_id and m["receiver_id"] != chat_id
        ]

        db["settings"] = [
            s for s in db["settings"]
            if s["chat_id"] != chat_id
        ]

        write_db(db)

    return jsonify({
        "message": "Account deleted successfully"
    })


@socketio.on("connect")
def socket_connect(auth):
    token = None

    if auth:
        token = auth.get("token")

    db = read_db()
    user = find_user_by_token(db, token)

    if not user:
        return False

    SID_USERS[request.sid] = user["chat_id"]
    join_room(user["chat_id"])

    emit("connected", {
        "message": "Connected",
        "chat_id": user["chat_id"]
    })


@socketio.on("disconnect")
def socket_disconnect():
    if request.sid in SID_USERS:
        del SID_USERS[request.sid]


@socketio.on("send_message")
def socket_send_message(data):
    sender_id = SID_USERS.get(request.sid)

    if not sender_id:
        return

    receiver_id = data.get("receiver_id")
    msg_type = data.get("type", "text")
    text = data.get("text", "")
    file_url = data.get("file_url")
    reply_to = data.get("reply_to")

    with DB_LOCK:
        db = read_db()

        receiver = find_user_by_chat_id(db, receiver_id)

        if not receiver:
            emit("error_message", {"error": "Receiver not found"})
            return

        msg = create_message(db, sender_id, receiver_id, msg_type, text, file_url, reply_to)

        write_db(db)

    socketio.emit("receive_message", msg, room=sender_id)
    socketio.emit("receive_message", msg, room=receiver_id)


if __name__ == "__main__":
    init_db()

    port = int(os.environ.get("PORT", 5000))

    print(f"Backend running on port {port}")

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )
