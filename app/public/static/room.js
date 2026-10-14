const API_BASE = window.location.origin;

let currentUserTelegramId = null

const roomId = new URLSearchParams(window.location.search).get("id");
const clientId = crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

let lastPresenceEventId = 0;
let receivedInitialActivity = false;
let lastMessageId = 0;
let activityPollTimer = null;
let messagePollTimer = null;
let heartbeatTimer = null;
let leavingRoom = false;
let roomSessionActive = false;

function getToken() {
    return localStorage.getItem("access_token");
}

async function fetchWithAuth(url, options = {}) {
    const token = getToken();
    return fetch(url, {
        ...options,
        headers: {
            ...(options.headers || {}),
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json",
        },
    });
}

async function loadCurrentUserProfile() { 
try { 
const res = await fetchWithAuth(`${API_BASE}/api/profile`); 
if (!res.ok) { 
console.error("Не удалось загрузить профиль"); 
return; 
} 
const profile = await res.json(); 
currentUserTelegramId = profile.telegram_id; 
} catch (error) { 
console.error("Ошибка загрузки профиля:", error); 
} 
} 



async function loadRoomDetails() {
    const res = await fetchWithAuth(`${API_BASE}/rooms/${roomId}`);
    if (res.status === 401) {
        localStorage.removeItem("access_token");
        window.location.href = "/";
        return false;
    }
    if (!res.ok) {
        window.location.href = "/dashboard";
        return false;
    }
    const room = await res.json();
    const inviteButton = document.getElementById("inviteMemberBtn"); 
    if (room.is_creator) { 
        inviteButton.hidden = false; 
        inviteButton.addEventListener("click", inviteMember); 
    } 

    document.getElementById("roomTitle").textContent = room.name;
    return room;
}

async function loadMessages(reset = false) { 
    const res = await fetchWithAuth(`${API_BASE}/rooms/${roomId}/messages`); 
    if (!res.ok) return; 
 
    const messages = await res.json(); 
    const container = document.getElementById("roomMessages"); 
 
    // Сохраняем позицию скролла, чтобы polling не сбрасывал чтение 
    const scrollTop = container.scrollTop; 
    const wasAtBottom = container.scrollHeight - container.scrollTop - 
container.clientHeight < 30; 
 
    container.replaceChildren(); 
 
    if (messages.length === 0) { 
        const empty = document.createElement("p"); 
        empty.className = "empty-state"; 
        empty.textContent = "Пока сообщений нет"; 
        container.appendChild(empty); 
        lastMessageId = 0; 
        return; 
    } 
 
    messages.forEach(msg => { 
        const el = document.createElement("div"); 
        el.className = "message"; 
        el.dataset.messageId = msg.id; 
 
        // Имя автора 
        const authorSpan = document.createElement("strong"); 
        authorSpan.textContent = msg.author_full_name || `Пользователь 
${msg.user_id}`; 
 
        // Текст сообщения 
        const textSpan = document.createElement("span"); 
        textSpan.className = "message-text"; 
        textSpan.textContent = ": " + msg.text; 
 
        el.appendChild(authorSpan); 
        el.appendChild(textSpan); 
 
        // Отметка «изменено» 
        if (msg.updated_at) { 
            const editedSpan = document.createElement("span"); 
            editedSpan.className = "message-edited"; 
            editedSpan.textContent = "(изменено)"; 
            el.appendChild(editedSpan); 
        } 
 
        // Кнопки действий только для автора 
        if (currentUserTelegramId && msg.user_id === currentUserTelegramId) { 
            const actions = document.createElement("div"); 
            actions.className = "message-actions"; 
 
            const editBtn = document.createElement("button"); 
            editBtn.textContent = "Редактировать"; 
            editBtn.dataset.messageId = msg.id; 
            editBtn.dataset.action = "edit"; 
 
            const deleteBtn = document.createElement("button"); 
            deleteBtn.textContent = "Удалить"; 
            deleteBtn.className = "delete-btn"; 
            deleteBtn.dataset.messageId = msg.id; 
            deleteBtn.dataset.action = "delete"; 
 
            actions.appendChild(editBtn); 
            actions.appendChild(deleteBtn); 
            el.appendChild(actions); 
        } 
 
        container.appendChild(el); 
        lastMessageId = Math.max(lastMessageId, msg.id); 
    }); 
 
    // Восстанавливаем позицию скролла 
    if (reset || wasAtBottom) { 
        container.scrollTop = container.scrollHeight; 
    } else { 
        container.scrollTop = scrollTop; 
    } 
}

async function sendMessage(e) {
    e.preventDefault();
    const input = document.getElementById("messageInput");
    const text = input.value.trim();

    if (!text) return;

    const response = await fetchWithAuth(`${API_BASE}/rooms/${roomId}/messages`, {
        method: "POST",
        body: JSON.stringify({ text }),
    });
    if (!response.ok) {
        alert("Не удалось отправить сообщение");
        return;
    }

    input.value = "";
    await loadMessages();
}

