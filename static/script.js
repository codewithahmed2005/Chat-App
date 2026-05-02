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
    const registerPage = document.getElementById('register-page');
    const loginPage = document.getElementById('login-page');
    if (registerPage) registerPage.classList.add('hidden');
    if (loginPage) loginPage.classList.remove('hidden');
}

function showRegister() {
    const loginPage = document.getElementById('login-page');
    const registerPage = document.getElementById('register-page');
    if (loginPage) loginPage.classList.add('hidden');
    if (registerPage) registerPage.classList.remove('hidden');
}

// ============ PASSWORD TOGGLE ============

function togglePassword(inputId) {
    let input = document.getElementById(inputId);
    if (input) {
        if (input.type === 'password') {
            input.type = 'text';
        } else {
            input.type = 'password';
        }
    }
}

// ============ DARK MODE ============

function toggleDarkMode() {
    isDarkMode = !isDarkMode;
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
        const darkBtn = document.getElementById('dark-mode-btn');
        if (darkBtn) darkBtn.innerHTML = '☀️';
    } else {
        document.body.classList.remove('dark-mode');
        const darkBtn = document.getElementById('dark-mode-btn');
        if (darkBtn) darkBtn.innerHTML = '🌙';
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
    let username = document.getElementById('reg-username')?.value || '';
    let fullname = document.getElementById('reg-fullname')?.value || '';
    let password = document.getElementById('reg-password')?.value || '';
    let confirmPassword = document.getElementById('reg-confirm-password')?.value || '';
    
    const regResult = document.getElementById('reg-result');
    
    if(!username || !fullname || !password) {
        if (regResult) regResult.innerHTML = '❌ Please fill all fields';
        return;
    }
    
    if(password !== confirmPassword) {
        if (regResult) regResult.innerHTML = '❌ Passwords do not match';
        return;
    }
    
    if(password.length < 4) {
        if (regResult) regResult.innerHTML = '❌ Password must be at least 4 characters';
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
            if (regResult) regResult.innerHTML = '✅ Registration successful!<br>Your User ID: <strong>' + data.user_id + '</strong><br>Please login.';
            const loginId = document.getElementById('login-id');
            if (loginId) loginId.value = data.user_id;
            
            // clear register form
            const regUsername = document.getElementById('reg-username');
            const regFullname = document.getElementById('reg-fullname');
            const regPassword = document.getElementById('reg-password');
            const regConfirm = document.getElementById('reg-confirm-password');
            if (regUsername) regUsername.value = '';
            if (regFullname) regFullname.value = '';
            if (regPassword) regPassword.value = '';
            if (regConfirm) regConfirm.value = '';
            
            setTimeout(function() {
                showLogin();
            }, 2000);
        } else {
            if (regResult) regResult.innerHTML = '❌ ' + data.message;
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        if (regResult) regResult.innerHTML = '❌ Network error. Make sure server is running.';
    });
}

// ============ LOGIN FUNCTION ============

function login() {
    let userId = document.getElementById('login-id')?.value || '';
    let password = document.getElementById('login-password')?.value || '';
    
    const loginResult = document.getElementById('login-result');
    
    if(!userId || !password) {
        if (loginResult) loginResult.innerHTML = '❌ Please fill all fields';
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
                const darkBtn = document.getElementById('dark-mode-btn');
                if (darkBtn) darkBtn.innerHTML = '☀️';
            }
            
            // set user info in header
            const userIdSpan = document.getElementById('user-id');
            const usernameSpan = document.getElementById('user-username');
            if (userIdSpan) userIdSpan.innerText = currentUserId;
            if (usernameSpan) usernameSpan.innerText = currentUsername;
            
            // load profile pic
            if (data.profile_pic) {
                const headerPic = document.getElementById('header-profile-pic');
                if (headerPic) headerPic.src = data.profile_pic;
            }
            
            const loginPage = document.getElementById('login-page');
            const appSection = document.getElementById('app-section');
            if (loginPage) loginPage.classList.add('hidden');
            if (appSection) appSection.classList.remove('hidden');
            
            socket.emit('join', {user_id: currentUserId});
            
            loadFriendRequests();
            loadFriends();
        } else {
            if (loginResult) loginResult.innerHTML = '❌ Invalid User ID or Password';
        }
    })
    .catch(function(error) {
        console.error('Error:', error);
        if (loginResult) loginResult.innerHTML = '❌ Network error. Make sure server is running.';
    });
}

