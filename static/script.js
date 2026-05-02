// socket connection
const socket = io('http://localhost:5000');

// global variables
let currentUserId = null;
let currentUsername = null;
let currentChatWith = null;
let friendsList = [];
let currentMessages = [];
let typingTimeout = null;
let isDarkMode = false;
let currentProfileData = {};

// ============ PAGE SWITCHING ============

function showLogin() {
    document.getElementById('register-page').classList.add('hidden');
    document.getElementById('login-page').classList.remove('hidden');
}

function showRegister() {
    document.getElementById('login-page').classList.add('hidden');
    document.getElementById('register-page').classList.remove('hidden');
}

// ============ PASSWORD TOGGLE ============

function togglePassword(inputId) {
    let input = document.getElementById(inputId);
    if (input.type === 'password') {
        input.type = 'text';
    } else {
        input.type = 'password';
    }
}

// ============ DARK MODE ============

function toggleDarkMode() {
    isDarkMode = !isDarkMode;
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
        document.getElementById('dark-mode-btn').innerHTML = '☀️ Light';
    } else {
        document.body.classList.remove('dark-mode');
        document.getElementById('dark-mode-btn').innerHTML = '🌙 Dark';
    }
    
    if (currentUserId) {
        fetch('/toggle_dark_mode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({user_id: currentUserId, dark_mode: isDarkMode})
        });
    }
}

// ============ REGISTER FUNCTION ============

function register() {
    let username = document.getElementById('reg-username').value;
    let fullname = document.getElementById('reg-fullname').value;
    let password = document.getElementById('reg-password').value;
    let confirmPassword = document.getElementById('reg-confirm-password').value;
    
    if(!username || !fullname || !password) {
        document.getElementById('reg-result').innerHTML = '❌ Please fill all fields';
        return;
    }
    
    if(password !== confirmPassword) {
        document.getElementById('reg-result').innerHTML = '❌ Passwords do not match';
        return;
    }
    
    if(password.length < 4) {
        document.getElementById('reg-result').innerHTML = '❌ Password must be at least 4 characters';
        return;
    }
    
    fetch('/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            username: username,
            fullname: fullname,
            password: password
        })
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            document.getElementById('reg-result').innerHTML = 
                '✅ Registration successful!<br>Your User ID: <strong>' + data.user_id + '</strong><br>Please login.';
            document.getElementById('login-id').value = data.user_id;
            document.getElementById('reg-username').value = '';
            document.getElementById('reg-fullname').value = '';
            document.getElementById('reg-password').value = '';
            document.getElementById('reg-confirm-password').value = '';
            setTimeout(function() {
                showLogin();
            }, 2000);
        } else {
            document.getElementById('reg-result').innerHTML = '❌ ' + data.message;
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        document.getElementById('reg-result').innerHTML = '❌ Network error. Make sure server is running.';
    });
}

// ============ LOGIN FUNCTION ============

function login() {
    let userId = document.getElementById('login-id').value;
    let password = document.getElementById('login-password').value;
    
    if(!userId || !password) {
        document.getElementById('login-result').innerHTML = '❌ Please fill all fields';
        return;
    }
    
    fetch('/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, password: password})
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            currentUserId = data.user_id;
            currentUsername = data.username;
            isDarkMode = data.dark_mode === 1;
            
            if (isDarkMode) {
                document.body.classList.add('dark-mode');
                document.getElementById('dark-mode-btn').innerHTML = '☀️ Light';
            }
            
            document.getElementById('user-id').innerText = currentUserId;
            document.getElementById('user-username').innerText = currentUsername;
            
            // load profile pic
            if (data.profile_pic) {
                document.getElementById('header-profile-pic').src = data.profile_pic;
            }
            
            document.getElementById('login-page').classList.add('hidden');
            document.getElementById('app-section').classList.remove('hidden');
            
            socket.emit('join', {user_id: currentUserId});
            
            loadFriendRequests();
            loadFriends();
        } else {
            document.getElementById('login-result').innerHTML = '❌ Invalid User ID or Password';
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        document.getElementById('login-result').innerHTML = '❌ Network error. Make sure server is running.';
    });
}

