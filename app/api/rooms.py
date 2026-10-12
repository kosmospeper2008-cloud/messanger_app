from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select
from api.models import ChatRoom, RoomMember, Message,User
from api.auth import get_current_user
from api.database import get_session
from sqlalchemy import or_ 

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("/") 
async def get_rooms( 
    user: User = Depends(get_current_user), 
    session: AsyncSession = Depends(get_session), 
): 
    result = await session.execute( 
        select(ChatRoom, RoomMember.user_id) 
        .outerjoin( 
            RoomMember, 
            (RoomMember.room_id == ChatRoom.id) 
            & (RoomMember.user_id == user.telegram_id), 
        ) 
        .where( 
            or_( 
                ChatRoom.created_by == user.telegram_id, 
                RoomMember.user_id == user.telegram_id, 
            ) 
        ) 
        .distinct() 
        .order_by(ChatRoom.created_at.desc()) 
    ) 
    rooms = result.all() 
 
    return [ 
        { 
            "id": room.id, 
            "name": room.name, 
            "description": room.description, 
            "created_by": room.created_by, 
            "created_at": room.created_at.isoformat() if 
room.created_at else None, 
            "is_member": member_id is not None, 
            "is_creator": room.created_by == user.telegram_id, 
        } 
        for room, member_id in rooms 
    ] 

class CreateRoomRequest(SQLModel):
    name: str
    description: str | None = None


