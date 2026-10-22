export type Role = 'OWNER' | 'ADMIN' | 'MANAGER';
export type User = {id: string; email: string; first_name: string};
export type Workspace = {id: string; name: string; currency: string; timezone: string; role: Role};
export type Member = {id: string; user_id: string; email: string; first_name: string; role: Role};
export const roleNames: Record<Role, string> = {OWNER: 'Владелец', ADMIN: 'Администратор', MANAGER: 'Менеджер'};
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {super(message); this.status = status;}
}
export type Client = {id: string; type: string; name: string; phone: string | null; email: string | null; website: string | null; notes: string | null};
export type Contact = {id: string; workspace_id: string; first_name: string; last_name: string | null; middle_name: string | null;
  phone: string | null; email: string | null; website: string | null; notes: string | null; client_ids: string[];
  created_at: string; updated_at: string};
export const contactName = (contact: Contact) => [contact.last_name, contact.first_name, contact.middle_name].filter(Boolean).join(' ');
export type Stage = {id: string; pipeline_id: string; name: string; position: number; stage_type: 'OPEN' | 'WON' | 'LOST'; color: string | null};
export type Pipeline = {id: string; name: string; is_default: boolean; is_active: boolean; stages: Stage[]};
export type Action = 'call' | 'message' | 'proposal' | 'decision';
export type Deal = {
  id: string; workspace_id: string; title: string; client_id: string;
  contact_id: string | null;
  pipeline_id: string; stage_id: string; responsible_user_id: string | null; amount: string; currency: string;
  contact_name: string | null; source: string | null; description: string | null;
  start_date: string | null; end_date: string | null;
  follow_up_at: string | null; follow_up_action: Action | null; follow_up_comment: string | null;
  created_at: string; updated_at: string;
};
export type DealInput = Pick<Deal, 'title' | 'client_id' | 'contact_id' | 'pipeline_id' | 'stage_id' | 'responsible_user_id' | 'amount' | 'contact_name' | 'source' | 'description' | 'start_date' | 'end_date'>;
export type DealActivity = {id: string; deal_id: string; author_user_id: string | null; author_name: string; body: string; kind: 'NOTE' | 'STAGE_CHANGE'; created_at: string};
export type DealTask = {id: string; workspace_id: string; deal_id: string; title: string; description: string | null;
  priority: 'LOW' | 'MEDIUM' | 'HIGH'; status: 'OPEN' | 'DONE'; assignee_user_id: string | null;
  created_by_user_id: string | null; completed_by_user_id: string | null;
  start_at: string | null; due_at: string | null; created_at: string; updated_at: string; completed_at: string | null};
export type MyDay = {tasks: {task: DealTask; deal_title: string}[];
  follow_ups: {deal_id: string; deal_title: string; at: string; action: Action; comment: string | null}[]};
export type FollowUpCompletion = {id: string; deal_id: string; completed_by_user_id: string | null; completed_by_name: string; scheduled_at: string; action: Action; planned_comment: string | null; outcome_comment: string | null; completed_at: string};

export async function request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method, signal, credentials: 'same-origin', headers: {
      ...(body === undefined ? {} : {'Content-Type': 'application/json'}),
      ...(['GET', 'HEAD'].includes(method) ? {} : {'X-StudioFlow-Request': '1'}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = typeof data?.detail === 'string' ? data.detail :
      Array.isArray(data?.detail) ? data.detail.map((item: {msg: string}) => item.msg).join('; ') : '';
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('session-expired'));
    throw new ApiError(response.status, `Не удалось выполнить запрос (${response.status}). ${detail}`);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export async function loadDeals(base: string, signal?: AbortSignal): Promise<Deal[]> {
  const result: Deal[] = [];
  for (let offset = 0; ; offset += 500) {
    const page = await request<Deal[]>(`${base}/deals?limit=500&offset=${offset}`, 'GET', undefined, signal);
    result.push(...page);
    if (page.length < 500) return result;
  }
}

export const errorText = (error: unknown) => error instanceof Error ? error.message : 'Не удалось сохранить изменения';
export const money = (amount: string | number, currency: string) =>
  new Intl.NumberFormat('ru-RU', {style: 'currency', currency, maximumFractionDigits: 2}).format(Number(amount));

// datetime-local uses browser local time; the API requires an explicit offset.
export function localDateTime(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