async function sendPresenceHeartbeat() {
    if (leavingRoom) return;

    const response = await fetchWithAuth(`${API_BASE}/rooms/${roomId}/presence`, {
        method: "POST",
        body: JSON.stringify({ client_id: clientId }),
    });
    if (response.status === 401) {
        localStorage.removeItem("access_token");
        window.location.href = "/";
    }
}

async function pollRoomActivity() {
    try {
        if (leavingRoom) return;
        const response = await fetchWithAuth(
            `${API_BASE}/rooms/${roomId}/activity?after_id=${lastPresenceEventId}`
        );
        if (response.status === 401) {
            localStorage.removeItem("access_token");
            window.location.href = "/";
            return;
        }
        if (!response.ok) return;

        const data = await response.json();
        renderActiveUsers(data.active_users);

        for (const event of data.events) {
            lastPresenceEventId = Math.max(lastPresenceEventId, event.id);

            if (receivedInitialActivity) {
                appendPresenceNotice(event);
            }
        }
        receivedInitialActivity = true;
    } catch (error) {
        console.error("Не удалось обновить присутствие в комнате", error);
    } finally {
        if (!leavingRoom) {
            activityPollTimer = window.setTimeout(pollRoomActivity, 3000);
        }
    }
}

async function pollRoomMessages() {
    try {
        if (leavingRoom) return;
        await loadMessages();
    } catch (error) {
        console.error("Не удалось обновить сообщения комнаты", error);
    } finally {
        if (!leavingRoom) {
            messagePollTimer = window.setTimeout(pollRoomMessages, 3000);
        }
    }
}

function renderActiveUsers(users) {
    const list = document.getElementById("activeUsers");
    list.replaceChildren();

    for (const user of users) {
        const item = document.createElement("li");
        const name = user.full_name || `Пользователь ${user.user_id}`;
        item.textContent = user.username
            ? `${name} (@${user.username})`
            : name;
        list.appendChild(item);
    }
}

function appendPresenceNotice(event) {
    const messages = document.getElementById("roomMessages");
    messages.querySelector(".empty-state")?.remove();
    const item = document.createElement("div");
    item.className = "message system-message";

    const name = event.full_name || `Пользователь ${event.user_id}`;
    item.textContent = event.type === "user_joined"
        ? `${name} присоединился к комнате`
        : `${name} покинул комнату`;

    messages.appendChild(item);
}

function leaveRoom() {
    if (!roomSessionActive || leavingRoom) return;
    leavingRoom = true;
    window.clearInterval(heartbeatTimer);
    window.clearTimeout(activityPollTimer);
    window.clearTimeout(messagePollTimer);

    fetchWithAuth(
        `${API_BASE}/rooms/${roomId}/presence/${clientId}`,
        { method: "DELETE", keepalive: true }
    ).catch(() => {});
}

async function enterRoom() {

        try { 
            await loadRoomMembers(); 
        } catch (error) { 
            document.getElementById("memberError").textContent = 
        error.message; 
        } 

    document.getElementById("roomChat").hidden = false;
    document.getElementById("roomMembers").hidden = false;
    document.getElementById("roomMessageForm").addEventListener("submit", sendMessage);
    roomSessionActive = true;

    await loadCurrentUserProfile();

    await loadMessages(true);
    await sendPresenceHeartbeat();
    await pollRoomActivity();
    messagePollTimer = window.setTimeout(pollRoomMessages, 3000);
    heartbeatTimer = window.setInterval(() => {
        sendPresenceHeartbeat().catch(console.error);
    }, 10000);
}



async function loadRoomMembers() { 
    const response = await fetchWithAuth( 
        `${API_BASE}/rooms/${roomId}/members` 
    ); 
    if (!response.ok) { 
        throw new Error("Не удалось загрузить участников комнаты"); 
    } 
 
    const members = await response.json(); 
    const list = document.getElementById("memberList"); 
    list.replaceChildren(); 
 
    if (members.length === 0) { 
        const empty = document.createElement("li"); 
        empty.textContent = "Участников пока нет"; 
        list.appendChild(empty); 
        return; 
    } 
 
    for (const member of members) { 
        const item = document.createElement("li"); 
        item.textContent = member.full_name 
            || (member.username ? `@${member.username}` : `Пользователь ${member.user_id}`); 
        list.appendChild(item); 
    } 
} 
 
