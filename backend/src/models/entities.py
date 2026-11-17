from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Text, UniqueConstraint, Boolean
from datetime import datetime, timezone
from src.config.database import Base
def utcnow(): return datetime.now(timezone.utc)
class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True);email=Column(String(120),unique=True,nullable=False)
    password=Column(String(300),nullable=False);role=Column(String(20),nullable=False)
class Sample(Base):
    __tablename__='samples'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False)
    title=Column(String(160),nullable=False);quantity=Column(Integer,nullable=False);location=Column(String(120),nullable=False)
class Transfer(Base):
    __tablename__='transfers'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False)
    sample_id=Column(Integer,ForeignKey('samples.id'),nullable=False);destination=Column(String(120),nullable=False)
    quantity=Column(Integer,nullable=False);note=Column(String(300),default='')
class Trial(Base):
    __tablename__='trials'
    id=Column(Integer,primary_key=True);name=Column(String(120),nullable=False)
    transfer_id=Column(Integer,ForeignKey('transfers.id'),nullable=False);timeout_ms=Column(Integer,nullable=False)
    status=Column(String(20),default='queued',nullable=False);result=Column(JSON,nullable=True)
    created_at=Column(DateTime(timezone=True),default=utcnow);error=Column(Text,default='')
    finished_at=Column(DateTime(timezone=True),nullable=True)
    archived=Column(Boolean,default=False,nullable=False)
    archive_id=Column(Integer,ForeignKey('archives.id'),nullable=True)
class TrialBalance(Base):
    __tablename__='trial_balances'
    trial_id=Column(Integer,ForeignKey('trials.id'),primary_key=True);remaining=Column(Integer,nullable=False);received=Column(Integer,nullable=False,default=0)
class Receipt(Base):
    __tablename__='receipts'
    id=Column(Integer,primary_key=True);trial_id=Column(Integer,ForeignKey('trials.id'),nullable=False)
    actor=Column(String(20),nullable=False);quantity=Column(Integer,nullable=False)
    __table_args__=(UniqueConstraint('trial_id','actor'),)
class Audit(Base):
    __tablename__='audit_logs'
    id=Column(Integer,primary_key=True);actor=Column(String(120),nullable=False);action=Column(String(160),nullable=False)
    created_at=Column(DateTime(timezone=True),default=utcnow)
class Archive(Base):
    __tablename__='archives'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False)
    cutoff=Column(DateTime(timezone=True),nullable=False)
    status=Column(String(20),default='pending',nullable=False)
    file_path=Column(String(300),default='');checksum=Column(String(64),default='')
    trial_count=Column(Integer,nullable=False,default=0)
    error=Column(Text,default='')
    created_at=Column(DateTime(timezone=True),default=utcnow)
    finished_at=Column(DateTime(timezone=True),nullable=True)
class ArchiveItem(Base):
    __tablename__='archive_items'
    id=Column(Integer,primary_key=True)
    archive_id=Column(Integer,ForeignKey('archives.id'),nullable=False)
    trial_id=Column(Integer,ForeignKey('trials.id'),nullable=False)
    status=Column(String(20),default='pending',nullable=False)
    __table_args__=(UniqueConstraint('trial_id'),)  # 同一演练全局只会被一个批次圈定
