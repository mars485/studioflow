import hashlib
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from app.models import Client, ClientMerge, ContactClient, Deal, IncomingLead, Invoice, Project
from app.services.audit import audit_deal, deal_snapshot

PROFILE_FIELDS = ('name', 'phone', 'email', 'website', 'notes')
REFERENCES = {'deals': Deal, 'projects': Project, 'invoices': Invoice, 'incoming_leads': IncomingLead}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def profile(row):
    return {'id': str(row.id), 'type': row.type, **{key: getattr(row, key) for key in PROFILE_FIELDS},
        'created_at': row.created_at.isoformat(), 'updated_at': row.updated_at.isoformat()}


async def merge_snapshot(db, workspace_id, source_id, target_id):
    # A fixed order prevents opposite-direction merges from taking opposite parent locks.
    clients = (await db.scalars(select(Client).where(Client.workspace_id == workspace_id,
        Client.id.in_([source_id, target_id])).order_by(Client.id).with_for_update()
        .execution_options(populate_existing=True))).all()
    if len(clients) != 2:
        raise HTTPException(404, 'Компания не найдена')
    by_id = {row.id: row for row in clients}
    source, target = by_id[source_id], by_id[target_id]
    if source.type != target.type:
        raise HTTPException(409, 'Нельзя объединять клиентов разных типов')
    snapshot = {'source': profile(source), 'target': profile(target), 'references': {}}
    for key, model in REFERENCES.items():
        rows = (await db.execute(select(model.id, model.client_id).where(model.workspace_id == workspace_id,
            model.client_id.in_([source_id, target_id])).order_by(model.id).with_for_update())).all()
        snapshot['references'][key] = {
            'source': [str(row.id) for row in rows if row.client_id == source_id],
            'target': [str(row.id) for row in rows if row.client_id == target_id]}
    links = (await db.execute(select(ContactClient.contact_id, ContactClient.client_id).where(
        ContactClient.workspace_id == workspace_id, ContactClient.client_id.in_([source_id, target_id]))
        .order_by(ContactClient.contact_id, ContactClient.client_id).with_for_update())).all()
    snapshot['references']['contacts'] = {
        'source': [str(row.contact_id) for row in links if row.client_id == source_id],
        'target': [str(row.contact_id) for row in links if row.client_id == target_id]}
    return source, target, snapshot


def preview_out(snapshot):
    return {'source': snapshot['source'], 'target': snapshot['target'], 'preview_version': digest(snapshot),
        'counts': {key: {'source': len(value['source']), 'target': len(value['target'])}
                   for key, value in snapshot['references'].items()}}


def receipt_out(row):
    return {'id': row.id, 'request_key': row.request_key, 'source_id': row.source_id, 'target_id': row.target_id,
        'actor_name': row.actor_name, 'created_at': row.created_at, 'source_fields': row.source_fields,
        'snapshot': row.snapshot}


async def apply_merge(db, workspace_id, user, data):
    # Called only after the workspace/membership lock (also serializes idempotency keys).
    request_digest = digest(data.model_dump(mode='json', exclude={'request_key'}))
    previous = await db.scalar(select(ClientMerge).where(ClientMerge.workspace_id == workspace_id,
        ClientMerge.request_key == data.request_key))
    if previous is not None:
        if previous.request_digest != request_digest:
            raise HTTPException(409, 'Этот ключ запроса уже использован с другими параметрами')
        return receipt_out(previous)
    source, target, snapshot = await merge_snapshot(db, workspace_id, data.source_id, data.target_id)
    if digest(snapshot) != data.preview_version:
        raise HTTPException(409, 'Карточки или связи изменились. Обновите предпросмотр и подтвердите заново')
    for field in data.source_fields:
        setattr(target, field, getattr(source, field))
    # Keep the existing deal audit meaningful even though these changes are not made via PATCH.
    deals = (await db.scalars(select(Deal).where(Deal.workspace_id == workspace_id, Deal.client_id == source.id))).all()
    for deal in deals:
        before = deal_snapshot(deal)
        deal.client_id = target.id
        audit_deal(db, deal, 'UPDATED', user=user, before=before)
    await db.flush()
    for model in (Project, Invoice, IncomingLead):
        await db.execute(update(model).where(model.workspace_id == workspace_id, model.client_id == source.id)
            .values(client_id=target.id))
    # Preserve the union of contact relationships; do not duplicate an already-shared contact.
    for contact_id in snapshot['references']['contacts']['source']:
        await db.execute(insert(ContactClient).values(workspace_id=workspace_id, client_id=target.id,
            contact_id=UUID(contact_id)).on_conflict_do_nothing())
    await db.execute(delete(ContactClient).where(ContactClient.workspace_id == workspace_id,
        ContactClient.client_id == source.id))
    receipt = ClientMerge(workspace_id=workspace_id, request_key=data.request_key, request_digest=request_digest,
        source_id=source.id, target_id=target.id, actor_id=user.id,
        actor_name=' '.join(filter(None, (user.first_name, user.last_name)))[:255],
        snapshot=snapshot, source_fields=sorted(data.source_fields))
    db.add(receipt)
    await db.delete(source)
    await db.commit()
    await db.refresh(receipt)
    return receipt_out(receipt)
