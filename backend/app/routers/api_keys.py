"""Router for API key management."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.auth import get_current_user
from app.crud import api_key_crud
from app.db import get_session
from app.models.models import User

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class CreateKeyRequest(BaseModel):
    name: str


class CreateKeyResponse(BaseModel):
    id: str
    name: str
    key: str  # shown once


class KeyInfo(BaseModel):
    id: str
    name: str
    created_at: str


@router.post("", response_model=CreateKeyResponse)
def create_key(
    body: CreateKeyRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    api_key, raw_key = api_key_crud.create_api_key(session, str(user.id), body.name)
    return CreateKeyResponse(id=str(api_key.id), name=api_key.name, key=raw_key)


@router.get("", response_model=list[KeyInfo])
def list_keys(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    keys = api_key_crud.list_keys(session, str(user.id))
    return [KeyInfo(id=str(k.id), name=k.name, created_at=str(k.created_at)) for k in keys]


@router.delete("/{key_id}")
def revoke_key(
    key_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ok = api_key_crud.revoke_key(session, key_id, str(user.id))
    return {"revoked": ok}