function logout() {
    currentUserId = null;
    currentUsername = null;
    currentChatWith = null;
    
    document.getElementById('app-section').classList.add('hidden');
    document.getElementById('register-page').classList.remove('hidden');
    
    document.getElementById('login-id').value = '';
    document.getElementById('login-password').value = '';
    document.getElementById('login-result').innerHTML = '';
    document.getElementById('chat-panel').classList.add('hidden');
    document.getElementById('no-chat-selected').classList.remove('hidden');
}

// ============ PROFILE FUNCTIONS ============

function openProfileModal() {
    document.getElementById('profile-modal').classList.remove('hidden');
    
    fetch('/get_profile/' + currentUserId)
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            currentProfileData = data;
            
            document.getElementById('profile-user-id').value = data.user_id;
            document.getElementById('profile-username').value = data.username;
            document.getElementById('profile-fullname').value = data.fullname;
            
            let profilePic = document.getElementById('profile-pic-preview');
            let headerPic = document.getElementById('header-profile-pic');
            
            if (data.profile_pic) {
                profilePic.src = data.profile_pic;
                headerPic.src = data.profile_pic;
            } else {
                profilePic.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23667eea"%3E%3Cpath d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
                headerPic.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23ffffff"%3E%3Cpath d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
            }
        }
    });
}

function closeProfileModal() {
    document.getElementById('profile-modal').classList.add('hidden');
    document.getElementById('profile-result').innerHTML = '';
}

function uploadProfilePic() {
    let input = document.getElementById('profile-pic-input');
    input.onchange = function(e) {
        let file = e.target.files[0];
        if (!file) return;
        
        let reader = new FileReader();
        reader.onload = function(evt) {
            let base64 = evt.target.result.split(',')[1];
            document.getElementById('profile-pic-preview').src = evt.target.result;
            currentProfileData.profile_pic_base64 = base64;
        };
        reader.readAsDataURL(file);
    };
    input.click();
}

function removeProfilePic() {
    document.getElementById('profile-pic-preview').src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23667eea"%3E%3Cpath d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
    currentProfileData.profile_pic_base64 = '';
}

function saveProfile() {
    let newUsername = document.getElementById('profile-username').value;
    let newFullname = document.getElementById('profile-fullname').value;
    
    if (!newUsername || !newFullname) {
        document.getElementById('profile-result').innerHTML = '❌ Username and Full Name required';
        return;
    }
    
    let body = {
        user_id: currentUserId,
        username: newUsername,
        fullname: newFullname
    };
    
    if (currentProfileData.profile_pic_base64 !== undefined) {
        body.profile_pic = currentProfileData.profile_pic_base64;
        delete currentProfileData.profile_pic_base64;
    } else if (currentProfileData.profile_pic === null) {
        body.profile_pic = '';
    }
    
    fetch('/update_profile', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)
    })
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            currentUsername = data.username;
            document.getElementById('user-username').innerText = currentUsername;
            document.getElementById('profile-result').innerHTML = '✅ Profile updated!';
            
            // reload header profile pic
            if (currentProfileData.profile_pic_base64) {
                document.getElementById('header-profile-pic').src = document.getElementById('profile-pic-preview').src;
            }
            
            setTimeout(() => {
                closeProfileModal();
            }, 1500);
        } else {
            document.getElementById('profile-result').innerHTML = '❌ ' + data.message;
        }
    });
}

// ============ FRIEND FUNCTIONS ============

function searchUser() {
    let searchId = document.getElementById('search-id').value;
    
    if(!searchId) {
        document.getElementById('search-result').innerHTML = '❌ Please enter an ID';
        return;
    }
    
    if(searchId === currentUserId) {
        document.getElementById('search-result').innerHTML = '❌ You cannot add yourself!';
        return;
    }
    
    fetch('/search_user/' + searchId)
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            document.getElementById('search-result').innerHTML = 
                '✅ Found: ' + data.username + ' (' + data.user_id + ') ' +
                '<button onclick="sendFriendRequest(\'' + data.user_id + '\')">➕ Add Friend</button>';
        } else {
            document.getElementById('search-result').innerHTML = '❌ User not found';
        }
    });
}

function sendFriendRequest(toId) {
    fetch('/send_request', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({from_id: currentUserId, to_id: toId})
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            alert('✅ Friend request sent!');
            document.getElementById('search-result').innerHTML = '';
            document.getElementById('search-id').value = '';
        } else {
            alert('❌ ' + data.message);
        }
    });
}

