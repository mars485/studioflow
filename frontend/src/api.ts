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
  utm_source: string | null; utm_medium: string | null; utm_campaign: string | null;
  utm_term: string | null; utm_content: string | null; http_referrer: string | null;
  follow_up_at: string | null; follow_up_action: Action | null; follow_up_comment: string | null;
  created_at: string; updated_at: string;
};
export type DealInput = Pick<Deal, 'title' | 'client_id' | 'contact_id' | 'pipeline_id' | 'stage_id' | 'responsible_user_id' | 'amount' | 'contact_name' | 'source' | 'description' | 'start_date' | 'end_date'>;
export type DealActivity = {id: string; deal_id: string; author_user_id: string | null; author_name: string; body: string; kind: ActivityKind; created_at: string;
  recipient_user_id?: string | null; recipient_name?: string | null};
export type DealTask = {id: string; workspace_id: string; deal_id: string; title: string; description: string | null;
  priority: 'LOW' | 'MEDIUM' | 'HIGH'; status: 'OPEN' | 'DONE'; assignee_user_id: string | null;
  created_by_user_id: string | null; completed_by_user_id: string | null;
  start_at: string | null; due_at: string | null; created_at: string; updated_at: string; completed_at: string | null};
export type TaskReminder = {id: string; workspace_id: string; task_id: string; recipient_user_id: string;
  created_by_user_id: string | null; kind: 'DATE' | 'START_OFFSET' | 'DUE_OFFSET'; at: string | null;
  offset_minutes: number | null; trigger_at: string | null; acknowledged_at: string | null; created_at: string};
export type DueTaskReminder = TaskReminder & {deal_id: string; deal_title: string; task_title: string};
export type MyDay = {tasks: {task: DealTask; deal_title: string}[];
  follow_ups: {deal_id: string; deal_title: string; at: string; action: Action; comment: string | null}[]};
export type FollowUpCompletion = {id: string; deal_id: string; completed_by_user_id: string | null; completed_by_name: string; scheduled_at: string; action: Action; planned_comment: string | null; outcome_comment: string | null; completed_at: string};
export type ActivityKind = 'NOTE' | 'STAGE_CHANGE' | 'EVENT' | 'MENTION';
export type DealTag = {id: string; name: string; created_at: string};
export type DealWatcher = {user_id: string; first_name: string; last_name: string | null; email: string};
export type DealContactLink = {contact_id: string; is_primary: boolean; first_name: string; last_name: string | null;
  middle_name: string | null; phone: string | null; email: string | null};
export type DealAttachment = {id: string; filename: string; content_type: string; size_bytes: number;
  uploaded_by_user_id: string | null; uploaded_by_name: string; created_at: string; has_content: boolean; sha256: string | null};
export type CustomFieldType = 'TEXT' | 'NUMBER' | 'DATE';
export type DealCustomField = {key: string; type: CustomFieldType; value: string};
export const activityKindNames: Record<ActivityKind, string> = {NOTE: 'Комментарий', EVENT: 'Событие', MENTION: 'Призвать к ответу', STAGE_CHANGE: 'Смена стадии'};
export type TaskStatus = {id: string; name: string; position: number; is_final: boolean};
export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH';
export type Task = {id: string; workspace_id: string; title: string; description: string | null;
  status_id: string; status_name: string; is_final: boolean; priority: TaskPriority;
  assignee_user_id: string | null; creator_user_id: string | null; completed_by_user_id: string | null;
  start_at: string | null; due_at: string | null; estimate_minutes: number | null;
  deal_id: string | null; project_id: string | null; contact_id: string | null; parent_task_id: string | null;
  completed_at: string | null; created_at: string; updated_at: string;
  checklist_done: number; checklist_total: number};
export type TaskChecklistItem = {id: string; task_id: string; text: string; is_done: boolean; position: number; created_at: string};
export const taskPriorityNames: Record<TaskPriority, string> = {LOW: 'Низкий', MEDIUM: 'Средний', HIGH: 'Высокий'};
export type ProjectStage = {id: string; name: string; position: number};
export type ProjectStatus = 'ACTIVE' | 'ARCHIVED' | 'COMPLETED';
export type Project = {id: string; workspace_id: string; title: string; client_id: string; deal_id: string | null;
  stage_id: string; stage_name: string; manager_user_id: string | null; amount: string; currency: string;
  start_date: string | null; end_date: string | null; status: ProjectStatus; archived_at: string | null;
  created_at: string; updated_at: string; tasks_total: number; tasks_done: number; members_count: number};
export type ProjectMember = {user_id: string; first_name: string; last_name: string | null; email: string; role: 'LEAD' | 'MEMBER'};
export type ProjectContact = {contact_id: string; first_name: string; last_name: string | null; middle_name: string | null;
  phone: string | null; email: string | null};
export type ProjectEvent = {id: string; kind: string; body: string; author_name: string; created_at: string};
export const projectStatusNames: Record<ProjectStatus, string> = {ACTIVE: 'Активный', ARCHIVED: 'В архиве', COMPLETED: 'Завершён'};

export async function request<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const binary = body instanceof Blob;
  const response = await fetch(`/api/v1${path}`, {
    method, signal, credentials: 'same-origin', headers: {
      ...(body === undefined ? {} : {'Content-Type': binary ? (body.type || 'application/octet-stream') : 'application/json'}),
      ...(['GET', 'HEAD'].includes(method) ? {} : {'X-StudioFlow-Request': '1'}),
    },
    body: body === undefined ? undefined : binary ? body : JSON.stringify(body),
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

export function newRequestKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function loadDeals(base: string, signal?: AbortSignal): Promise<Deal[]> {
  const result: Deal[] = [];
  for (let offset = 0; ; offset += 500) {
    const page = await request<Deal[]>(`${base}/deals?limit=500&offset=${offset}`, 'GET', undefined, signal);
    result.push(...page);
    if (page.length < 500) return result;
  }
}

export async function loadTasks(base: string, signal?: AbortSignal, filters: Record<string, string> = {}): Promise<Task[]> {
  const result: Task[] = [];
  for (let offset = 0; ; offset += 500) {
    const params = new URLSearchParams({...filters, limit: '500', offset: String(offset)});
    const page = await request<Task[]>(`${base}/tasks?${params}`, 'GET', undefined, signal);
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
