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
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")

CORS(app, supports_credentials=True)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)


# =========================
# PATH CONFIG
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Local: backend folder
# Render with persistent disk: DATA_DIR=/var/data
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = os.path.join(DATA_DIR, "userchat.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

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


# =========================
# BASIC HELPERS
# =========================

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

    # Make sure old/incomplete JSON has all keys
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        db = default_db()

    changed = False

    for key in ["users", "contacts", "messages", "settings"]:
        if key not in db:
            db[key] = []
            changed = True

    # Make sure old messages have required fields
    for msg in db["messages"]:
        if "deleted_for" not in msg:
            msg["deleted_for"] = []
            changed = True

        if "edited" not in msg:
            msg["edited"] = False
            changed = True

        if "deleted" not in msg:
            msg["deleted"] = False
            changed = True

        if "updated_at" not in msg:
            msg["updated_at"] = None
            changed = True

    if changed:
        write_db(db)


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
        "chat_id": str(user["chat_id"]),
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


# =========================
# NUMERIC USER ID SYSTEM
# =========================

def generate_chat_id(db):
    while True:
        # 10 digit numeric ID
        # Example: 8459210374
        chat_id = str(secrets.randbelow(9000000000) + 1000000000)

        exists = any(str(u["chat_id"]) == chat_id for u in db["users"])

        if not exists:
            return chat_id


def migrate_old_ids_to_numeric():
    """
    Old IDs like ID12345678 will be changed to numeric IDs.
    Contacts, messages and settings will also be updated.
    """

    with DB_LOCK:
        db = read_db()
        mapping = {}

        for user in db["users"]:
            old_id = str(user["chat_id"])

            # Already numeric, skip
            if old_id.isdigit():
                user["chat_id"] = old_id
                continue

            new_id = generate_chat_id(db)

            mapping[old_id] = new_id
            user["chat_id"] = new_id

        if not mapping:
            write_db(db)
            return

        # Update contacts
        for contact in db["contacts"]:
            old_user_chat_id = str(contact.get("user_chat_id", ""))
            old_contact_chat_id = str(contact.get("contact_chat_id", ""))

            if old_user_chat_id in mapping:
                contact["user_chat_id"] = mapping[old_user_chat_id]

            if old_contact_chat_id in mapping:
                contact["contact_chat_id"] = mapping[old_contact_chat_id]

        # Update messages
        for msg in db["messages"]:
            old_sender = str(msg.get("sender_id", ""))
            old_receiver = str(msg.get("receiver_id", ""))

            if old_sender in mapping:
                msg["sender_id"] = mapping[old_sender]

            if old_receiver in mapping:
                msg["receiver_id"] = mapping[old_receiver]

            if "deleted_for" in msg:
                msg["deleted_for"] = [
                    mapping.get(str(user_id), str(user_id))
                    for user_id in msg["deleted_for"]
                ]

        # Update settings
        for setting in db["settings"]:
            old_setting_id = str(setting.get("chat_id", ""))

            if old_setting_id in mapping:
                setting["chat_id"] = mapping[old_setting_id]

        write_db(db)

        print("Old alphabet IDs migrated to numeric IDs:")
        print(mapping)


def generate_msg_id():
    return "MSG" + uuid.uuid4().hex[:12].upper()


def find_user_by_chat_id(db, chat_id):
    chat_id = str(chat_id).strip()

    for user in db["users"]:
        if str(user["chat_id"]) == chat_id:
            return user

    return None


def conversation_messages(db, user1, user2):
    user1 = str(user1)
    user2 = str(user2)

    result = []

    for msg in db["messages"]:
        if user1 in msg.get("deleted_for", []):
            continue

        condition1 = str(msg["sender_id"]) == user1 and str(msg["receiver_id"]) == user2
        condition2 = str(msg["sender_id"]) == user2 and str(msg["receiver_id"]) == user1

        if condition1 or condition2:
            result.append(msg)

    result.sort(key=lambda x: x.get("created_at", ""))
    return result


def create_message(db, sender_id, receiver_id, msg_type="text", text="", file_url=None, reply_to=None):
    msg = {
        "id": generate_msg_id(),
        "sender_id": str(sender_id),
        "receiver_id": str(receiver_id),
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


# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    return jsonify({
        "message": "Backend is running",
        "database": DB_FILE,
        "uploads": UPLOAD_DIR
    })


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}

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
    data = request.get_json() or {}

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

    data = request.get_json() or {}

    name = data.get("name", "").strip()
    username = data.get("username", "").strip().lower()
    about = data.get("about", "").strip()

    if not name or not username:
        return jsonify({"error": "Name and username are required"}), 400

    with DB_LOCK:
        db = read_db()
        db_user = find_user_by_chat_id(db, user["chat_id"])

        if not db_user:
            return jsonify({"error": "User not found"}), 404

        for u in db["users"]:
            if u["username"] == username and str(u["chat_id"]) != str(db_user["chat_id"]):
                return jsonify({"error": "Username already taken"}), 400

        db_user["name"] = name
        db_user["username"] = username
        db_user["about"] = about

        write_db(db)

    return jsonify({
        "message": "Profile updated",
        "user": public_user(db_user)
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

    filename = secure_filename(str(user["chat_id"]) + "_" + uuid.uuid4().hex + ext)

    path = os.path.join(UPLOAD_FOLDERS["profiles"], filename)
    file.save(path)

    file_url = f"/uploads/profiles/{filename}"

    with DB_LOCK:
        db = read_db()
        db_user = find_user_by_chat_id(db, user["chat_id"])

        if not db_user:
            return jsonify({"error": "User not found"}), 404

        old_image = db_user.get("profile_image")
        db_user["profile_image"] = file_url

        write_db(db)

    # Optional: delete old DP file
    if old_image:
        try:
            relative_path = old_image.replace("/uploads/", "")
            old_file_path = os.path.join(UPLOAD_DIR, relative_path)

            if os.path.exists(old_file_path):
                os.remove(old_file_path)
        except Exception as e:
            print("Could not delete old profile image:", e)

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
        db_user["profile_image"] = None

        write_db(db)

    if old_image:
        try:
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

    data = request.get_json() or {}
    contact_id = str(data.get("chat_id", "")).strip()

    if not contact_id:
        return jsonify({"error": "Contact ID is required"}), 400

    if not contact_id.isdigit():
        return jsonify({"error": "User ID must contain numbers only"}), 400

    with DB_LOCK:
        db = read_db()

        db_user = find_user_by_chat_id(db, user["chat_id"])

        if not db_user:
            return jsonify({"error": "User not found"}), 404

        if contact_id == str(db_user["chat_id"]):
            return jsonify({"error": "You cannot add yourself"}), 400

        contact_user = find_user_by_chat_id(db, contact_id)

        if not contact_user:
            return jsonify({"error": "User not found"}), 404

        exists = any(
            str(c["user_chat_id"]) == str(db_user["chat_id"]) and str(c["contact_chat_id"]) == contact_id
            for c in db["contacts"]
        )

        if exists:
            return jsonify({"error": "Contact already added"}), 400

        db["contacts"].append({
            "user_chat_id": str(db_user["chat_id"]),
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
        if str(contact["user_chat_id"]) == str(user["chat_id"]):
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

    contact_id = str(contact_id).strip()

    if not contact_id.isdigit():
        return jsonify({"error": "User ID must contain numbers only"}), 400

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

    data = request.get_json() or {}

    receiver_id = str(data.get("receiver_id", "")).strip()
    msg_type = data.get("type", "text")
    text = data.get("text", "")
    file_url = data.get("file_url")
    reply_to = data.get("reply_to")

    if not receiver_id:
        return jsonify({"error": "Receiver ID is required"}), 400

    if not receiver_id.isdigit():
        return jsonify({"error": "Receiver ID must contain numbers only"}), 400

    with DB_LOCK:
        db = read_db()

        receiver = find_user_by_chat_id(db, receiver_id)

        if not receiver:
            return jsonify({"error": "Receiver not found"}), 404

        msg = create_message(
            db,
            user["chat_id"],
            receiver_id,
            msg_type,
            text,
            file_url,
            reply_to
        )

        write_db(db)

    socketio.emit("receive_message", msg, room=str(user["chat_id"]))
    socketio.emit("receive_message", msg, room=receiver_id)

    return jsonify(msg)


@app.route("/api/messages/<message_id>/edit", methods=["PUT"])
def edit_message(message_id):
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json() or {}
    new_text = data.get("text", "").strip()

    if not new_text:
        return jsonify({"error": "Text is required"}), 400

    with DB_LOCK:
        db = read_db()

        msg = next((m for m in db["messages"] if m["id"] == message_id), None)

        if not msg:
            return jsonify({"error": "Message not found"}), 404

        if str(msg["sender_id"]) != str(user["chat_id"]):
            return jsonify({"error": "You can edit only your own message"}), 403

        if msg.get("deleted"):
            return jsonify({"error": "Cannot edit deleted message"}), 400

        if msg["type"] != "text":
            return jsonify({"error": "Only text messages can be edited"}), 400

        msg["text"] = new_text
        msg["edited"] = True
        msg["updated_at"] = now()

        write_db(db)

    socketio.emit("message_edited", msg, room=str(msg["sender_id"]))
    socketio.emit("message_edited", msg, room=str(msg["receiver_id"]))

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
            if str(user["chat_id"]) not in msg.get("deleted_for", []):
                msg["deleted_for"].append(str(user["chat_id"]))
        else:
            if str(msg["sender_id"]) != str(user["chat_id"]):
                return jsonify({"error": "Only sender can delete for everyone"}), 403

            msg["deleted"] = True
            msg["text"] = "This message was deleted"
            msg["file_url"] = None
            msg["updated_at"] = now()

        write_db(db)

    socketio.emit("message_deleted", msg, room=str(msg["sender_id"]))
    socketio.emit("message_deleted", msg, room=str(msg["receiver_id"]))

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

    allowed = {
        "images": [".jpg", ".jpeg", ".png", ".webp", ".gif"],
        "videos": [".mp4", ".webm", ".mov", ".mkv"],
        "voice": [".webm", ".mp3", ".wav", ".ogg", ".m4a"]
    }

    if ext not in allowed[kind]:
        return jsonify({"error": f"Invalid {kind} file type"}), 400

    filename = secure_filename(str(user["chat_id"]) + "_" + uuid.uuid4().hex + ext)

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

    setting = next(
        (s for s in db["settings"] if str(s["chat_id"]) == str(user["chat_id"])),
        None
    )

    if not setting:
        setting = {
            "chat_id": str(user["chat_id"]),
            "theme": "light"
        }

    return jsonify(setting)


@app.route("/api/settings/theme", methods=["PUT"])
def update_theme():
    db, user, error, status = require_auth()

    if error:
        return error, status

    data = request.get_json() or {}
    theme = data.get("theme", "light")

    allowed_themes = ["light", "dark", "green", "blue"]

    if theme not in allowed_themes:
        return jsonify({"error": "Invalid theme"}), 400

    with DB_LOCK:
        db = read_db()

        setting = next(
            (s for s in db["settings"] if str(s["chat_id"]) == str(user["chat_id"])),
            None
        )

        if not setting:
            db["settings"].append({
                "chat_id": str(user["chat_id"]),
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
        chat_id = str(user["chat_id"])

        db["users"] = [
            u for u in db["users"]
            if str(u["chat_id"]) != chat_id
        ]

        db["contacts"] = [
            c for c in db["contacts"]
            if str(c["user_chat_id"]) != chat_id and str(c["contact_chat_id"]) != chat_id
        ]

        db["messages"] = [
            m for m in db["messages"]
            if str(m["sender_id"]) != chat_id and str(m["receiver_id"]) != chat_id
        ]

        db["settings"] = [
            s for s in db["settings"]
            if str(s["chat_id"]) != chat_id
        ]

        write_db(db)

    return jsonify({
        "message": "Account deleted successfully"
    })


# =========================
# SOCKET.IO EVENTS
# =========================

@socketio.on("connect")
def socket_connect(auth):
    token = None

    if auth:
        token = auth.get("token")

    db = read_db()
    user = find_user_by_token(db, token)

    if not user:
        return False

    chat_id = str(user["chat_id"])

    SID_USERS[request.sid] = chat_id
    join_room(chat_id)

    emit("connected", {
        "message": "Connected",
        "chat_id": chat_id
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

    data = data or {}

    receiver_id = str(data.get("receiver_id", "")).strip()
    msg_type = data.get("type", "text")
    text = data.get("text", "")
    file_url = data.get("file_url")
    reply_to = data.get("reply_to")

    if not receiver_id:
        emit("error_message", {"error": "Receiver ID is required"})
        return

    if not receiver_id.isdigit():
        emit("error_message", {"error": "Receiver ID must contain numbers only"})
        return

    with DB_LOCK:
        db = read_db()

        receiver = find_user_by_chat_id(db, receiver_id)

        if not receiver:
            emit("error_message", {"error": "Receiver not found"})
            return

        msg = create_message(
            db,
            sender_id,
            receiver_id,
            msg_type,
            text,
            file_url,
            reply_to
        )

        write_db(db)

    socketio.emit("receive_message", msg, room=str(sender_id))
    socketio.emit("receive_message", msg, room=str(receiver_id))


# =========================
# INIT FOR LOCAL + GUNICORN
# =========================

init_db()
migrate_old_ids_to_numeric()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print(f"Backend running on http://0.0.0.0:{port}")

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=True,
        allow_unsafe_werkzeug=True
    )
