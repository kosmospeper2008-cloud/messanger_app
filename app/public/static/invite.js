const token = new URLSearchParams(window.location.search).get("token");
const button = document.getElementById("acceptInviteBtn");
const roomName = document.getElementById("inviteRoomName");
const error = document.getElementById("inviteError");
const tokenPattern = /^[A-Za-z0-9_-]{20,128}$/;

function getToken() {
    return localStorage.getItem("access_token");
}

async function fetchWithAuth(url, options = {}) {
    const headers = new Headers(options.headers || {});
    const accessToken = getToken();

    if (accessToken) {
        headers.set("Authorization", `Bearer ${accessToken}`);
    }
    if (options.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    return fetch(url, { ...options, headers });
}

async function loadInvite() {
    if (!token || !tokenPattern.test(token)) {
        error.textContent = "Ссылка-приглашение имеет неверный формат.";
        roomName.textContent = "";
        return;
    }

    if (!getToken()) {
        sessionStorage.setItem("pendingInviteToken", token);
        window.location.href = "/";
        return;
    }

    try {
        const response = await fetchWithAuth(
            `/invite-links/${encodeURIComponent(token)}`
        );
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Не удалось проверить приглашение.");
        }

        roomName.textContent = `Вас пригласили в комнату «${data.room_name}».`;
        button.hidden = false;
    } catch (requestError) {
        error.textContent = requestError.message;
        roomName.textContent = "";
    }
}

button.addEventListener("click", async () => {
    button.disabled = true;
    error.textContent = "";

    try {
        const response = await fetchWithAuth(
            `/invite-links/${encodeURIComponent(token)}/accept`,
            { method: "POST" }
        );
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || "Не удалось принять приглашение.");
        }

        sessionStorage.removeItem("pendingInviteToken");
        window.location.href = `/room?id=${encodeURIComponent(data.room_id)}`;
    } catch (requestError) {
        error.textContent = requestError.message;
        button.disabled = false;
    }
});

loadInvite();
