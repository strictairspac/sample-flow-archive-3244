-- 归档功能增量结构。新表由 SQLAlchemy create_all 幂等建立；trials 增量列由启动流程幂等执行下列 ALTER。
ALTER TABLE trials ADD COLUMN IF NOT EXISTS finished_at timestamptz;
ALTER TABLE trials ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT false;
ALTER TABLE trials ADD COLUMN IF NOT EXISTS archive_id integer;
-- archives(id, code unique, cutoff, status, file_path, checksum, trial_count, error, created_at, finished_at)
-- archive_items(id, archive_id -> archives.id, trial_id -> trials.id UNIQUE, status)
-- 约束要点：archive_items.trial_id 全局唯一，两个并发批次圈中同一演练时仅归档一份。
