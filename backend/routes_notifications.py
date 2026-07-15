from fastapi import APIRouter, Depends

from auth import get_current_user
from database import db
from utils import clean

router = APIRouter(prefix='/notifications', tags=['notifications'])


@router.get('')
async def list_notifications(user: dict = Depends(get_current_user)):
    items = await db.notifications.find({'user_id': user['id']}, {'_id': 0}).sort('created_at', -1).to_list(50)
    unread = await db.notifications.count_documents({'user_id': user['id'], 'read': False})
    return {'items': items, 'unread': unread}


@router.post('/mark-read')
async def mark_all_read(user: dict = Depends(get_current_user)):
    await db.notifications.update_many({'user_id': user['id'], 'read': False}, {'$set': {'read': True}})
    return {'ok': True}


@router.post('/{notification_id}/read')
async def mark_read(notification_id: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({'id': notification_id, 'user_id': user['id']}, {'$set': {'read': True}})
    return {'ok': True}
