async function loadNotifications() { 
    const response = await fetchWithAuth(`${API_BASE}/notifications`); 
    if (!response.ok) { 
        throw new Error("Не удалось загрузить уведомления"); 
    } 
 
    const data = await response.json(); 
    document.getElementById("unreadCount").textContent = 
        data.unread_count > 99 ? "99+" : 
String(data.unread_count); 
 
    const list = document.getElementById("notificationList"); 
    list.replaceChildren(); 
 
    if (data.items.length === 0) { 
        const empty = document.createElement("li"); 
        empty.textContent = "Новых приглашений нет"; 
        list.appendChild(empty); 
        return; 
    } 
 
    for (const notification of data.items) { 
        const item = document.createElement("li"); 
        const inviter = notification.invited_by.full_name 
            || notification.invited_by.username 
            || `Пользователь ${notification.invited_by.user_id}`; 
        const text = document.createElement("p"); 
        text.textContent = 
            `${inviter} приглашает вас в комнату 
«${notification.room_name}»`; 
        item.appendChild(text); 
 
        if (notification.status === "pending") { 
            const accept = document.createElement("button"); 
            accept.type = "button"; 
            accept.textContent = "Принять"; 
            accept.dataset.action = "accept"; 
            accept.dataset.invitationId = 
notification.invitation_id; 
 
            const decline = document.createElement("button"); 
            decline.type = "button"; 
            decline.textContent = "Отклонить"; 
            decline.dataset.action = "decline"; 
            decline.dataset.invitationId = 
notification.invitation_id; 
 
            item.append(accept, decline); 
        } else { 
            const state = document.createElement("span"); 
            state.textContent = notification.status === 
"accepted" 
                ? "Приглашение принято" 
                : "Приглашение отклонено"; 
            item.appendChild(state); 
        } 
 
        list.appendChild(item); 
    } 
} 
 
async function respondToInvitation(invitationId, action) { 
    const error = document.getElementById("notificationError"); 
    error.textContent = ""; 
 
    try { 
        const response = await fetchWithAuth( 
            `${API_BASE}/invitations/${invitationId}/${action}`, 
            { method: "POST" } 
        ); 
        if (!response.ok) { 
            const result = await response.json(); 
            throw new Error(result.detail || "Не удалось обработать приглашение"); 
        } 
 
        await loadNotifications(); 
        if (action === "accept") { 
            await loadRooms(); 
        } 
    } catch (requestError) { 
        error.textContent = requestError.message; 
    } 
} 
 
function setupNotifications() { 
    const button = document.getElementById("notificationBtn"); 
    const panel = document.getElementById("notificationPanel"); 
    const list = document.getElementById("notificationList"); 
 
    button.addEventListener("click", async () => { 
        panel.hidden = !panel.hidden; 
        button.setAttribute("aria-expanded", 
String(!panel.hidden)); 
        if (panel.hidden) return; 
 
        try { 
            const response = await fetchWithAuth( 
                `${API_BASE}/notifications/read`, 
                { method: "POST" } 
            ); 
            if (!response.ok) { 
                throw new Error("Не удалось отметить уведомления прочитанными"); 
            } 
            await loadNotifications(); 
        } catch (error) { 
            document.getElementById("notificationError").textContent = error.message;
        } 
    }); 
 
    list.addEventListener("click", event => { 
        const button = event.target.closest("button[data-action]");
        if (!button) return; 
        respondToInvitation(button.dataset.invitationId, 
button.dataset.action); 
    }); 
 
    loadNotifications().catch(error => { 
        document.getElementById("notificationError").textContent 
= error.message; 
    }); 
    window.setInterval(() => { 
        loadNotifications().catch(error => 
console.error(error)); 
    }, 30000); 
}

window.addEventListener("DOMContentLoaded", setupNotifications);