"""Explicit, local-only demo setup through the public API; never a startup hook."""

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from http.cookiejar import CookieJar
import ipaddress
import json
import os
from pathlib import Path
import secrets
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener
from uuid import NAMESPACE_URL, uuid5

EMAIL = "demo@studioflow.example.com"
WORKSPACE = "IT GROUP · Демо (учебные данные)"
NOTICE = "ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ. Вымышленные компании, контакты, суммы и оплаты."


def local_url(value):
    parts = urlsplit(value)
    try:
        loopback = parts.hostname == "localhost" or ipaddress.ip_address(parts.hostname).is_loopback
    except (ValueError, TypeError):
        loopback = False
    if (parts.scheme != "http" or not loopback or parts.username or parts.password
            or parts.path not in ("", "/") or parts.query or parts.fragment):
        raise ValueError("Demo setup accepts only an explicit loopback HTTP origin, never a remote target")
    return value.rstrip("/")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Demo setup refuses redirects")


class APIError(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Demo API request failed (HTTP {status}); no existing data was removed")


class API:
    def __init__(self, origin):
        self.origin = local_url(origin)
        self.http = build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())

    def request(self, method, path, data=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("API paths must be local")
        body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        req = Request(self.origin + "/api/v1" + path, data=body, method=method,
                      headers={"Content-Type": "application/json", "X-StudioFlow-Request": "1"})
        try:
            with self.http.open(req, timeout=30) as response:
                result = response.read()
                return json.loads(result) if result else None
        except HTTPError as exc:
            # Do not echo request bodies, cookies, credentials or server diagnostics.
            raise APIError(exc.code) from None


def save_state(path, state):
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def credentials(path):
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("email") != EMAIL or len(state.get("password", "")) < 20:
            raise ValueError("Not a StudioFlow demo credentials file")
        return state
    state = {"email": EMAIL, "password": secrets.token_urlsafe(24), "entities": {}}
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
    return state


def seed(api, state, persist, now=None):
    """Only this dedicated demo account/workspace is writable. Reruns add no duplicates."""
    now = (now or datetime.now(timezone.utc)).replace(hour=12, minute=0, second=0, microsecond=0)
    auth = {"email": state["email"], "password": state["password"]}
    if auth["email"] != EMAIL:
        raise ValueError("Only the dedicated demo account is supported")
    try:
        user = api.request("POST", "/auth/register", {**auth, "first_name": "Алексей · Демо"})
    except APIError as exc:
        if exc.status != 409:
            raise
        user = api.request("POST", "/auth/login", auth)
    if user["email"] != EMAIL:
        raise ValueError("Unexpected account; setup stopped")
    spaces = api.request("GET", "/workspaces")
    workspace = next((row for row in spaces if row["id"] == state.get("workspace_id")), None)
    if state.get("workspace_id") and workspace is None:
        raise ValueError("Recorded demo workspace is inaccessible; it will not be recreated")
    fresh = workspace is None
    if fresh:
        if spaces:
            raise ValueError("Demo account already has untracked workspaces; refusing to change them")
        workspace = api.request("POST", "/workspaces", {"name": WORKSPACE})
        state["workspace_id"] = workspace["id"]
        persist()
    if workspace["name"] != WORKSPACE or workspace["role"] != "OWNER":
        raise ValueError("Expected the dedicated demo workspace with OWNER access")
    base = "/workspaces/" + workspace["id"]
    entities = state.setdefault("entities", {})

    def ensure(key, suffix, data, query=""):
        rows = api.request("GET", base + suffix + query)
        if key in entities:
            row = next((item for item in rows if item["id"] == entities[key]), None)
            if row is None:
                raise ValueError(f"Demo entry {key} was removed; refusing to restore it silently")
            return row, False
        natural = next((field for field in ("title", "name", "description") if field in data), None)
        if natural and any(item.get(natural) == data[natural] for item in rows):
            raise ValueError(f"Untracked demo entry {key}; refusing to duplicate or overwrite it")
        row = api.request("POST", base + suffix, data)
        entities[key] = row["id"]
        persist()
        return row, True

    pipelines = api.request("GET", base + "/pipelines")
    if len(pipelines) != 1:
        raise ValueError("Demo pipeline was changed; automatic setup stopped")
    pipeline = pipelines[0]
    stages = sorted(pipeline["stages"], key=lambda row: row["position"])
    if len(stages) != 4:
        raise ValueError("Demo stages were changed; automatic setup stopped")
    if fresh:
        for stage, name, color in zip(stages, ["Новые обращения", "В работе", "Успешно", "Не реализовано"],
                                      ["#e31e24", "#df9a73", "#6b9e84", "#aaaab4"]):
            api.request("PATCH", base + f"/pipelines/{pipeline['id']}/stages/{stage['id']}", {"name": name, "color": color})
    companies = []
    people = []
    for i, (company, first, last) in enumerate([
        ("Демо · Альфа Групп", "Мария", "Волкова"), ("Демо · Студия Форма", "Александр", "Иванов"),
        ("Демо · ТехноЛайн", "Елена", "Смирнова"), ("Демо · Север", "Дмитрий", "Петров"),
        ("Демо · Архитектура", "Анна", "Соколова"),
    ]):
        company_row, _ = ensure(f"company-{i}", "/clients", {"name": company, "email": f"company{i}@example.com", "notes": NOTICE})
        contact, _ = ensure(f"contact-{i}", "/contacts", {"first_name": first, "last_name": last,
            "email": f"contact{i}@example.com", "client_ids": [company_row["id"]], "notes": NOTICE})
        companies.append(company_row)
        people.append(contact)
    deals = []
    titles = ["Корпоративный сайт", "SEO-продвижение", "Интернет-магазин", "Редизайн сайта", "Поддержка сайта",
              "Лендинг для запуска", "Разработка портала", "Каталог продукции", "Сайт девелопера", "Аудит интерфейса", "Продвижение услуг", "Личный кабинет"]
    stage_indexes = [0, 0, 1, 1, 1, 0, 2, 2, 2, 3, 3, 1]
    for i, title in enumerate(titles):
        deal, created = ensure(f"deal-{i}", "/deals", {"title": "Демо · " + title, "client_id": companies[i % 5]["id"],
            "contact_id": people[i % 5]["id"], "pipeline_id": pipeline["id"], "stage_id": stages[stage_indexes[i]]["id"],
            "responsible_user_id": user["id"], "amount": str([180000, 65000, 420000, 210000, 45000, 95000, 680000, 260000, 350000, 40000, 75000, 520000][i]),
            "source": ["Демо · Сайт", "Демо · Рекомендация", "Демо · Звонок"][i % 3], "description": NOTICE + " Обсудить задачи и согласовать следующий этап.",
            "start_date": (now - timedelta(days=8)).date().isoformat(), "end_date": (now + timedelta(days=20)).date().isoformat()}, "?limit=500")
        deals.append(deal)
        if created:
            if stage_indexes[i] < 2 and i % 3 != 1:
                api.request("PUT", base + f"/deals/{deal['id']}/follow-up", {"at": (now + timedelta(days=[-2, 0, 2, 0][i % 4])).isoformat(),
                    "action": ["call", "proposal", "decision"][i % 3], "comment": "Демо: уточнить обратную связь и следующий шаг."})
            api.request("POST", base + f"/deals/{deal['id']}/activities", {"kind": "NOTE", "body": "Демо: встреча проведена, требования зафиксированы. " + NOTICE})
            if i == 0:
                api.request("POST", base + f"/deals/{deal['id']}/activities", {"kind": "MENTION", "recipient_user_id": user["id"],
                    "body": "Демо: прототип готов к обсуждению. Проверьте комментарии перед встречей."})
    project_stages = api.request("GET", base + "/project-stages")
    projects = []
    for i, deal_index in enumerate([6, 7, 8]):
        project, _ = ensure(f"project-{i}", "/projects", {"title": deals[deal_index]["title"], "deal_id": deals[deal_index]["id"],
            "stage_id": project_stages[min(i, len(project_stages) - 1)]["id"], "start_date": (now - timedelta(days=5)).date().isoformat(),
            "end_date": (now + timedelta(days=25)).date().isoformat()}, "?status=all")
        projects.append(project)
    statuses = api.request("GET", base + "/task-statuses")
    for i, title in enumerate(["Собрать требования", "Подготовить концепцию", "Согласовать прототип", "Проверить адаптив", "Обновить контент",
                               "Провести SEO-аудит", "Сверстать главную", "Протестировать формы", "Передать проект клиенту"]):
        status = statuses[i % len(statuses)]
        ensure(f"task-{i}", "/tasks", {"title": "Демо · " + title, "description": NOTICE, "status_id": status["id"],
            "priority": ["HIGH", "MEDIUM", "LOW"][i % 3], "assignee_user_id": user["id"], "project_id": projects[i % 3]["id"],
            "deal_id": deals[[6, 7, 8][i % 3]]["id"], "start_at": (now - timedelta(days=3)).isoformat(),
            "due_at": (now + timedelta(days=i - 2)).isoformat(), "estimate_minutes": [120, 240, 60][i % 3]}, "?limit=500")
    organization, _ = ensure("organization", "/organizations", {"name": "Демо · IT GROUP (не для оплаты)", "address": "Учебные реквизиты. Не использовать для реальных документов."})
    for i in range(4):
        invoice, created = ensure(f"invoice-{i}", "/invoices", {"organization_id": organization["id"], "client_id": companies[i]["id"],
            "issued_on": now.date().isoformat(), "amount": str([180000, 65000, 420000, 95000][i]), "manager_user_id": user["id"],
            "description": f"Демо · Услуги веб-студии {i + 1}. НЕ ДЛЯ ОПЛАТЫ. " + NOTICE}, "?limit=500")
        if created and i:
            api.request("PATCH", base + f"/invoices/{invoice['id']}", {"state": "ISSUED"})
            if i > 1:
                api.request("POST", base + f"/invoices/{invoice['id']}/payments", {"request_key": str(uuid5(NAMESPACE_URL, invoice["id"] + ":demo-payment")),
                    "paid_on": now.date().isoformat(), "amount": str(Decimal(invoice["amount"]) / (2 if i == 2 else 1)),
                    "method": "DEMO", "comment": "Учебная запись, не реальное поступление"})
    return {"workspace_id": workspace["id"], "workspace": WORKSPACE, "email": EMAIL, "companies": 5, "contacts": 5, "deals": 12, "projects": 3, "tasks": 9, "invoices": 4}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--credentials-file", type=Path, required=True, help="Private JSON outside the repository; keep it for safe reruns")
    parser.add_argument("--confirm-local-demo", action="store_true")
    args = parser.parse_args()
    if not args.confirm_local_demo:
        parser.error("Explicit --confirm-local-demo is required; never point a local tunnel at production")
    api = API(args.base_url)
    path = args.credentials_file.resolve()
    source_root = Path(__file__).resolve().parents[1]
    repository_root = source_root.parent if (source_root.parent / "frontend").is_dir() else source_root
    if repository_root in path.parents:
        parser.error("Credentials must be stored outside the repository")
    state = credentials(path)
    try:
        result = seed(api, state, lambda: save_state(path, state))
        print(json.dumps({**result, "credentials_file": str(path)}, ensure_ascii=False, indent=2))
    finally:
        try:
            api.request("POST", "/auth/logout")
        except (APIError, OSError):
            pass


if __name__ == "__main__":
    main()
