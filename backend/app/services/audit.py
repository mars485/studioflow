from app.models.audit import DealAudit


def deal_snapshot(deal):
    # Only used transiently to detect changes; values are never persisted to the audit.
    return {column.key: getattr(deal, column.key) for column in deal.__table__.columns
            if column.key not in ('id', 'workspace_id', 'created_at', 'updated_at')}


def audit_deal(db, deal, action, *, user=None, token=None, before=None):
    fields = sorted(key for key, value in deal_snapshot(deal).items()
                    if before is not None and before[key] != value)
    if action == 'UPDATED' and not fields:
        return
    db.add(DealAudit(workspace_id=deal.workspace_id, deal_id=deal.id, action=action, fields=fields,
        actor_id=token.id if token is not None else user.id,
        actor_kind='INTEGRATION' if token is not None else 'USER',
        actor_name='Интеграция' if token is not None else ' '.join(filter(None, (user.first_name, user.last_name)))[:255]))
