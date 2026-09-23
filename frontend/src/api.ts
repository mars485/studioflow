export type Role = 'OWNER' | 'ADMIN' | 'MANAGER';
export type User = {id: string; email: string; first_name: string};
export type Workspace = {id: string; name: string; currency: string; timezone: string; role: Role};
export type Member = {id: string; user_id: string; email: string; first_name: string; role: Role};
export const roleNames: Record<Role, string> = {OWNER: 'Владелец', ADMIN: 'Администратор', MANAGER: 'Менеджер'};
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {super(message); this.status = status;}
}
export type Client = {id: string; name: string};
export type Stage = {id: string; pipeline_id: string; name: string; position: number; stage_type: string};
export type Pipeline = {id: string; name: string; is_default: boolean; stages: Stage[]};
export type Action = 'call' | 'message' | 'proposal' | 'decision';
export type Deal = {
  id: string; workspace_id: string; title: string; client_id: string;
  pipeline_id: string; stage_id: string; amount: string; currency: string;
  contact_name: string | null; source: string | null; description: string | null;
  follow_up_at: string | null; follow_up_action: Action | null; follow_up_comment: string | null;
  created_at: string; updated_at: string;
};
export type DealInput = Pick<Deal, 'title' | 'client_id' | 'pipeline_id' | 'stage_id' | 'amount' | 'contact_name' | 'source' | 'description'>;

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
