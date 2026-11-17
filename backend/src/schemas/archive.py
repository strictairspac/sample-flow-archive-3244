from pydantic import BaseModel
from datetime import datetime
class ArchiveInput(BaseModel):
    cutoff: datetime  # 截止时间：仅圈定此前已结束的演练
