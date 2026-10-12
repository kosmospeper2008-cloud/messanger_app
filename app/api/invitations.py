from datetime import datetime, timezone 
 
from fastapi import APIRouter, Depends, HTTPException, status 
from sqlalchemy.exc import IntegrityError 
from sqlmodel import SQLModel, select 
from sqlalchemy.ext.asyncio import AsyncSession 
from api.auth import get_current_user 
from api.database import get_session 
from api.models import ChatRoom, RoomInvitation, RoomMember, User 
 
router = APIRouter(tags=["invitations"]) 
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