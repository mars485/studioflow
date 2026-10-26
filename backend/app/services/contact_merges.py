from fastapi import HTTPException
from sqlalchemy import delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.api.v1.crm import assign_primary_contact
from app.models import Contact, ContactClient, ContactMerge, Deal, DealContact, ProjectContact, Task
from app.services.audit import audit_deal, deal_snapshot
from app.services.client_merges import digest, receipt_out

PROFILE_FIELDS = ('first_name', 'last_name', 'middle_name', 'phone', 'email', 'website', 'notes')


def profile(row):
    return {'id': str(row.id), **{key: getattr(row, key) for key in PROFILE_FIELDS},
        'created_at': row.created_at.isoformat(), 'updated_at': row.updated_at.isoformat()}


async def merge_snapshot(db, workspace_id, source_id, target_id):
    contacts = (await db.scalars(select(Contact).where(Contact.workspace_id == workspace_id,
        Contact.id.in_([source_id, target_id])).order_by(Contact.id).with_for_update()
        .execution_options(populate_existing=True))).all()
    if len(contacts) != 2:
        raise HTTPException(404, 'Контакт не найден')
    by_id = {row.id: row for row in contacts}
    source, target = by_id[source_id], by_id[target_id]
    snapshot = {'source': profile(source), 'target': profile(target), 'references': {}}
    for key, model, identity in (('companies', ContactClient, ContactClient.client_id),
                                  ('projects', ProjectContact, ProjectContact.project_id), ('tasks', Task, Task.id)):
        rows = (await db.execute(select(identity.label('object_id'), model.contact_id).where(
            model.workspace_id == workspace_id, model.contact_id.in_([source_id, target_id]))
            .order_by(identity, model.contact_id).with_for_update())).all()
        snapshot['references'][key] = {
            'source': [str(row.object_id) for row in rows if row.contact_id == source_id],
            'target': [str(row.object_id) for row in rows if row.contact_id == target_id]}
    linked_deals = select(DealContact.deal_id).where(DealContact.workspace_id == workspace_id,
        DealContact.contact_id.in_([source_id, target_id]))
    deals = (await db.scalars(select(Deal).where(Deal.workspace_id == workspace_id,
        or_(Deal.contact_id.in_([source_id, target_id]), Deal.id.in_(linked_deals)))
        .order_by(Deal.id).with_for_update().execution_options(populate_existing=True))).all()
    links = (await db.scalars(select(DealContact).where(DealContact.workspace_id == workspace_id,
        DealContact.deal_id.in_([row.id for row in deals])).order_by(DealContact.deal_id, DealContact.contact_id)
        .with_for_update().execution_options(populate_existing=True))).all()
    # Do not silently repair a pre-existing divergent primary pointer while deleting an identity.
    for deal in deals:
        primaries = [link.contact_id for link in links if link.deal_id == deal.id and link.is_primary]
        if primaries != ([] if deal.contact_id is None else [deal.contact_id]):
            raise HTTPException(409, 'Основной контакт сделки несогласован. Сначала исправьте связи сделки')
    snapshot['references']['deals'] = {
        side: sorted({str(link.deal_id) for link in links if link.contact_id == object_id})
        for side, object_id in (('source', source_id), ('target', target_id))}
    snapshot['references']['primary_deals'] = {
        side: [str(deal.id) for deal in deals if deal.contact_id == object_id]
        for side, object_id in (('source', source_id), ('target', target_id))}
    snapshot['deal_links'] = [{'deal_id': str(link.deal_id), 'contact_id': str(link.contact_id),
        'is_primary': link.is_primary, 'created_at': link.created_at.isoformat()} for link in links]
    snapshot['deal_state'] = [{'id': str(deal.id), 'contact_id': str(deal.contact_id) if deal.contact_id else None,
        'contact_name': deal.contact_name, 'updated_at': deal.updated_at.isoformat()} for deal in deals]
    return source, target, deals, snapshot


async def apply_merge(db, workspace_id, user, data):
    request_digest = digest(data.model_dump(mode='json', exclude={'request_key'}))
    previous = await db.scalar(select(ContactMerge).where(ContactMerge.workspace_id == workspace_id,
        ContactMerge.request_key == data.request_key))
    if previous is not None:
        if previous.request_digest != request_digest:
            raise HTTPException(409, 'Этот ключ запроса уже использован с другими параметрами')
        return receipt_out(previous)
    source, target, deals, snapshot = await merge_snapshot(db, workspace_id, data.source_id, data.target_id)
    if digest(snapshot) != data.preview_version:
        raise HTTPException(409, 'Карточки или связи изменились. Обновите предпросмотр и подтвердите заново')
    for field in data.source_fields:
        setattr(target, field, getattr(source, field))
    await db.flush()
    for model, identity in ((ContactClient, 'client_id'), (ProjectContact, 'project_id')):
        rows = (await db.scalars(select(model).where(model.workspace_id == workspace_id,
            model.contact_id == source.id))).all()
        for row in rows:
            values = {'workspace_id': workspace_id, 'contact_id': target.id, identity: getattr(row, identity)}
            if isinstance(row, ProjectContact):
                values['created_at'] = row.created_at
            await db.execute(insert(model).values(**values).on_conflict_do_nothing())
        await db.execute(delete(model).where(model.workspace_id == workspace_id, model.contact_id == source.id))
    for deal in deals:
        before = deal_snapshot(deal)
        source_links = [row for row in snapshot['deal_links'] if row['deal_id'] == str(deal.id) and row['contact_id'] == str(source.id)]
        if source_links:
            await db.execute(insert(DealContact).values(workspace_id=workspace_id, deal_id=deal.id,
                contact_id=target.id, is_primary=False).on_conflict_do_nothing())
        await db.execute(delete(DealContact).where(DealContact.workspace_id == workspace_id,
            DealContact.deal_id == deal.id, DealContact.contact_id == source.id))
        if deal.contact_id in (source.id, target.id):
            await assign_primary_contact(db, deal, target.id)
        audit_deal(db, deal, 'UPDATED', user=user, before=before)
    await db.flush()
    await db.execute(update(Task).where(Task.workspace_id == workspace_id, Task.contact_id == source.id)
        .values(contact_id=target.id))
    receipt = ContactMerge(workspace_id=workspace_id, request_key=data.request_key, request_digest=request_digest,
        source_id=source.id, target_id=target.id, actor_id=user.id,
        actor_name=' '.join(filter(None, (user.first_name, user.last_name)))[:255], snapshot=snapshot,
        source_fields=sorted(data.source_fields))
    db.add(receipt)
    await db.delete(source)
    await db.commit()
    await db.refresh(receipt)
    return receipt_out(receipt)