function loadFriendRequests() {
    fetch('/get_requests/' + currentUserId)
    .then(res => res.json())
    .then(data => {
        if(data.requests && data.requests.length > 0) {
            document.getElementById('requests-section').classList.remove('hidden');
            let html = '';
            for(let i = 0; i < data.requests.length; i++) {
                let reqId = data.requests[i];
                html += '<div>' +
                            '<span>👤 ' + reqId + '</span>' +
                            '<button onclick="acceptRequest(\'' + reqId + '\')">Accept</button>' +
                        '</div>';
            }
            document.getElementById('requests-list').innerHTML = html;
        } else {
            document.getElementById('requests-section').classList.add('hidden');
        }
    });
}

function acceptRequest(fromId) {
    fetch('/accept_request', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({from_id: fromId, to_id: currentUserId})
    })
    .then(res => res.json())
    .then(function(data) {
        loadFriendRequests();
        loadFriends();
    });
}

function loadFriends() {
    fetch('/get_friends/' + currentUserId)
    .then(res => res.json())
    .then(data => {
        friendsList = data.friends;
        let html = '';
        if(friendsList.length === 0) {
            html = '<div class="empty-friends">No friends yet.<br>🔍 Search and add someone!</div>';
        } else {
            for(let i = 0; i < friendsList.length; i++) {
                let friendId = friendsList[i];
                html += '<div onclick="startChat(\'' + friendId + '\')">' +
                            '<span>👤</span> ' + friendId +
                        '</div>';
            }
        }
        document.getElementById('friends-list').innerHTML = html;
        document.getElementById('friend-count').innerHTML = '(' + friendsList.length + ')';
    });
}

// ============ FILE SHARING ============

function showFileMenu() {
    let menu = document.getElementById('file-menu');
    menu.classList.toggle('hidden');
}

function sendFile(fileType) {
    let input = document.getElementById('file-input');
    let acceptTypes = {
        'image': 'image/*',
        'video': 'video/*',
        'audio': 'audio/*',
        'document': '.pdf,.doc,.docx,.txt,.zip,.xlsx,.pptx'
    };
    input.accept = acceptTypes[fileType];
    
    input.onchange = function(e) {
        let file = e.target.files[0];
        if (!file) return;
        
        let reader = new FileReader();
        reader.onload = function(evt) {
            let base64 = evt.target.result.split(',')[1];
            
            socket.emit('private_message', {
                to_id: currentChatWith,
                from_id: currentUserId,
                content: file.name,
                message_type: fileType,
                file_data: base64,
                file_name: file.name,
                reply_to: null
            });
            
            let now = new Date();
            let timeString = now.getHours() + ':' + (now.getMinutes() < 10 ? '0' : '') + now.getMinutes();
            displayFileMessage(currentUserId, file.name, timeString, true, fileType, URL.createObjectURL(file));
        };
        reader.readAsDataURL(file);
    };
    input.click();
    
    document.getElementById('file-menu').classList.add('hidden');
}

