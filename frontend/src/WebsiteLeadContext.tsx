export type WebsiteContext = {
  form_kind: 'contact' | 'audit'; source_url: string; submitted_at: string;
  contact_text: string | null; website: string | null; privacy_consent: boolean;
  audit_email_consent: boolean; policy_version: string | null; client_type: 'PERSON' | 'COMPANY';
  utm_source: string | null; utm_medium: string | null; utm_campaign: string | null;
  utm_term: string | null; utm_content: string | null;
};
const utmFields = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'] as const;

export default function WebsiteLeadContext({context}: {context: WebsiteContext}) {
  return <details className="websiteLeadContext"><summary>Контекст заявки сайта · {context.form_kind === 'audit' ? 'Аудит' : 'Обращение'}</summary>
    <dl>
      <dt>Источник</dt><dd>{context.source_url}</dd>
      <dt>Отправлена по данным источника</dt><dd><time dateTime={context.submitted_at}>{new Date(context.submitted_at).toLocaleString('ru-RU')}</time></dd>
      <dt>Тип клиента</dt><dd>{context.client_type === 'PERSON' ? 'Частное лицо' : 'Компания, указанная источником'}</dd>
      <dt>Контакт как передал сайт</dt><dd>{context.contact_text || 'Не указан'}</dd>
      <dt>Сайт заявителя</dt><dd>{context.website || 'Не указан'}</dd>
      <dt>Обработка персональных данных</dt><dd>{context.privacy_consent ? 'Согласие заявлено источником' : 'Не заявлено'}</dd>
      <dt>Запрошенный аудит по email</dt><dd>{context.audit_email_consent ? 'Согласие заявлено источником; не рекламная подписка' : 'Согласие не заявлено'}</dd>
      <dt>Версия политики</dt><dd>{context.policy_version || 'Источник не передал версию'}</dd>
      {utmFields.map(field => context[field] ? <div key={field}><dt>{field}</dt><dd>{context[field]}</dd></div> : null)}
    </dl>
    <p className="muted">Сохранённый снимок принятой заявки, а не независимая проверка согласия посетителя. URL и пользовательский текст не выполняются.</p>
  </details>;
}
