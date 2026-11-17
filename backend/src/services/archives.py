"""按截止时间归档已结束演练的证据。

流程：发起时把截止前已结束的演练固化为批次物品（archive_items.trial_id 全局唯一，
并发批次圈中同一演练时仅一份）→ 证据文件整体落盘并校验 SHA256 → 校验通过才逐场
清理结果、演练账与回执（每场一个事务，archived 标记与清理同事务提交，下载无中间态）
→ 条件更新置 archived 保证完成审计仅记一次。任意时刻中断都可按原批次续跑：
已清理的跳过不重复清理，重试不重复记审计。清理后文件缺失或被篡改时明确报错。
"""
import hashlib,json,os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.config.database import Session, engine
from src.config.settings import ARTIFACTS_DIR
from src.models.entities import Trial, TrialBalance, Receipt, Archive, ArchiveItem, Audit
from src.utils.serialization import record
from .common import save, queue

LOCK_BASE=7_200_000_000  # 归档批次 advisory lock 命名空间，避免与其他用途冲突

def utcnow(): return datetime.now(timezone.utc)

def _dir():
    p=Path(ARTIFACTS_DIR)/'archives';p.mkdir(parents=True,exist_ok=True);return p

def listing(db):
    rows=db.scalars(select(Archive).order_by(Archive.id.desc())).all()
    grouped={}
    for it in db.scalars(select(ArchiveItem)).all(): grouped.setdefault(it.archive_id,[]).append(it.trial_id)
    return [{**record(a),'trial_ids':sorted(grouped.get(a.id,[]))} for a in rows]

def detail(db,ident):
    obj=db.get(Archive,ident)
    if not obj: raise HTTPException(404,'归档批次不存在')
    ids=db.scalars(select(ArchiveItem.trial_id).where(ArchiveItem.archive_id==obj.id).order_by(ArchiveItem.trial_id)).all()
    return {**record(obj),'trial_ids':ids}

def create(db,data,user,enqueue=True):
    cutoff=data.cutoff
    if cutoff.tzinfo is None: cutoff=cutoff.replace(tzinfo=timezone.utc)
    claimed=select(ArchiveItem.trial_id)
    candidates=db.scalars(select(Trial).where(
        Trial.status.in_(['completed','failed']),
        Trial.finished_at.isnot(None),Trial.finished_at<=cutoff,
        Trial.archived.is_(False),
        ~Trial.id.in_(claimed),
    ).order_by(Trial.id)).all()  # 发起时刻圈定；之后才结束的演练不满足条件，不纳入
    obj=Archive(code='tmp-'+os.urandom(8).hex(),cutoff=cutoff,status='pending')
    db.add(obj);db.flush()
    obj.code=f'ARCH-{utcnow():%Y%m%d}-{obj.id:04d}'
    rows=[]
    if candidates:
        rows=db.execute(pg_insert(ArchiveItem).values([{'archive_id':obj.id,'trial_id':t.id} for t in candidates])
            .on_conflict_do_nothing(index_elements=['trial_id']).returning(ArchiveItem.trial_id)).scalars().all()
    obj.trial_count=len(rows)
    if not rows: obj.status='failed';obj.error='截止时间前已结束的演练均已被其他批次圈定，或没有可归档的演练'
    save(db,obj,user,f'发起归档批次 {obj.code}（圈定 {len(rows)} 场演练，截止 {cutoff.isoformat()}）')
    if rows and enqueue:
        try: queue.rpush('locklab:archive',str(obj.id))
        except Exception:
            obj.status='failed';obj.error='队列不可用，请稍后重试';db.commit()
    return {**record(obj),'trial_ids':sorted(rows)}

def retry(db,ident,user):
    obj=db.get(Archive,ident)
    if not obj: raise HTTPException(404,'归档批次不存在')
    if obj.status=='archived': raise HTTPException(409,'批次已归档，无需重试')
    if obj.trial_count==0: raise HTTPException(409,'批次未圈定任何演练，无法重试')
    obj.status='pending';obj.error='';db.commit()  # 重试不重复记审计；物品不变，续跑原批次
    try: queue.rpush('locklab:archive',str(obj.id))
    except Exception:
        obj.status='failed';obj.error='队列不可用，请稍后重试';db.commit();raise HTTPException(503,obj.error)
    return detail(db,ident)

