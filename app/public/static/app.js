// frontend/app.js
const API_BASE = "";

let sessionToken = null;
let expiresAt = null;
let timerInterval = null;

// ===== Утилиты для токена =====
function getToken() {
    return localStorage.getItem("access_token");
}
function setToken(token) {
    localStorage.setItem("access_token", token);
}
function clearToken() {
    localStorage.removeItem("access_token");
}

async function fetchWithAuth(url, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getToken();

    if (token) {
        headers.set("Authorization", `Bearer ${token}`);
    }
    if (options.body && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    return fetch(url, { ...options, headers });
}

// ===== Проверка авторизации =====
async function checkAuth() {
    if (!getToken()) return null;

    try {
        const res = await fetchWithAuth(`${API_BASE}/api/profile`);
        if (!res.ok) {
            clearToken();
            return null;
        }
        return await res.json();
    } catch (e) {
        clearToken();
        return null;
    }
}

// ===== Страница входа =====
async function initLogin() {
    const user = await checkAuth();
    if (user) {
        window.location.href = "/dashboard";
        return;
    }

    // Создаём сессию
    try {
        const res = await fetchWithAuth(`${API_BASE}/auth/create-session`, {
            method: "POST"
        });
        const data = await res.json();

        if (!res.ok) {
            alert("Ошибка создания сессии");
            return;
        }

        sessionToken = data.session_token;
        expiresAt = new Date(Date.now() + data.expires_in * 1000);

        const botLink = document.getElementById("botLink");
        botLink.href = data.bot_url;
    } catch (e) {
        alert("Ошибка сети");
    }
}

function openBot() {
    // Показываем шаг 2
    document.getElementById("step1").classList.add("hidden");
    document.getElementById("step2").classList.remove("hidden");

    // Запускаем таймер
    startTimer();

    // Обработчик для кнопки входа
    const btn = document.getElementById("submitBtn");
    btn.addEventListener("click", verifyCode);
}

function startTimer() {
    const timerEl = document.getElementById("timer");
    
    timerInterval = setInterval(() => {
        const now = new Date();
        const diff = Math.floor((expiresAt - now) / 1000);

        if (diff <= 0) {
            clearInterval(timerInterval);
            timerEl.textContent = "⏰ Время истекло. Обнови страницу.";
            document.getElementById("submitBtn").disabled = true;
            return;
        }

        const minutes = Math.floor(diff / 60);
        const seconds = diff % 60;
        timerEl.textContent = `⏳ Код действителен: ${minutes}:${seconds.toString().padStart(2, '0')}`;
    }, 1000);
}

async function verifyCode() {
    const code = document.getElementById("code").value.trim();
    const errorEl = document.getElementById("error");
    const btn = document.getElementById("submitBtn");
    errorEl.textContent = "";

    if (!/^\d{6}$/.test(code)) {
        errorEl.textContent = "Код должен содержать 6 цифр";
        return;
    }

    btn.disabled = true;
    btn.textContent = "Проверяем...";

    try {
        const res = await fetchWithAuth(`${API_BASE}/auth/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_token: sessionToken, code })
        });
        const data = await res.json();

        if (!res.ok) {
            errorEl.textContent = data.detail || "Ошибка";
            btn.disabled = false;
            btn.textContent = "Войти";
            return;
        }

        clearInterval(timerInterval);
        setToken(data.access_token);
        window.location.href = "/dashboard";
    } catch (e) {
        errorEl.textContent = "Ошибка сети";
        btn.disabled = false;
        btn.textContent = "Войти";
    }
}

// ===== Страница профиля =====
async function initProfile() {
    const user = await checkAuth();
    if (!user) {
        window.location.href = "/";
        return;
    }

    const card = document.getElementById("profileCard");
    if (!card) return;

    const initial = (user.full_name || user.username || "?").charAt(0).toUpperCase();

    card.innerHTML = `
        <div class="avatar">${initial}</div>
        <div class="field">
            <div class="field-label">Имя</div>
            <div class="field-value">${user.full_name || "—"}</div>
        </div>
        <div class="field">
            <div class="field-label">Username</div>
            <div class="field-value">@${user.username || "—"}</div>
        </div>
        <div class="field">
            <div class="field-label">Telegram ID</div>
            <div class="field-value">${user.telegram_id}</div>
        </div>
        <div class="field">
            <div class="field-label">Дата регистрации</div>
            <div class="field-value">${new Date(user.created_at).toLocaleString("ru-RU")}</div>
        </div>
    `;
}

function logout() {
    clearToken();
    window.location.href = "/";
}

// ===== Инициализация =====
document.addEventListener("DOMContentLoaded", () => {
    const path = window.location.pathname;
    if (path === "/" || path.endsWith("login")) {
        initLogin();
    } else if (path === "/profile") {
        initProfile();
    }
});