function logout() {
    currentUserId = null;
    currentUsername = null;
    currentChatWith = null;
    
    const appSection = document.getElementById('app-section');
    const registerPage = document.getElementById('register-page');
    if (appSection) appSection.classList.add('hidden');
    if (registerPage) registerPage.classList.remove('hidden');
    
    const loginId = document.getElementById('login-id');
    const loginPassword = document.getElementById('login-password');
    const loginResult = document.getElementById('login-result');
    if (loginId) loginId.value = '';
    if (loginPassword) loginPassword.value = '';
    if (loginResult) loginResult.innerHTML = '';
    
    const chatPanel = document.getElementById('chat-panel');
    const noChatSelected = document.getElementById('no-chat-selected');
    if (chatPanel) chatPanel.classList.add('hidden');
    if (noChatSelected) noChatSelected.classList.remove('hidden');
    
    // also hide chat screen if visible
    const chatScreen = document.getElementById('chat-screen');
    const contactsScreen = document.getElementById('contacts-screen');
    if (chatScreen) chatScreen.classList.add('hidden');
    if (contactsScreen) contactsScreen.classList.remove('hidden');
}

// ============ REFRESH FRIENDS LIST ============

function refreshFriendsList() {
    loadFriends();
    loadFriendRequests();
    let refreshBtn = document.querySelector('.refresh-btn');
    if (refreshBtn) {
        refreshBtn.style.transform = 'rotate(180deg)';
        setTimeout(() => {
            refreshBtn.style.transform = 'rotate(0deg)';
        }, 500);
    }
}

// ============ PROFILE FUNCTIONS ============

function openProfileModal() {
    const modal = document.getElementById('profile-modal');
    if (modal) modal.classList.remove('hidden');
    
    fetch('/get_profile/' + currentUserId)
    .then(res => res.json())
    .then(data => {
        if (data.status === 'success') {
            currentProfileData = data;
            
            const profileUserId = document.getElementById('profile-user-id');
            const profileUsername = document.getElementById('profile-username');
            const profileFullname = document.getElementById('profile-fullname');
            const profilePicPreview = document.getElementById('profile-pic-preview');
            const headerPic = document.getElementById('header-profile-pic');
            
            if (profileUserId) profileUserId.value = data.user_id;
            if (profileUsername) profileUsername.value = data.username;
            if (profileFullname) profileFullname.value = data.fullname;
            
            if (data.profile_pic) {
                if (profilePicPreview) profilePicPreview.src = data.profile_pic;
                if (headerPic) headerPic.src = data.profile_pic;
            } else {
                if (profilePicPreview) profilePicPreview.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23667eea"%3E%3Cpath d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
                if (headerPic) headerPic.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23ffffff"%3E%3Cpath d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
            }
        }
    });
}

function closeProfileModal() {
    const modal = document.getElementById('profile-modal');
    if (modal) modal.classList.add('hidden');
    const profileResult = document.getElementById('profile-result');
    if (profileResult) profileResult.innerHTML = '';
}

function uploadProfilePic() {
    let input = document.getElementById('profile-pic-input');
    if (!input) return;
    
    input.onchange = function(e) {
        let file = e.target.files[0];
        if (!file) return;
        
        let reader = new FileReader();
        reader.onload = function(evt) {
            let base64 = evt.target.result.split(',')[1];
            const profilePicPreview = document.getElementById('profile-pic-preview');
            if (profilePicPreview) profilePicPreview.src = evt.target.result;
            currentProfileData.profile_pic_base64 = base64;
        };
        reader.readAsDataURL(file);
    };
    input.click();
}

