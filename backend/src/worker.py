import time,traceback,json
from datetime import datetime, timezone
from pathlib import Path
from src.config.database import Session
from src.config.settings import ARTIFACTS_DIR
from src.models.entities import Trial, Archive, Audit
from src.services.common import queue
from src.services.concurrency import execute
from src.services.archives import process_archive
while True:
    Path('/tmp/worker-heartbeat').touch()
    item=queue.blpop(['locklab:queue','locklab:archive'],timeout=2)  # 演练队列优先，日常演练照常执行
    if not item: continue
    key,raw=item[0],item[1]
    try:
        if key=='locklab:archive':
            process_archive(int(raw));continue
        ident=int(raw)
        result=execute(ident)
        Path(f'{ARTIFACTS_DIR}/trial-{ident}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as e:
        traceback.print_exc()
        msg=str(getattr(e,'detail',None) or e)  # HTTPException 取 detail，保留明确的中文原因
        with Session() as db:
            if key=='locklab:archive':
                obj=db.get(Archive,int(raw))
                if obj and obj.status!='archived':
                    if obj.status!='failed': db.add(Audit(actor='system',action=f'归档批次 {obj.code} 失败：{msg[:120]}'))
                    obj.status='failed';obj.error=msg[:480];db.commit()
            else:
                obj=db.get(Trial,int(raw))
                if obj: obj.status='failed';obj.error=str(e);obj.finished_at=datetime.now(timezone.utc);db.commit()