@router.post("/")
async def create_room(req: CreateRoomRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    room = ChatRoom(
        name=req.name,
        description=req.description,
        created_by=user.telegram_id,
    )
    session.add(room)
    await session.commit()
    await session.refresh(room)

    member = RoomMember(room_id=room.id, user_id=user.telegram_id)
    session.add(member)
    await session.commit()

    return {
        "id": room.id,
        "name": room.name,
        "description": room.description,
    }



@router.get("/{room_id}")
async def get_room(room_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    room = await session.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    member_result = await session.execute(
        select(RoomMember.room_id).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user.telegram_id,
        )
    )
    return {
        "id": room.id,
        "name": room.name,
        "description": room.description,
        "is_member": member_result.scalar_one_or_none() is not None,
        "is_creator": room.created_by == user.telegram_id,
    }




@router.get("/{room_id}/messages")
async def get_room_messages(room_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await _ensure_room_access(room_id, user, session)

    result = await session.execute(
        select(Message, User.full_name, User.username)
        .join(User, Message.user_id == User.telegram_id)
        .where(Message.room_id == room_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.all()

    return [
        {
            "id": message.id,
            "room_id": message.room_id,
            "user_id": message.user_id,
            "author_full_name": full_name,
            "author_username": username,
            "text": message.text,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        for message, full_name, username in messages
    ]


class CreateMessageRequest(SQLModel):
    text: str


@router.post("/{room_id}/messages")
async def create_message(room_id: int, req: CreateMessageRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await _ensure_room_access(room_id, user, session)

    message = Message(
        room_id=room_id,
        user_id=user.telegram_id,
        text=req.text,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)

    return {
        "id": message.id,
        "room_id": message.room_id,
        "user_id": message.user_id,
        "text": message.text,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }



from collections import deque
from time import monotonic

PRESENCE_TTL_SECONDS = 30

# room_id -> user_id -> client_id -> profile + last_seen
active_rooms: dict[int, dict[int, dict[str, dict]]] = {}
room_events: dict[int, deque] = {}
next_presence_event_id = 0


def _record_presence_event(
    room_id: int,
    event_type: str,
    user_id: int,
    profile: dict,
) -> None:
    global next_presence_event_id
    next_presence_event_id += 1

    events = room_events.setdefault(room_id, deque(maxlen=500))
    events.append({
        "id": next_presence_event_id,
        "type": event_type,
        "user_id": user_id,
        "full_name": profile["full_name"],
        "username": profile["username"],
    })


def _remove_expired_connections(room_id: int) -> None:
    users = active_rooms.get(room_id)
    if not users:
        return

    now = monotonic()

    for user_id, clients in list(users.items()):
        profile = next(iter(clients.values()), None)

        for client_id, client in list(clients.items()):
            if now - client["last_seen"] > PRESENCE_TTL_SECONDS:
                del clients[client_id]

        if not clients:
            del users[user_id]
            if profile is not None:
                _record_presence_event(room_id, "user_left", user_id, profile)

    if not users:
        active_rooms.pop(room_id, None)


async def _ensure_room_access(
    room_id: int,
    user: User,
    session: AsyncSession,
) -> None:
    room = await session.get(ChatRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    result = await session.execute(
        select(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user.telegram_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Вы не участник комнаты")


class PresenceRequest(SQLModel):
    client_id: str



@router.post("/{room_id}/presence")
async def update_presence(
    room_id: int,
    req: PresenceRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_room_access(room_id, user, session)
    _remove_expired_connections(room_id)

    users = active_rooms.setdefault(room_id, {})
    clients = users.get(user.telegram_id)

    profile = {
        "full_name": user.full_name,
        "username": user.username,
        "last_seen": monotonic(),
    }

    if clients is None:
        clients = {}
        users[user.telegram_id] = clients
        _record_presence_event(
            room_id,
            "user_joined",
            user.telegram_id,
            profile,
        )

    profile["last_seen"] = monotonic()
    clients[req.client_id] = profile

    return {"ok": True}


@router.delete("/{room_id}/presence/{client_id}")
async def remove_presence(
    room_id: int,
    client_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_room_access(room_id, user, session)
    _remove_expired_connections(room_id)

    users = active_rooms.get(room_id, {})
    clients = users.get(user.telegram_id, {})
    removed_client = clients.pop(client_id, None)

    if removed_client is not None and not clients:
        users.pop(user.telegram_id, None)
        _record_presence_event(
            room_id,
            "user_left",
            user.telegram_id,
            removed_client,
        )

    if not users:
        active_rooms.pop(room_id, None)

    return {"ok": True}


@router.get("/{room_id}/activity")
async def get_room_activity(
    room_id: int,
    after_id: int = 0,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await _ensure_room_access(room_id, user, session)
    _remove_expired_connections(room_id)

    users = active_rooms.get(room_id, {})
    active_users = []

    for user_id, clients in users.items():
        profile = next(iter(clients.values()))
        active_users.append({
            "user_id": user_id,
            "full_name": profile["full_name"],
            "username": profile["username"],
        })

    events = [
        event
        for event in room_events.get(room_id, ())
        if event["id"] > after_id
    ]

    return {
        "active_users": active_users,
        "events": events,
    }



@router.get("/{room_id}/members") 
async def get_room_members( 
    room_id: int, 
    user: User = Depends(get_current_user), 
    session: AsyncSession = Depends(get_session), 
): 
    room = await session.get(ChatRoom, room_id) 
    if room is None: 
        raise HTTPException(status_code=404, detail="Комната не найдена") 
 
    membership = await session.execute( 
        select(RoomMember.id).where( 
            RoomMember.room_id == room_id, 
            RoomMember.user_id == user.telegram_id, 
        ) 
    ) 
    is_member = membership.scalar_one_or_none() is not None 
    if not is_member and room.created_by != user.telegram_id: 
        raise HTTPException(status_code=403, detail="Нет доступа к участникам комнаты") 
 
    result = await session.execute( 
        select(RoomMember, User) 
        .join(User, User.telegram_id == RoomMember.user_id) 
        .where(RoomMember.room_id == room_id) 
        .order_by(RoomMember.joined_at.asc()) 
    ) 
    return [ 
        { 
            "user_id": member.user_id, 
            "username": profile.username, 
            "full_name": profile.full_name, 
            "joined_at": member.joined_at.isoformat() if 
member.joined_at else None, 
        } 
        for member, profile in result.all() 
    ] 