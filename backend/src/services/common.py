from redis import Redis
from src.config.settings import REDIS_URL
from src.models.entities import Audit
from src.utils.serialization import record
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
queue=Redis.from_url(REDIS_URL,decode_responses=True)
def save(db,obj,user,action):
    db.add(obj);db.add(Audit(actor=user.email,action=action))
    try: db.commit()
    except IntegrityError:
        db.rollback();raise HTTPException(409,'编号已存在或引用对象无效，请调整后重试')
    return record(obj)
