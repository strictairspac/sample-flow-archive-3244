from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.archive import ArchiveInput
from src.services import archives as service
router=APIRouter()
@router.get('/archives')
def listing(db=Depends(db_session),user=Depends(current)): return service.listing(db)
@router.post('/archives',status_code=201)
def create(data:ArchiveInput,db=Depends(db_session),user=Depends(writer)): return service.create(db,data,user)
@router.get('/archives/{ident}')
def detail(ident:int,db=Depends(db_session),user=Depends(current)): return service.detail(db,ident)
@router.post('/archives/{ident}/retry')
def retry(ident:int,db=Depends(db_session),user=Depends(writer)): return service.retry(db,ident,user)