function removeProfilePic() {
    const profilePicPreview = document.getElementById('profile-pic-preview');
    if (profilePicPreview) {
        profilePicPreview.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23667eea"%3E%3Cpath d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/%3E%3C/svg%3E';
    }
    currentProfileData.profile_pic_base64 = '';
}

function saveProfile() {
    let newUsername = document.getElementById('profile-username')?.value || '';
    let newFullname = document.getElementById('profile-fullname')?.value || '';
    
    const profileResult = document.getElementById('profile-result');
    
    if (!newUsername || !newFullname) {
        if (profileResult) profileResult.innerHTML = '❌ Username and Full Name required';
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
            const usernameSpan = document.getElementById('user-username');
            if (usernameSpan) usernameSpan.innerText = currentUsername;
            if (profileResult) profileResult.innerHTML = '✅ Profile updated!';
            
            if (currentProfileData.profile_pic_base64) {
                const headerPic = document.getElementById('header-profile-pic');
                const profilePicPreview = document.getElementById('profile-pic-preview');
                if (headerPic) headerPic.src = profilePicPreview ? profilePicPreview.src : '';
            }
            
            setTimeout(() => {
                closeProfileModal();
            }, 1500);
        } else {
            if (profileResult) profileResult.innerHTML = '❌ ' + data.message;
        }
    });
}

// ============ FRIEND FUNCTIONS ============

function searchUser() {
    let searchId = document.getElementById('search-id')?.value || '';
    const searchResult = document.getElementById('search-result');
    
    if(!searchId) {
        if (searchResult) {
            searchResult.innerHTML = '❌ Please enter an ID';
            searchResult.classList.remove('hidden');
        }
        return;
    }
    
    if(searchId === currentUserId) {
        if (searchResult) {
            searchResult.innerHTML = '❌ You cannot add yourself!';
            searchResult.classList.remove('hidden');
        }
        return;
    }
    
    fetch('/search_user/' + searchId)
    .then(res => res.json())
    .then(data => {
        if (searchResult) {
            if(data.status === 'success') {
                searchResult.innerHTML = '✅ Found: ' + data.username + ' (' + data.user_id + ')<br><button onclick="sendFriendRequest(\'' + data.user_id + '\')">➕ Add Friend</button>';
                searchResult.classList.remove('hidden');
            } else {
                searchResult.innerHTML = '❌ User not found';
                searchResult.classList.remove('hidden');
            }
            
            setTimeout(() => {
                searchResult.classList.add('hidden');
            }, 5000);
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
            const searchResult = document.getElementById('search-result');
            const searchId = document.getElementById('search-id');
            if (searchResult) searchResult.innerHTML = '';
            if (searchId) searchId.value = '';
        } else {
            alert('❌ ' + data.message);
        }
    });
}

function loadFriendRequests() {
    fetch('/get_requests/' + currentUserId)
    .then(res => res.json())
    .then(data => {
        const requestsSection = document.getElementById('requests-section');
        const requestsList = document.getElementById('requests-list');
        
        if(data.requests && data.requests.length > 0 && requestsSection && requestsList) {
            requestsSection.classList.remove('hidden');
            let html = '';
            for(let i = 0; i < data.requests.length; i++) {
                let reqId = data.requests[i];
                html += `<div class="request-item">
                            <div class="friend-info">
                                <div class="friend-avatar">👤</div>
                                <div class="friend-details">
                                    <div class="friend-name">${reqId}</div>
                                    <div class="friend-id">ID: ${reqId}</div>
                                </div>
                            </div>
                            <button onclick="acceptRequest('${reqId}')">Accept</button>
                        </div>`;
            }
            requestsList.innerHTML = html;
        } else if (requestsSection) {
            requestsSection.classList.add('hidden');
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
        const friendsListDiv = document.getElementById('friends-list');
        const friendCountSpan = document.getElementById('friend-count');
        
        let html = '';
        if(friendsList.length === 0 && friendsListDiv) {
            html = '<div class="empty-state" style="padding: 40px; text-align: center; color: #a0aec0;">No friends yet.<br>🔍 Search and add someone!</div>';
        } else if (friendsListDiv) {
            for(let i = 0; i < friendsList.length; i++) {
                let friendId = friendsList[i];
                html += `<div class="friend-item" data-id="${friendId}" onclick="startChat('${friendId}')">
                            <div class="friend-info">
                                <div class="friend-avatar">👤</div>
                                <div class="friend-details">
                                    <div class="friend-name">${friendId}</div>
                                    <div class="friend-id">ID: ${friendId}</div>
                                </div>
                            </div>
                        </div>`;
            }
        }
        if (friendsListDiv) friendsListDiv.innerHTML = html;
        if (friendCountSpan) friendCountSpan.innerHTML = '(' + friendsList.length + ')';
    });
}

// ============ FILE SHARING ============

function showFileMenu() {
    const menu = document.getElementById('file-menu');
    if (menu) menu.classList.toggle('hidden');
}

function sendFile(fileType) {
    let input = document.getElementById('file-input');
    if (!input) return;
    
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
        };
        reader.readAsDataURL(file);
    };
    input.click();
    
    const fileMenu = document.getElementById('file-menu');
    if (fileMenu) fileMenu.classList.add('hidden');
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