function displayFileMessage(sender, fileName, timestamp, isMine, fileType, fileUrl) {
    let messagesDiv = document.getElementById('messages');
    
    let div = document.createElement('div');
    div.className = 'message ' + (isMine ? 'my-message' : 'friend-message');
    
    let innerHtml = '';
    if (fileType === 'image') {
        innerHtml = '<div class="file-message"><img src="' + fileUrl + '" style="max-width:200px;border-radius:10px" onclick="window.open(this.src)"></div>';
    } else if (fileType === 'video') {
        innerHtml = '<div class="file-message"><video controls style="max-width:250px"><source src="' + fileUrl + '"></video></div>';
    } else if (fileType === 'audio') {
        innerHtml = '<div class="file-message"><audio controls src="' + fileUrl + '"></audio></div>';
    } else {
        innerHtml = '<div class="file-message"><a href="' + fileUrl + '" download class="file-download">📄 ' + fileName + '</a></div>';
    }
    
    innerHtml += '<br><small>' + timestamp + '</small>';
    div.innerHTML = innerHtml;
    
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// ============ TYPING INDICATOR ============

function handleTyping() {
    if (!currentChatWith) return;
    
    socket.emit('typing', {
        to_id: currentChatWith,
        from_id: currentUserId,
        is_typing: true
    });
    
    if (typingTimeout) clearTimeout(typingTimeout);
    typingTimeout = setTimeout(function() {
        socket.emit('typing', {
            to_id: currentChatWith,
            from_id: currentUserId,
            is_typing: false
        });
    }, 1000);
}

// ============ CHAT FUNCTIONS ============

function startChat(friendId) {
    currentChatWith = friendId;
    currentMessages = [];
    
    document.getElementById('no-chat-selected').classList.add('hidden');
    document.getElementById('chat-panel').classList.remove('hidden');
    document.getElementById('chat-with').innerText = friendId;
    document.getElementById('messages').innerHTML = '';
    
    fetch('/get_messages/' + currentUserId + '/' + friendId)
    .then(res => res.json())
    .then(data => {
        let messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = '';
        if (data.messages) {
            for (let i = 0; i < data.messages.length; i++) {
                let msg = data.messages[i];
                if (!msg.is_deleted) {
                    let isMine = msg.from_id === currentUserId;
                    displayMessageFromData(msg, isMine);
                }
                currentMessages.push(msg);
            }
        }
    });
}

function sendPrivateMessage() {
    let msg = document.getElementById('message-input').value;
    
    if(!msg || !currentChatWith) return;
    
    socket.emit('private_message', {
        to_id: currentChatWith,
        from_id: currentUserId,
        content: msg,
        message_type: 'text',
        file_data: null,
        file_name: '',
        reply_to: null
    });
    
    let now = new Date();
    let timeString = now.getHours() + ':' + (now.getMinutes() < 10 ? '0' : '') + now.getMinutes();
    displayMessage(currentUserId, msg, timeString, true, 'text', null);
    document.getElementById('message-input').value = '';
    
    socket.emit('typing', {
        to_id: currentChatWith,
        from_id: currentUserId,
        is_typing: false
    });
}

function displayMessage(sender, content, timestamp, isMine, type, fileName) {
    let messagesDiv = document.getElementById('messages');
    
    let div = document.createElement('div');
    div.className = 'message ' + (isMine ? 'my-message' : 'friend-message');
    div.setAttribute('data-content', content);
    
    let innerHtml = '<strong>' + (isMine ? 'You' : sender) + ':</strong> ' + escapeHtml(content);
    innerHtml += '<br><small>' + timestamp + '</small>';
    
    if (isMine) {
        innerHtml = '<div class="message-actions"><span onclick="editMessage(this)">✏️</span><span onclick="deleteMessage(this)">🗑️</span></div>' + innerHtml;
    }
    
    div.innerHTML = innerHtml;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function displayMessageFromData(msg, isMine) {
    let messagesDiv = document.getElementById('messages');
    
    let div = document.createElement('div');
    div.className = 'message ' + (isMine ? 'my-message' : 'friend-message');
    div.setAttribute('data-message-id', msg.message_id);
    div.setAttribute('data-content', msg.content);
    
    let innerHtml = '';
    
    if (msg.message_type === 'image') {
        innerHtml = '<div class="file-message"><img src="' + msg.content + '" style="max-width:200px;border-radius:10px" onclick="window.open(this.src)"></div>';
    } else if (msg.message_type === 'video') {
        innerHtml = '<div class="file-message"><video controls style="max-width:250px"><source src="' + msg.content + '"></video></div>';
    } else if (msg.message_type === 'audio') {
        innerHtml = '<div class="file-message"><audio controls src="' + msg.content + '"></audio></div>';
    } else if (msg.message_type === 'document') {
        innerHtml = '<div class="file-message"><a href="' + msg.content + '" download class="file-download">📄 ' + msg.file_name + '</a></div>';
    } else {
        let content = msg.is_deleted ? '[Message deleted]' : escapeHtml(msg.content);
        innerHtml = '<strong>' + (isMine ? 'You' : msg.from_id) + ':</strong> ' + content;
        if (msg.is_edited) innerHtml += '<span class="edited-badge">(edited)</span>';
    }
    
    innerHtml += '<br><small>' + msg.timestamp + '</small>';
    
    if (isMine && !msg.is_deleted) {
        innerHtml = '<div class="message-actions"><span onclick="editMessage(this)">✏️</span><span onclick="deleteMessage(this)">🗑️</span></div>' + innerHtml;
    }
    
    div.innerHTML = innerHtml;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function escapeHtml(text) {
    if (!text) return '';
    let div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============ EDIT & DELETE MESSAGES ============

function editMessage(element) {
    let messageDiv = element.closest('.message');
    let oldContent = messageDiv.getAttribute('data-content');
    
    let editForm = document.createElement('div');
    editForm.className = 'message-edit-form';
    editForm.innerHTML = '<input type="text" id="edit-input" value="' + oldContent + '">' +
                         '<button onclick="saveEdit(this)">Save</button>' +
                         '<button onclick="cancelEdit(this)">Cancel</button>';
    
    let contentDiv = messageDiv.querySelector('strong')?.parentNode || messageDiv;
    let originalContent = contentDiv.innerHTML;
    
    contentDiv.innerHTML = '';
    contentDiv.appendChild(editForm);
}

function saveEdit(element) {
    let editForm = element.closest('.message-edit-form');
    let messageDiv = editForm.closest('.message');
    let newContent = editForm.querySelector('input').value;
    let messageId = messageDiv.getAttribute('data-message-id');
    
    socket.emit('edit_message', {
        message_id: messageId,
        new_content: newContent,
        user_id: currentUserId
    });
    
    let contentDiv = messageDiv.querySelector('strong')?.parentNode || messageDiv;
    contentDiv.innerHTML = '<strong>You:</strong> ' + escapeHtml(newContent) + '<span class="edited-badge">(edited)</span><br><small>' + 
                           (messageDiv.querySelector('small')?.innerText || '') + '</small>';
    messageDiv.setAttribute('data-content', newContent);
}

function cancelEdit(element) {
    let editForm = element.closest('.message-edit-form');
    let messageDiv = editForm.closest('.message');
    let oldContent = messageDiv.getAttribute('data-content');
    
    let contentDiv = messageDiv.querySelector('strong')?.parentNode || messageDiv;
    contentDiv.innerHTML = '<strong>You:</strong> ' + escapeHtml(oldContent) + '<br><small>' + 
                           (messageDiv.querySelector('small')?.innerText || '') + '</small>';
}

function deleteMessage(element) {
    if (!confirm('Delete this message?')) return;
    
    let messageDiv = element.closest('.message');
    let messageId = messageDiv.getAttribute('data-message-id');
    
    socket.emit('delete_message', {
        message_id: messageId,
        user_id: currentUserId,
        delete_for_everyone: true
    });
    
    messageDiv.style.opacity = '0.5';
    let contentDiv = messageDiv.querySelector('strong')?.parentNode || messageDiv;
    contentDiv.innerHTML = '<strong>You:</strong> [Message deleted]<br><small>' + 
                           (messageDiv.querySelector('small')?.innerText || '') + '</small>';
}

function handleKeyPress(event) {
    if(event.key === 'Enter') {
        sendPrivateMessage();
    }
}

// ============ SOCKET EVENTS ============

socket.on('private_message', function(data) {
    if(currentChatWith === data.from_id) {
        displayMessage(data.from_id, data.content, data.timestamp, false, data.message_type, data.file_name);
    }
});

socket.on('user_typing', function(data) {
    if (currentChatWith === data.from_id) {
        let indicator = document.getElementById('typing-indicator');
        if (data.is_typing) {
            indicator.classList.remove('hidden');
            setTimeout(function() {
                indicator.classList.add('hidden');
            }, 2000);
        } else {
            indicator.classList.add('hidden');
        }
    }
});

socket.on('message_edited', function(data) {
    let messages = document.querySelectorAll('.message');
    for (let msg of messages) {
        if (msg.getAttribute('data-message-id') === data.message_id) {
            let contentDiv = msg.querySelector('strong')?.parentNode || msg;
            let timestamp = msg.querySelector('small')?.innerText || '';
            contentDiv.innerHTML = '<strong>You:</strong> ' + escapeHtml(data.new_content) + '<span class="edited-badge">(edited)</span><br><small>' + timestamp + '</small>';
            msg.setAttribute('data-content', data.new_content);
            break;
        }
    }
});

socket.on('message_deleted', function(data) {
    let messages = document.querySelectorAll('.message');
    for (let msg of messages) {
        if (msg.getAttribute('data-message-id') === data.message_id) {
            let contentDiv = msg.querySelector('strong')?.parentNode || msg;
            let timestamp = msg.querySelector('small')?.innerText || '';
            contentDiv.innerHTML = '<strong>' + (msg.classList.contains('my-message') ? 'You:' : 'Friend:') + '</strong> [Message deleted]<br><small>' + timestamp + '</small>';
            break;
        }
    }
});

// ============ REFRESH FRIENDS LIST ============

function refreshFriendsList() {
    loadFriends();
    loadFriendRequests();
    // show notification
    let refreshBtn = document.querySelector('.refresh-btn');
    refreshBtn.style.transform = 'rotate(180deg)';
    setTimeout(() => {
        refreshBtn.style.transform = 'rotate(0deg)';
    }, 500);
}

// ============ REPLY TO MESSAGE ============

let currentReplyTo = null;

function openReplyModal(messageId, originalContent, senderName) {
    currentReplyTo = { messageId, originalContent, senderName };
    document.getElementById('reply-original-msg').innerHTML = `<strong>Replying to ${senderName}:</strong><br>${originalContent}`;
    document.getElementById('reply-input').value = '';
    document.getElementById('reply-modal').classList.remove('hidden');
}

function closeReplyModal() {
    document.getElementById('reply-modal').classList.add('hidden');
    currentReplyTo = null;
}

function sendReply() {
    let replyText = document.getElementById('reply-input').value;
    if (!replyText || !currentReplyTo) return;
    
    let replyContent = `📌 Replying to "${currentReplyTo.originalContent}": ${replyText}`;
    
    socket.emit('private_message', {
        to_id: currentChatWith,
        from_id: currentUserId,
        content: replyContent,
        message_type: 'text',
        file_data: null,
        file_name: '',
        reply_to: currentReplyTo.messageId
    });
    
    let now = new Date();
    let timeString = now.getHours() + ':' + (now.getMinutes() < 10 ? '0' : '') + now.getMinutes();
    displayMessage(currentUserId, replyContent, timeString, true, 'text', null);
    
    closeReplyModal();
}

// ============ THREE DOT MENU FOR MESSAGES ============

function showMessageOptions(event, messageId, content, isMine, senderName) {
    event.stopPropagation();
    
    // remove existing menu
    let existingMenu = document.querySelector('.message-options');
    if (existingMenu) existingMenu.remove();
    
    let menu = document.createElement('div');
    menu.className = 'message-options';
    
    if (isMine) {
        menu.innerHTML = `
            <div onclick="editMessageById('${messageId}', '${escapeHtml(content)}', this)">✏️ Edit</div>
            <div onclick="deleteMessageById('${messageId}', this)">🗑️ Delete</div>
            <div onclick="openReplyModal('${messageId}', '${escapeHtml(content)}', 'You')">↩️ Reply</div>
        `;
    } else {
        menu.innerHTML = `
            <div onclick="openReplyModal('${messageId}', '${escapeHtml(content)}', '${senderName}')">↩️ Reply</div>
        `;
    }
    
    let rect = event.target.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.top = rect.bottom + 5 + 'px';
    menu.style.left = rect.left + 'px';
    
    document.body.appendChild(menu);
    
    // click outside to close
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 100);
}

function editMessageById(messageId, oldContent, element) {
    let newContent = prompt('Edit your message:', oldContent);
    if (newContent && newContent !== oldContent) {
        socket.emit('edit_message', {
            message_id: messageId,
            new_content: newContent,
            user_id: currentUserId
        });
    }
    // close menu
    element.closest('.message-options').remove();
}

function deleteMessageById(messageId, element) {
    if (!confirm('Delete this message?')) return;
    
    socket.emit('delete_message', {
        message_id: messageId,
        user_id: currentUserId,
        delete_for_everyone: true
    });
    
    element.closest('.message-options').remove();
    
    // find and mark message as deleted
    let messages = document.querySelectorAll('.message');
    for (let msg of messages) {
        if (msg.getAttribute('data-message-id') === messageId) {
            let contentDiv = msg.querySelector('.message-content') || msg;
            contentDiv.innerHTML = '<em>[Message deleted]</em>';
            break;
        }
    }
}

// Update displayMessage function to include three dot menu
function displayMessage(sender, content, timestamp, isMine, type, fileName) {
    let messagesDiv = document.getElementById('messages');
    
    if(messagesDiv.children.length === 1 && messagesDiv.children[0].classList) {
        if(messagesDiv.children[0].classList.contains('welcome-message')) {
            messagesDiv.innerHTML = '';
        }
    }
    
    let div = document.createElement('div');
    div.className = 'message ' + (isMine ? 'my-message' : 'friend-message');
    div.setAttribute('data-content', content);
    
    // add three dot menu
    let menuHtml = `<span class="three-dot-menu" onclick="showMessageOptions(event, '${Date.now()}', '${escapeHtml(content)}', ${isMine}, '${sender}')">⋮</span>`;
    
    let innerHtml = '<div class="message-content"><strong>' + (isMine ? 'You' : sender) + ':</strong> ' + escapeHtml(content);
    innerHtml += '<br><small>' + timestamp + '</small></div>';
    
    div.innerHTML = menuHtml + innerHtml;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function displayMessageFromData(msg, isMine) {
    let messagesDiv = document.getElementById('messages');
    
    let div = document.createElement('div');
    div.className = 'message ' + (isMine ? 'my-message' : 'friend-message');
    div.setAttribute('data-message-id', msg.message_id);
    div.setAttribute('data-content', msg.content);
    
    // add three dot menu
    let menuHtml = `<span class="three-dot-menu" onclick="showMessageOptions(event, '${msg.message_id}', '${escapeHtml(msg.content)}', ${isMine}, '${msg.from_id}')">⋮</span>`;
    
    let innerHtml = '<div class="message-content">';
    
    if (msg.message_type === 'image') {
        innerHtml += '<div class="file-message"><img src="' + msg.content + '" style="max-width:200px;border-radius:10px" onclick="window.open(this.src)"></div>';
    } else if (msg.message_type === 'video') {
        innerHtml += '<div class="file-message"><video controls style="max-width:250px"><source src="' + msg.content + '"></video></div>';
    } else if (msg.message_type === 'audio') {
        innerHtml += '<div class="file-message"><audio controls src="' + msg.content + '"></audio></div>';
    } else if (msg.message_type === 'document') {
        innerHtml += '<div class="file-message"><a href="' + msg.content + '" download class="file-download">📄 ' + msg.file_name + '</a></div>';
    } else {
        let content = msg.is_deleted ? '[Message deleted]' : escapeHtml(msg.content);
        innerHtml += '<strong>' + (isMine ? 'You' : msg.from_id) + ':</strong> ' + content;
        if (msg.is_edited) innerHtml += '<span class="edited-badge">(edited)</span>';
    }
    
    innerHtml += '<br><small>' + msg.timestamp + '</small>';
    innerHtml += '</div>';
    
    div.innerHTML = menuHtml + innerHtml;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Update edit and delete socket handlers
socket.on('message_edited', function(data) {
    let messages = document.querySelectorAll('.message');
    for (let msg of messages) {
        if (msg.getAttribute('data-message-id') === data.message_id) {
            let contentDiv = msg.querySelector('.message-content');
            if (contentDiv) {
                let timestamp = contentDiv.querySelector('small')?.innerText || '';
                let sender = contentDiv.querySelector('strong')?.innerText || 'You:';
                contentDiv.innerHTML = sender + ' ' + escapeHtml(data.new_content) + '<span class="edited-badge">(edited)</span><br><small>' + timestamp + '</small>';
            }
            msg.setAttribute('data-content', data.new_content);
            break;
        }
    }
});

socket.on('message_deleted', function(data) {
    let messages = document.querySelectorAll('.message');
    for (let msg of messages) {
        if (msg.getAttribute('data-message-id') === data.message_id) {
            let contentDiv = msg.querySelector('.message-content');
            if (contentDiv) {
                let timestamp = contentDiv.querySelector('small')?.innerText || '';
                let sender = contentDiv.querySelector('strong')?.innerText || 'Someone:';
                contentDiv.innerHTML = sender + ' <em>[Message deleted]</em><br><small>' + timestamp + '</small>';
            }
            break;
        }
    }
});

socket.on('connect', function() {
    console.log('✅ Connected to server');
});

socket.on('disconnect', function() {
    console.log('❌ Disconnected from server');
});