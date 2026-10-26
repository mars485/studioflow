from fastapi import HTTPException
from sqlalchemy import select

from app.models import EmployeeGroupBlock, EmployeeGroupMember, Workspace, WorkspaceMember


async def blocked_actions(db, workspace_id, user_id):
    rows = (await db.scalars(select(EmployeeGroupBlock.action).join(EmployeeGroupMember,
        (EmployeeGroupMember.workspace_id == EmployeeGroupBlock.workspace_id) &
        (EmployeeGroupMember.group_id == EmployeeGroupBlock.group_id)).where(
        EmployeeGroupMember.workspace_id == workspace_id, EmployeeGroupMember.user_id == user_id).distinct())).all()
    return set(rows)


def required_actions(path):
    """Classify workspace-relative business paths; None means unknown, never implicit allow."""
    parts = path.strip('/').split('/')
    root = parts[0]
    if root in ('groups', 'group-permissions', 'members') or not path.strip('/'):
        return set()
    if root in ('client-merges', 'contact-merges'):
        if parts[-1] == 'preview':
            return set()
        actions = {'clients.write', 'crm.write', 'tasks.write', 'projects.write'}
        if root == 'client-merges':
            actions |= {'finance.write', 'integrations.write'}
        return actions
    if root == 'deals':
        return {'crm.write', 'tasks.write'} if 'tasks' in parts[2:3] else {'crm.write'}
    if root in ('pipelines', 'tags'):
        return {'crm.write'}
    if root in ('clients', 'contacts'):
        return {'clients.write'}
    if root in ('tasks', 'task-statuses', 'reminders', 'time-entries'):
        return {'tasks.write'}
    if root in ('projects', 'project-stages', 'project-templates'):
        return {'projects.write'}
    if root in ('organizations', 'invoices', 'acts'):
        return {'finance.write'}
    if root in ('integration-tokens', 'integration-leads', 'webhooks'):
        return {'integrations.write'}
    if root == 'notifications':
        return set()  # Personal read acknowledgements do not edit the referenced deal.
    return None


async def enforce_request_blocks(request, member, db):
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    # Serialize every mutation with group and membership changes, and re-read stale authority.
    await db.scalar(select(Workspace.id).where(Workspace.id == member.workspace_id).with_for_update())
    current = await db.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == member.workspace_id,
        WorkspaceMember.user_id == member.user_id).execution_options(populate_existing=True))
    if current is None:
        raise HTTPException(404, 'Workspace not found')
    if current.role == 'OWNER':
        return
    blocked = await blocked_actions(db, current.workspace_id, current.user_id)
    if not blocked:
        return
    prefix = f'/api/v1/workspaces/{current.workspace_id}'
    relative = request.url.path.removeprefix(prefix)
    needed = required_actions(relative)
    if needed is None or needed & blocked:
        raise HTTPException(403, 'Изменение запрещено настройками группы сотрудников')


async def enforce_token_blocks(db, token):
    # lead_token already owns the workspace lock and checks current issuer membership/role.
    role = await db.scalar(select(WorkspaceMember.role).where(WorkspaceMember.workspace_id == token.workspace_id,
        WorkspaceMember.user_id == token.created_by_user_id))
    if role != 'OWNER' and {'crm.write', 'clients.write', 'integrations.write'} & await blocked_actions(db, token.workspace_id, token.created_by_user_id):
        raise HTTPException(403, 'Приём заявок запрещён настройками группы автора токена')
