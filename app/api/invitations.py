import hashlib
import secrets
import time

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel, select

from api.auth import get_current_user
from api.database import get_session
from api.models import ChatRoom, RoomInvitation, RoomInviteLink, RoomMember, User
 
router = APIRouter(tags=["invitations"]) 


def _hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_invite_link(invite: RoomInviteLink | None) -> RoomInviteLink:
    if invite is None:
        raise HTTPException(status_code=404, detail="Ссылка-приглашение не найдена")
    if invite.revoked_at is not None:
        raise HTTPException(status_code=410, detail="Ссылка-приглашение отозвана")
    if invite.expires_at <= int(time.time()):
        raise HTTPException(status_code=410, detail="Срок действия ссылки истёк")
    if invite.used_at is not None:
        raise HTTPException(status_code=409, detail="Ссылка уже использована")
    return invite


@router.post("/rooms/{room_id}/invite-link", status_code=status.HTTP_201_CREATED)
async def create_room_invite_link(
    room_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    room = await session.get(ChatRoom, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    if room.created_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Создать ссылку может только создатель комнаты",
        )

    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 24 * 60 * 60
    invite = RoomInviteLink(
        room_id=room_id,
        created_by_id=user.telegram_id,
        token_hash=_hash_invite_token(token),
        expires_at=expires_at,
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    return {
        "invite_id": invite.id,
        "invite_path": f"/invite?token={token}",
        "expires_at": expires_at,
    }


@router.get("/invite-links/{token}", dependencies=[Depends(get_current_user)])
async def get_room_invite_link(
    token: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RoomInviteLink).where(
            RoomInviteLink.token_hash == _hash_invite_token(token)
        )
    )
    invite = _validate_invite_link(result.scalar_one_or_none())

    room = await session.get(ChatRoom, invite.room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")

    return {
        "room_id": room.id,
        "room_name": room.name,
        "expires_at": invite.expires_at,
    }


@router.post("/invite-links/{token}/accept")
async def accept_room_invite_link(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    token_hash = _hash_invite_token(token)
    result = await session.execute(
        select(RoomInviteLink).where(RoomInviteLink.token_hash == token_hash)
    )
    invite = _validate_invite_link(result.scalar_one_or_none())

    now = int(time.time())
    claim_result = await session.execute(
        update(RoomInviteLink)
        .where(
            RoomInviteLink.id == invite.id,
            RoomInviteLink.used_at.is_(None),
            RoomInviteLink.revoked_at.is_(None),
            RoomInviteLink.expires_at > now,
        )
        .values(used_at=now)
    )
    if claim_result.rowcount != 1:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ссылка уже использована, отозвана или просрочена",
        )

    membership_result = await session.execute(
        select(RoomMember.id).where(
            RoomMember.room_id == invite.room_id,
            RoomMember.user_id == user.telegram_id,
        )
    )
    already_member = membership_result.scalar_one_or_none() is not None
    if not already_member:
        session.add(RoomMember(room_id=invite.room_id, user_id=user.telegram_id))

    await session.commit()
    return {"room_id": invite.room_id, "already_member": already_member}


@router.post("/rooms/{room_id}/invite-links/{invite_id}/revoke")
async def revoke_room_invite_link(
    room_id: int,
    invite_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    room = await session.get(ChatRoom, room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Комната не найдена")
    if room.created_by != user.telegram_id:
        raise HTTPException(
            status_code=403,
            detail="Отозвать ссылку может только создатель комнаты",
        )

    invite = await session.get(RoomInviteLink, invite_id)
    if invite is None or invite.room_id != room_id:
        raise HTTPException(status_code=404, detail="Ссылка-приглашение не найдена")
    if invite.used_at is not None:
        raise HTTPException(status_code=409, detail="Ссылка уже использована")
    if invite.revoked_at is None:
        invite.revoked_at = int(time.time())
        await session.commit()

    return {"ok": True}
class InviteUserRequest(SQLModel): 
    telegram_id: int 
 
@router.post("/rooms/{room_id}/invite", status_code=status.HTTP_201_CREATED) 
async def invite_user( 
    room_id: int, 
    request: InviteUserRequest, 
    user: User = Depends(get_current_user), 
    session: AsyncSession = Depends(get_session), 
): 
    room = await session.get(ChatRoom, room_id) 
    if room is None: 
        raise HTTPException(status_code=404, detail="Комната не найдена") 
    if room.created_by != user.telegram_id: 
        raise HTTPException(status_code=403, detail="Приглашать может только создатель") 
    if request.telegram_id == user.telegram_id: 
        raise HTTPException(status_code=400, detail="Нельзя пригласить себя") 
 
    invited_user_result = await session.execute( 
        select(User).where(User.telegram_id == request.telegram_id) 
    ) 
    if invited_user_result.scalar_one_or_none() is None: 
        raise HTTPException(status_code=404, 
detail="Пользователь не найден") 
 
    membership = await session.execute( 
        select(RoomMember.id).where( 
            RoomMember.room_id == room_id, 
            RoomMember.user_id == request.telegram_id, 
        ) 
    ) 
    if membership.scalar_one_or_none() is not None: 
        raise HTTPException(status_code=409, 
detail="Пользователь уже в комнате") 
 
    result = await session.execute( 
        select(RoomInvitation).where( 
            RoomInvitation.room_id == room_id, 
            RoomInvitation.invitee_id == request.telegram_id, 
        ) 
    ) 
    invitation = result.scalar_one_or_none() 
    now = datetime.now(timezone.utc) 
 
    if invitation is not None and invitation.status != "declined": 
        raise HTTPException(status_code=409, detail="Приглашение уже существует") 
 
    if invitation is None: 
        invitation = RoomInvitation( 
            room_id=room_id, 
            invitee_id=request.telegram_id, 
            invited_by_id=user.telegram_id, 
            status="pending", 
            is_read=False, 
            created_at=now, 
        ) 
        session.add(invitation) 
    else: 
        invitation.invited_by_id = user.telegram_id 
        invitation.status = "pending" 
        invitation.is_read = False 
        invitation.created_at = now 
        invitation.responded_at = None 
 
    try: 
        await session.commit() 
        await session.refresh(invitation) 
    except IntegrityError as exc: 
        await session.rollback() 
        raise HTTPException( 
            status_code=409, 
            detail="Приглашение уже было создано", 
        ) from exc 
 
    return { 
        "id": invitation.id, 
        "room_id": invitation.room_id, 
        "telegram_id": invitation.invitee_id, 
        "status": invitation.status, 
    } 
 
@router.get("/notifications") 
async def get_notifications( 
    user: User = Depends(get_current_user), 
    session: AsyncSession = Depends(get_session), 
): 
    result = await session.execute( 
        select(RoomInvitation, ChatRoom, User) 
        .join(ChatRoom, ChatRoom.id == RoomInvitation.room_id) 
        .join(User, User.telegram_id == 
RoomInvitation.invited_by_id) 
        .where(RoomInvitation.invitee_id == user.telegram_id) 
        .order_by(RoomInvitation.created_at.desc()) 
    ) 
    rows = result.all() 
    items = [ 
        { 
            "id": invitation.id, 
            "type": "room_invitation", 
            "invitation_id": invitation.id, 
            "room_id": room.id, 
            "room_name": room.name, 
            "invited_by": { 
                "user_id": inviter.telegram_id, 
                "username": inviter.username, 
                "full_name": inviter.full_name, 
            }, 
            "status": invitation.status, 
            "is_read": invitation.is_read, 
            "created_at": invitation.created_at.isoformat(), 
        } 
        for invitation, room, inviter in rows 
    ] 
    return { 
        "unread_count": sum(not item["is_read"] for item in 
items), 
        "items": items, 
    } 
 
@router.post("/notifications/read") 
async def mark_notifications_read( 
    user: User = Depends(get_current_user), 
    session: AsyncSession = Depends(get_session), 
): 
    result = await session.execute( 
        select(RoomInvitation).where( 
            RoomInvitation.invitee_id == user.telegram_id, 
            RoomInvitation.is_read.is_(False), 
        ) 
    ) 
    for invitation in result.scalars().all(): 
        invitation.is_read = True 
    await session.commit() 
    return {"ok": True} 



 
async def _respond_to_invitation( 
    invitation_id: int, 
    user: User, 
    session: AsyncSession, 
    new_status: str, 
): 
    invitation = await session.get(RoomInvitation, 
invitation_id) 
    if invitation is None or invitation.invitee_id != user.telegram_id: 
        raise HTTPException(status_code=404, detail="Приглашение не найдено") 
 
    if invitation.status == new_status: 
        return {"invitation_id": invitation.id, "status": invitation.status} 
    if invitation.status != "pending": 
        raise HTTPException(status_code=409, detail="Приглашение уже обработано") 
 
    if new_status == "accepted": 
        membership = await session.execute( 
            select(RoomMember.id).where( 
                RoomMember.room_id == invitation.room_id, 
                RoomMember.user_id == user.telegram_id, 
            ) 
        ) 
        if membership.scalar_one_or_none() is None: 
            session.add( 
                RoomMember(room_id=invitation.room_id, user_id=user.telegram_id) 
            ) 
 
    invitation.status = new_status 
    invitation.is_read = True 
    invitation.responded_at = datetime.now(timezone.utc) 
    try: 
        await session.commit() 
    except IntegrityError as exc: 
        await session.rollback() 
        raise HTTPException( 
            status_code=409, 
            detail="Состояние приглашения изменилось. Обновите уведомления.", 
        ) from exc 
 
    return {"invitation_id": invitation.id, "status": 
invitation.status} 
 
@router.post("/invitations/{invitation_id}/accept") 
async def accept_invitation( 
    invitation_id: int, 
    user: User = Depends(get_current_user), 
    session: AsyncSession = Depends(get_session), 
): 
    return await _respond_to_invitation( 
        invitation_id, user, session, "accepted" 
    ) 
 
@router.post("/invitations/{invitation_id}/decline") 
async def decline_invitation( 
    invitation_id: int, 
    user: User = Depends(get_current_user), 
    session: AsyncSession = Depends(get_session)): 
    return await _respond_to_invitation(invitation_id, user, session, "declined")