async function inviteMember() { 
    const input = window.prompt("Введите Telegram ID пользователя"); 
    if (input === null) return; 
 
    const telegramId = Number(input.trim()); 
    const status = document.getElementById("inviteStatus"); 
    status.textContent = ""; 
 
    if (!Number.isSafeInteger(telegramId) || telegramId <= 0) { 
        status.textContent = "Введите корректный Telegram ID"; 
        return; 
    } 
 
    try { 
        const response = await fetchWithAuth( 
           `${API_BASE}/rooms/${roomId}/invite`, 
            { 
                method: "POST", 
                body: JSON.stringify({ telegram_id: telegramId 
}), 
            } 
        ); 
        const result = await response.json(); 
        if (!response.ok) { 
            throw new Error(result.detail || "Не удалось отправить приглашение"); 
        } 
 
        status.textContent = "Приглашение отправлено. Ожидается принятие."; 
        // Намеренно не вызываем loadRoomMembers(): адресат еще не участник. 
    } catch (error) { 
        status.textContent = error.message; 
    }
}


// ===== Делегирование кликов по кнопкам сообщений ===== 
document.getElementById("roomMessages").addEventListener("click", async (e) => { 
    const btn = e.target.closest("[data-action]"); 
    if (!btn) return; 
 
    const messageId = btn.dataset.messageId; 
    const action = btn.dataset.action; 
 
    if (action === "edit") { 
        openEditDialog(messageId); 
    } else if (action === "delete") { 
        await handleDelete(messageId, btn); 
    } 
}); 
 
 
// ===== Редактирование ===== 
let editingMessageId = null; 
 
function openEditDialog(messageId) { 
    editingMessageId = messageId; 
 
    // Ищем текущий текст сообщения в DOM 
    const msgEl = document.querySelector(`.message[data-message
id="${messageId}"]`); 
    if (!msgEl) return; 
 
    const textSpan = msgEl.querySelector(".message-text"); 
    // Убираем ": " в начале 
    const currentText = textSpan ? textSpan.textContent.slice(2) : ""; 
 
    const dialog = document.getElementById("editMessageDialog"); 
    const textarea = document.getElementById("editMessageText"); 
    const errorEl = document.getElementById("editMessageError"); 
 
    textarea.value = currentText; 
    errorEl.textContent = ""; 
    dialog.showModal(); 
} 
 
document.getElementById("editMessageForm").addEventListener("submit", async (e) => { 
    e.preventDefault(); 
 
    const textarea = document.getElementById("editMessageText"); 
    const errorEl = document.getElementById("editMessageError"); 
    const submitBtn = e.target.querySelector("button[type='submit']"); 
    const text = textarea.value.trim(); 
 
    errorEl.textContent = ""; 
 
    if (!text) { 
        errorEl.textContent = "Текст не может быть пустым"; 
        return; 
    } 
    if (text.length > 5000) { 
        errorEl.textContent = "Текст не должен превышать 5000 символов"; 
        return; 
    } 
 
    submitBtn.disabled = true; 
    try { 
        const response = await fetchWithAuth( 
            `${API_BASE}/rooms/${roomId}/messages/${editingMessageId}`, 
            { 
                method: "PATCH", 
                body: JSON.stringify({ text }), 
            } 
        ); 
 
        if (response.ok) { 
            document.getElementById("editMessageDialog").close(); 
            await loadMessages(true); 
        } else { 
            const data = await response.json(); 
            errorEl.textContent = data.detail || "Ошибка при сохранении"; 
        } 
    } catch (error) { 
        errorEl.textContent = "Ошибка сети"; 
    } finally { 
        submitBtn.disabled = false; 
    } 
}); 
 
document.getElementById("cancelEditMessage").addEventListener("click", () => { 
    document.getElementById("editMessageDialog").close(); 
}); 
 
 
// ===== Удаление ===== 
async function handleDelete(messageId, btn) { 
    if (!window.confirm("Вы уверены, что хотите удалить это сообщение?")) { 
        return; 
    } 
 
    btn.disabled = true; 
    try { 
        const response = await fetchWithAuth( 
            `${API_BASE}/rooms/${roomId}/messages/${messageId}`, 
            { method: "DELETE" } 
        ); 
 
        if (response.status === 204 || response.ok) { 
            await loadMessages(true); 
        } else { 
            const data = await response.json(); 
            alert(data.detail || "Ошибка при удалении"); 
        } 
    } catch (error) { 
        alert("Ошибка сети"); 
    } finally { 
        btn.disabled = false; 
    } 
}




window.addEventListener("DOMContentLoaded", async () => {
    if (!roomId) {
        window.location.href = "/dashboard";
        return;
    }

    if (!getToken()) {
        window.location.href = "/";
        return;
    }
    const room = await loadRoomDetails();
    if (!room) return;

    if (!room.is_member) {
        window.location.href = "/dashboard";
        return;
    }

    await enterRoom();
});

window.addEventListener("pagehide", leaveRoom);
window.addEventListener("pageshow", event => {
    if (!event.persisted || !roomId || !roomSessionActive) return;

    leavingRoom = false;
    sendPresenceHeartbeat().catch(console.error);
    pollRoomActivity();
    pollRoomMessages();
    heartbeatTimer = window.setInterval(() => {
        sendPresenceHeartbeat().catch(console.error);
    }, 10000);
});