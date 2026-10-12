const API_BASE = window.location.origin;
let activeRoomId = null;

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

function showEmptyState(text) {
    const container = document.getElementById("messages");
    const emptyState = document.createElement("p");
    emptyState.className = "empty-state";
    emptyState.textContent = text;
    container.replaceChildren(emptyState);
}

async function loadRooms() {
    const res = await fetchWithAuth(`${API_BASE}/rooms/`);
    const rooms = await res.json();
    const list = document.getElementById("roomList");
    list.replaceChildren();

    if (rooms.length === 0) {
        const emptyItem = document.createElement("li");
        emptyItem.textContent = "Комнат пока нет";
        list.appendChild(emptyItem);
        showEmptyState("Пока нет комнат. Создайте комнату, чтобы начать переписку");
        return;
    }

    rooms.forEach(room => {
        const item = document.createElement("li");
        const button = document.createElement("button");
        button.dataset.roomId = room.id;
        button.textContent = room.name;
        button.addEventListener("click", () => openRoom(room.id));
        item.appendChild(button);
        list.appendChild(item);
    });
}

async function createRoom() {
    const name = prompt("Название комнаты");
    if (!name) return;

    const description = prompt("Описание комнаты", "");
    const res = await fetchWithAuth(`${API_BASE}/rooms/`, {
        method: "POST",
        body: JSON.stringify({ name, description })
    });

    if (res.ok) {
        await loadRooms();
    }
}

async function openRoom(roomId) {
    window.location.href = `/room?id=${encodeURIComponent(roomId)}`;
}

async function loadMessages(roomId) {
    const res = await fetchWithAuth(`${API_BASE}/rooms/${roomId}/messages`);
    if (!res.ok) {
        showEmptyState("Не удалось загрузить сообщения");
        return;
    }

    const messages = await res.json();
    const container = document.getElementById("messages");
    if (messages.length === 0) {
        showEmptyState("Пока сообщений нет");
        return;
    }

    container.replaceChildren();
    messages.forEach(msg => {
        const element = document.createElement("div");
        element.className = "message";
        element.textContent = `${msg.author_full_name}: ${msg.text}`;
        container.appendChild(element);
    });
}

async function sendMessage(event) {
    event.preventDefault();

    const input = document.getElementById("messageInput");
    const button = event.currentTarget.querySelector("button[type='submit']");
    const text = input.value.trim();
    if (activeRoomId === null || !text) return;

    const roomId = activeRoomId;
    button.disabled = true;
    try {
        const response = await fetchWithAuth(`${API_BASE}/rooms/${roomId}/messages`, {
            method: "POST",
            body: JSON.stringify({ text })
        });
        if (!response.ok) {
            throw new Error("Не удалось отправить сообщение");
        }

        await loadMessages(roomId);
        input.value = "";
        input.focus();
    } catch (error) {
        alert(error.message);
    } finally {
        button.disabled = false;
    }
}

async function openProfile(event) {
    event.preventDefault();
    const profileUrl = event.currentTarget.href;
    const response = await fetchWithAuth(`${API_BASE}/api/profile`);
    if (response.status === 401) {
        localStorage.removeItem("access_token");
        window.location.href = "/";
        return;
    }
    if (!response.ok) {
        alert("Не удалось загрузить профиль");
        return;
    }

    window.location.href = profileUrl;
}

window.addEventListener("DOMContentLoaded", () => {
    document.getElementById("createRoomBtn").addEventListener("click", createRoom);
    document.getElementById("profileLink").addEventListener("click", openProfile);
    document.getElementById("messageForm").addEventListener("submit", sendMessage);
    loadRooms();
});