def _verify(archive,trial_ids):
    """重读归档文件并校验：缺失/篡改/不完整一律明确报错，绝不返回空证据。"""
    path=Path(archive.file_path) if archive.file_path else None
    if not path or not path.exists(): raise HTTPException(410,f'归档批次 {archive.code} 的证据文件缺失，无法提供下载，请联系管理员核查')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=archive.checksum: raise HTTPException(422,f'归档批次 {archive.code} 的证据文件校验失败，内容可能被篡改')
    try: doc=json.loads(raw.decode('utf-8'))
    except Exception: raise HTTPException(422,f'归档批次 {archive.code} 的证据文件无法解析，内容可能被篡改')
    present={e.get('trial_id') for e in doc.get('entries',[])}
    missing=[t for t in trial_ids if t not in present]
    if missing: raise HTTPException(422,f'归档批次 {archive.code} 的证据文件不完整，缺少演练 {missing}')
    return doc

def _write_file(db,archive,items):
    entries=[]
    for it in items:
        trial=db.get(Trial,it.trial_id)
        balance=db.get(TrialBalance,trial.id)
        receipts=db.scalars(select(Receipt).where(Receipt.trial_id==trial.id).order_by(Receipt.id)).all()
        entries.append({'trial_id':trial.id,'export':record(trial),
            'balances':({'remaining':balance.remaining,'received':balance.received} if balance else None),
            'receipts':[{'actor':r.actor,'quantity':r.quantity} for r in receipts]})
    doc={'code':archive.code,'cutoff':archive.cutoff.isoformat(),'created_at':utcnow().isoformat(),'trial_count':len(entries),'entries':entries}
    path=_dir()/f'{archive.code}.json'
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')  # 保持键序，归档前后下载字节一致
    os.replace(tmp,path)  # 原子落盘，下载方不会读到半个文件
    archive.file_path=str(path);archive.checksum=hashlib.sha256(path.read_bytes()).hexdigest()
    _verify(archive,[it.trial_id for it in items])  # 校验完整后才允许进入清理阶段

def process_archive(archive_id,after_write=None):
    """worker 入口：落盘→校验→清理→完成。可安全重入，中断后续跑原批次。"""
    with engine.connect() as lock_conn:
        got=lock_conn.execute(text('SELECT pg_try_advisory_lock(:k)'),{'k':LOCK_BASE+archive_id}).scalar()
        if not got: return  # 另一进程正在处理同批次，避免并发清理与重复审计
        try:
            with Session() as db:
                archive=db.get(Archive,archive_id)
                if not archive or archive.status=='archived': return
                items=db.scalars(select(ArchiveItem).where(ArchiveItem.archive_id==archive_id).order_by(ArchiveItem.id)).all()
                if not items: return
                if archive.status!='processing':
                    archive.status='processing';archive.error='';db.commit()
                trial_ids=[it.trial_id for it in items]
                if not archive.checksum:
                    _write_file(db,archive,items);db.commit()
                    if after_write: after_write()  # 演练钩子：模拟“文件写完未清理”时中断
                else:
                    try: _verify(archive,trial_ids)
                    except HTTPException:
                        cleaned=db.scalar(select(Trial.id).where(Trial.archive_id==archive_id,Trial.archived.is_(True)).limit(1))
                        if cleaned: raise  # 已有演练被清理，无法从数据库重建，必须明确报错
                        archive.checksum='';db.commit()  # 尚未清理任何演练，可从数据库安全重建
                        _write_file(db,archive,items);db.commit()
                for it in items:
                    trial=db.get(Trial,it.trial_id)
                    if not trial or trial.archived: continue  # 上次中断前已清理，重试不重复清理
                    db.execute(text('DELETE FROM receipts WHERE trial_id=:t'),{'t':trial.id})
                    db.execute(text('DELETE FROM trial_balances WHERE trial_id=:t'),{'t':trial.id})
                    trial.result=None;trial.archived=True;trial.archive_id=archive_id
                    it.status='cleaned';db.commit()  # 清理与 archived 标记同事务，下载不会落到空证据
                done=db.execute(text("UPDATE archives SET status='archived',finished_at=:now WHERE id=:i AND status<>'archived'"),{'now':utcnow(),'i':archive_id}).rowcount
                if done: db.add(Audit(actor='system',action=f'归档批次 {archive.code} 完成：校验通过，清理 {len(items)} 场演练的结果、演练账与回执'))
                db.commit()
        finally:
            lock_conn.execute(text('SELECT pg_advisory_unlock(:k)'),{'k':LOCK_BASE+archive_id})

def archived_export(db,trial):
    archive=db.get(Archive,trial.archive_id)
    if not archive: raise HTTPException(410,'演练对应的归档批次记录缺失，无法提供下载')
    doc=_verify(archive,[trial.id])
    entry=next(e for e in doc['entries'] if e['trial_id']==trial.id)
    return entry['export']
