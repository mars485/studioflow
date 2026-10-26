"""Bounded server-to-server envelope; never evaluates source HTML or fetches URLs."""
import re
from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, EmailStr, StrictBool, StringConstraints, field_validator, model_validator

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ProfileUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
PageUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)]
UtmText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
UTM_FIELDS = ('utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content')


class WebsiteContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    form_kind: Literal['contact', 'audit']
    source_url: PageUrl
    submitted_at: AwareDatetime
    contact_text: ShortText | None = None
    website: ProfileUrl | None = None
    privacy_consent: StrictBool
    audit_email_consent: StrictBool = False
    policy_version: ShortText | None = None
    client_type: Literal['PERSON', 'COMPANY']
    utm_source: UtmText | None = None
    utm_medium: UtmText | None = None
    utm_campaign: UtmText | None = None
    utm_term: UtmText | None = None
    utm_content: UtmText | None = None


class WebsiteLeadInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: UUID
    form_kind: Literal['contact', 'audit']
    name: ShortText
    contact: ShortText | None = None
    email: EmailStr | None = None
    website: ProfileUrl | None = None
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)] | None = None
    company_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)] | None = None
    source_url: PageUrl
    submitted_at: AwareDatetime
    privacy_consent: StrictBool
    audit_email_consent: StrictBool = False
    policy_version: ShortText | None = None
    utm_source: UtmText | None = None
    utm_medium: UtmText | None = None
    utm_campaign: UtmText | None = None
    utm_term: UtmText | None = None
    utm_content: UtmText | None = None

    @field_validator('email')
    @classmethod
    def normalize_email(cls, value):
        return value.lower() if value else None

    @field_validator('submitted_at')
    @classmethod
    def utc_timestamp(cls, value):
        return value.astimezone(timezone.utc)

    @field_validator('submitted_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError('Нужна ISO-дата с часовым поясом')
        if isinstance(value, str) and not re.match(r'^\d{4}-\d{2}-\d{2}T', value):
            raise ValueError('Нужна ISO-дата с часовым поясом')
        return value

    @field_validator('website', 'source_url')
    @classmethod
    def safe_url(cls, value, info):
        if value is None:
            return value
        if re.search(r'[\x00-\x20\x7f\\]', value):
            raise ValueError('URL содержит недопустимые символы')
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError('Нужен HTTP(S) URL без логина и пароля')
        # Accessing port also rejects malformed ports; no DNS/HTTP lookup is performed.
        port = parsed.port
        if info.field_name == 'source_url' and (parsed.scheme != 'https' or parsed.hostname != 'itgsystem.ru'
                or port not in (None, 443) or parsed.query or parsed.fragment):
            raise ValueError('Источник должен быть HTTPS-страницей itgsystem.ru без query/fragment')
        return value

    @model_validator(mode='after')
    def required_consents_and_contacts(self):
        if not self.privacy_consent:
            raise ValueError('Нужно согласие на обработку данных')
        if not self.contact and not self.email:
            raise ValueError('Нужен контакт или email')
        if self.form_kind == 'audit' and (not self.email or not self.website or not self.audit_email_consent):
            raise ValueError('Для аудита нужны сайт, email и согласие на запрошенный аудит')
        return self

    def context(self) -> WebsiteContext:
        return WebsiteContext(**self.model_dump(include={
            'form_kind', 'source_url', 'submitted_at', 'website', 'privacy_consent', 'audit_email_consent',
            'policy_version', *UTM_FIELDS}), contact_text=self.contact,
            client_type='COMPANY' if self.company_name else 'PERSON')

    def lead_fields(self):
        phone = None
        if self.contact and re.fullmatch(r'[+0-9().\s-]+', self.contact) and 7 <= len(re.sub(r'\D', '', self.contact)) <= 15 and len(self.contact) <= 50:
            phone = self.contact
        details = [self.message, f'Контакт с сайта: {self.contact}' if self.contact else None,
            f'Сайт заявителя: {self.website}' if self.website else None, f'Страница формы: {self.source_url}']
        return {'request_key': self.request_key,
            'title': ('Запрос аудита: ' if self.form_kind == 'audit' else 'Заявка с сайта: ') + self.name,
            'company_name': self.company_name or self.name, 'contact_first_name': self.name,
            'phone': phone, 'email': self.email, 'message': '\n\n'.join(value for value in details if value),
            'source': 'ITG website / ' + self.form_kind}