// ============ CHAT FUNCTIONS - MOBILE ============

function startChat(friendId) {
    goToChatScreen(friendId, friendId);
}

function goToChatScreen(friendId, friendName) {
    currentChatWith = friendId;
    
    const contactsScreen = document.getElementById('contacts-screen');
    const chatScreen = document.getElementById('chat-screen');
    const chatWithName = document.getElementById('chat-with-name');
    
    if (contactsScreen) contactsScreen.classList.add('hidden');
    if (chatScreen) chatScreen.classList.remove('hidden');
    if (chatWithName) chatWithName.innerText = friendName || friendId;
    
    // load messages
    const messagesDiv = document.getElementById('messages');
    if (messagesDiv) messagesDiv.innerHTML = '<div class="welcome-message">💭 Loading messages...</div>';
    
    fetch('/get_messages/' + currentUserId + '/' + friendId)
    .then(res => res.json())
    .then(data => {
        if (messagesDiv) {
            messagesDiv.innerHTML = '';
            if (data.messages && data.messages.length === 0) {
                messagesDiv.innerHTML = '<div class="welcome-message">💭 No messages yet. Send a message!</div>';
            } else if (data.messages) {
                for (let i = 0; i < data.messages.length; i++) {
                    let msg = data.messages[i];
                    if (!msg.is_deleted) {
                        let isMine = msg.from_id === currentUserId;
                        displayMessageFromData(msg, isMine);
                    }
                }
            }
        }
    });
}

function goBackToContacts() {
    currentChatWith = null;
    
    const chatScreen = document.getElementById('chat-screen');
    const contactsScreen = document.getElementById('contacts-screen');
    const messageInput = document.getElementById('message-input');
    
    if (chatScreen) chatScreen.classList.add('hidden');
    if (contactsScreen) contactsScreen.classList.remove('hidden');
    if (messageInput) messageInput.value = '';
    
    loadFriends();
    loadFriendRequests();
}

function sendPrivateMessage() {
    let msg = document.getElementById('message-input')?.value || '';
    
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
    
    const messageInput = document.getElementById('message-input');
    if (messageInput) messageInput.value = '';
    
    socket.emit('typing', {
        to_id: currentChatWith,
        from_id: currentUserId,
        is_typing: false
    });
}

