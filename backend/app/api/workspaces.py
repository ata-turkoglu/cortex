import re
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..core.database import SessionLocal
from ..core.workspaces import WorkspaceContext, WorkspaceNotFoundError
from ..models import GraphRagState, Workspace, WorkspaceIndexState, WorkspaceResource
router=APIRouter(prefix="/workspaces",tags=["workspaces"]); SLUG=re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
def get_session():
    session=SessionLocal()
    try: yield session; session.commit()
    except Exception: session.rollback(); raise
    finally: session.close()
class WorkspaceCreate(BaseModel): name:str=Field(min_length=1,max_length=160); slug:str=Field(min_length=1,max_length=80); description:str|None=None
class WorkspaceRead(BaseModel):
    id:str; name:str; slug:str; description:str|None; state:str; created_at:datetime; deleted_at:datetime|None
    model_config={"from_attributes":True}
def lookup(s,id):
    try:return WorkspaceContext.load(s,id).workspace
    except WorkspaceNotFoundError as exc: raise HTTPException(404,"workspace not found") from exc
@router.get("",response_model=list[WorkspaceRead])
def list_workspaces(s:Session=Depends(get_session)): return s.scalars(select(Workspace).where(Workspace.deleted_at.is_(None)).order_by(Workspace.created_at)).all()
@router.post("",response_model=WorkspaceRead,status_code=status.HTTP_201_CREATED)
def create(payload:WorkspaceCreate,s:Session=Depends(get_session)):
    if not SLUG.fullmatch(payload.slug): raise HTTPException(422,"invalid workspace slug")
    if s.scalar(select(Workspace.id).where(Workspace.slug==payload.slug)): raise HTTPException(409,"workspace slug already exists")
    now=datetime.now(timezone.utc); w=Workspace(id=str(uuid4()),**payload.model_dump(),state="active",created_at=now,updated_at=now); s.add(w); base=f"workspaces/{w.id}"
    for typ,name,path in [("qdrant_chunks","cortex_chunks",None),("graphrag_root",None,f"{base}/graphrag"),("cache",None,f"{base}/cache"),("uploads",None,f"{base}/uploads"),("normalized",None,f"{base}/normalized")]: s.add(WorkspaceResource(id=str(uuid4()),workspace_id=w.id,resource_type=typ,logical_name="active",backend_name=name,path=path,active=True,created_at=now))
    s.add(WorkspaceIndexState(workspace_id=w.id,updated_at=now)); s.add(GraphRagState(workspace_id=w.id,graph_root=f"{base}/graphrag",updated_at=now)); s.flush(); return w
@router.get("/{workspace_id}",response_model=WorkspaceRead)
def get(workspace_id:str,s:Session=Depends(get_session)): return lookup(s,workspace_id)
@router.delete("/{workspace_id}",status_code=204)
def delete(workspace_id:str,s:Session=Depends(get_session)):
    w=lookup(s,workspace_id); now=datetime.now(timezone.utc); w.deleted_at=now; w.state="deleting"; w.updated_at=now
    return Response(status_code=204)
