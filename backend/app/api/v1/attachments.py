import hashlib
import unicodedata
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import current_user, workspace_access
from app.api.v1.crm import find_deal, lock_deal
from app.api.v1.schemas import DealAttachmentOut
from app.core.config import settings
from app.core.database import get_db
from app.core.http import read_limited_body
from app.models import DealAttachment, User, Workspace
from app.models.entities import DealAttachmentContent

router = APIRouter(prefix="/workspaces/{workspace_id}/deals/{deal_id}/attachments", tags=["Attachments"])


def safe_filename(filename: str) -> str:
    name = filename.strip()
    if not name or name in (".", "..") or any(char in '/\\' or unicodedata.category(char).startswith('C') for char in filename):
        raise HTTPException(422, "Имя файла не должно содержать путь или управляющие символы")
    return name


@router.post("/upload", response_model=DealAttachmentOut, status_code=201)
async def upload(deal_id: UUID, request: Request, filename: str = Query(min_length=1, max_length=255),
                 upload_key: UUID = Query(), workspace_id: UUID = Depends(workspace_access),
                 user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    filename = safe_filename(filename)
    await find_deal(db, workspace_id, deal_id)
    data = await read_limited_body(request, settings.attachment_max_bytes)
    digest = hashlib.sha256(data).hexdigest()
    # All writers for the quota and upload keys serialize on the same row.
    await db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    await lock_deal(db, workspace_id, deal_id)
    existing = await db.scalar(select(DealAttachment).where(DealAttachment.workspace_id == workspace_id,
                                                           DealAttachment.upload_key == upload_key))
    if existing is not None:
        if existing.deal_id != deal_id or existing.sha256 != digest or existing.filename != filename:
            raise HTTPException(409, "Ключ загрузки уже использован для другого файла")
        return existing
    used = await db.scalar(select(func.coalesce(func.sum(DealAttachment.size_bytes), 0)).where(
        DealAttachment.workspace_id == workspace_id, DealAttachment.sha256.is_not(None)))
    if used + len(data) > settings.attachment_workspace_quota_bytes:
        raise HTTPException(413, "Превышена квота файлов студии")
    # Client MIME is descriptive only; downloads always use octet-stream + attachment.
    content_type = request.headers.get("content-type", "application/octet-stream").split(';', 1)[0].strip()
    if not content_type or len(content_type) > 100 or not content_type.isascii():
        content_type = "application/octet-stream"
    row = DealAttachment(workspace_id=workspace_id, deal_id=deal_id, filename=filename, content_type=content_type,
        size_bytes=len(data), sha256=digest, upload_key=upload_key, uploaded_by_user_id=user.id,
        uploaded_by_name=" ".join(filter(None, (user.first_name, user.last_name))))
    db.add(row)
    await db.flush()
    db.add(DealAttachmentContent(workspace_id=workspace_id, attachment_id=row.id, data=bytes(data)))
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/{attachment_id}/download")
async def download(deal_id: UUID, attachment_id: UUID, workspace_id: UUID = Depends(workspace_access),
                   db: AsyncSession = Depends(get_db)):
    await find_deal(db, workspace_id, deal_id)
    row = (await db.execute(select(DealAttachment, DealAttachmentContent.data).join(DealAttachmentContent,
        (DealAttachmentContent.workspace_id == DealAttachment.workspace_id) &
        (DealAttachmentContent.attachment_id == DealAttachment.id)).where(DealAttachment.workspace_id == workspace_id,
        DealAttachment.deal_id == deal_id, DealAttachment.id == attachment_id))).first()
    if row is None:
        raise HTTPException(404, "Содержимое файла не найдено; старые вложения могут содержать только метаданные")
    attachment, data = row
    return Response(content=data, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename=download; filename*=UTF-8''{quote(attachment.filename, safe='')}",
        "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox", "Cache-Control": "no-store"})