function displayMessage(sender, content, timestamp, isMine, type, fileName) {
    let messagesDiv = document.getElementById('messages');
    if (!messagesDiv) return;
    
    if(messagesDiv.children.length === 1 && messagesDiv.children[0].classList) {
        if(messagesDiv.children[0].classList.contains('welcome-message')) {
            messagesDiv.innerHTML = '';
        }
    }
    
    let div = document.createElement('div');
    div.className = 'message ' + (isMine ? 'my-message' : 'friend-message');
    div.setAttribute('data-content', content);
    
    let menuHtml = `<span class="three-dot-menu" onclick="showMessageOptions(event, '${Date.now()}', '${escapeHtml(content)}', ${isMine}, '${sender}')">⋮</span>`;
    
    let innerHtml = '<div class="message-content"><strong>' + (isMine ? 'You' : sender) + ':</strong> ' + escapeHtml(content);
    innerHtml += '<br><small>' + timestamp + '</small></div>';
    
    div.innerHTML = menuHtml + innerHtml;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function displayMessageFromData(msg, isMine) {
    let messagesDiv = document.getElementById('messages');
    if (!messagesDiv) return;
    
    let div = document.createElement('div');
    div.className = 'message ' + (isMine ? 'my-message' : 'friend-message');
    div.setAttribute('data-message-id', msg.message_id);
    div.setAttribute('data-content', msg.content);
    
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

function escapeHtml(text) {
    if (!text) return '';
    let div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============ REPLY TO MESSAGE ============

let currentReplyTo = null;

function showMessageOptions(event, messageId, content, isMine, senderName) {
    event.stopPropagation();
    
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
    menu.style.background = 'white';
    menu.style.borderRadius = '10px';
    menu.style.boxShadow = '0 5px 15px rgba(0,0,0,0.2)';
    menu.style.padding = '5px 0';
    menu.style.zIndex = '1000';
    menu.style.minWidth = '100px';
    
    let menuItems = menu.querySelectorAll('div');
    menuItems.forEach(item => {
        item.style.padding = '8px 15px';
        item.style.cursor = 'pointer';
        item.style.fontSize = '14px';
    });
    
    document.body.appendChild(menu);
    
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 100);
}

function openReplyModal(messageId, originalContent, senderName) {
    currentReplyTo = { messageId, originalContent, senderName };
    const replyOriginal = document.getElementById('reply-original-msg');
    const replyModal = document.getElementById('reply-modal');
    if (replyOriginal) replyOriginal.innerHTML = `<strong>Replying to ${senderName}:</strong><br>${originalContent}`;
    const replyInput = document.getElementById('reply-input');
    if (replyInput) replyInput.value = '';
    if (replyModal) replyModal.classList.remove('hidden');
}

function closeReplyModal() {
    const replyModal = document.getElementById('reply-modal');
    if (replyModal) replyModal.classList.add('hidden');
    currentReplyTo = null;
}

function sendReply() {
    let replyText = document.getElementById('reply-input')?.value || '';
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

function editMessageById(messageId, oldContent, element) {
    let newContent = prompt('Edit your message:', oldContent);
    if (newContent && newContent !== oldContent) {
        socket.emit('edit_message', {
            message_id: messageId,
            new_content: newContent,
            user_id: currentUserId
        });
    }
    if (element) {
        let menu = element.closest('.message-options');
        if (menu) menu.remove();
    }
}

function deleteMessageById(messageId, element) {
    if (!confirm('Delete this message?')) return;
    
    socket.emit('delete_message', {
        message_id: messageId,
        user_id: currentUserId,
        delete_for_everyone: true
    });
    
    if (element) {
        let menu = element.closest('.message-options');
        if (menu) menu.remove();
    }
    
    let messages = document.querySelectorAll('.message');
    for (let msg of messages) {
        if (msg.getAttribute('data-message-id') === messageId) {
            let contentDiv = msg.querySelector('.message-content');
            if (contentDiv) {
                let timestamp = contentDiv.querySelector('small')?.innerText || '';
                let sender = contentDiv.querySelector('strong')?.innerText || 'Someone:';
                contentDiv.innerHTML = sender + ' <em>[Message deleted]</em><br><small>' + timestamp + '</small>';
            }
            break;
        }
    }
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
    if (currentChatWith === data.from_id && data.is_typing) {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.classList.remove('hidden');
            setTimeout(() => {
                if (typingIndicator) typingIndicator.classList.add('hidden');
            }, 2000);
        }
    } else {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) typingIndicator.classList.add('hidden');
    }
});

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
