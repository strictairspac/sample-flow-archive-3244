import os,logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text
from src.config.database import Base,engine
from src.models import entities
from src.controllers.auth import router as auth
from src.routes import samples,transfers,trials,archives,audit
from src.middlewares.errors import ErrorMiddleware
from src.middlewares.request_id import RequestIdMiddleware
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with engine.begin() as c:  # 既有库的增量列，幂等；详见 migrations/002_archive.sql
        for ddl in ("ALTER TABLE trials ADD COLUMN IF NOT EXISTS finished_at timestamptz",
                    "ALTER TABLE trials ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT false",
                    "ALTER TABLE trials ADD COLUMN IF NOT EXISTS archive_id integer"):
            c.execute(text(ddl))
    if os.getenv('SEED_DEMO','true')=='true':
        try:
            from scripts.seed_demo import seed
            seed()
        except Exception: logging.exception('seed failed; manual retry is available')
    yield
app=FastAPI(title='实验样本流转并发台',lifespan=lifespan)
app.add_middleware(ErrorMiddleware);app.add_middleware(RequestIdMiddleware)
for r in (auth,samples.router,transfers.router,trials.router,archives.router,audit.router): app.include_router(r)
@app.get('/health')
def health():
    with engine.connect() as c: c.execute(text('SELECT 1'))
    from src.services.common import queue
    queue.ping()
    return {'status':'healthy'}
