# Развёртывание на VPS

Production использует отдельный `docker-compose.production.yml`: PostgreSQL без внешнего порта, API без reload и публикации порта, собранный React и Caddy. Dev-конфигурация не меняется. Нужны Docker Engine и Compose plugin.

## Отдельный сервер без внешнего reverse proxy

1. Направьте домен на VPS и откройте TCP 80/443. Если перед VPS уже есть прокси, сначала согласуйте маршрутизацию и завершение TLS; не меняйте существующий DNS вслепую.
2. Скопируйте `.env.production.example` в `.env.production`. Задайте `DOMAIN` без протокола и пути. Сгенерируйте отдельный пароль PostgreSQL, например `openssl rand -hex 32`, и внесите его в файл. Не используйте пароль локальной базы. Ограничьте доступ: `chmod 600 .env.production`.
3. Соберите и запустите:

```sh
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
docker compose --env-file .env.production -f docker-compose.production.yml ps -a
```

`migrate` должен завершиться с кодом 0 до запуска API. Caddy получает и продлевает TLS-сертификат, сохраняя его в отдельном volume. API принимает cookie только по HTTPS, разрешённый Origin соответствует домену. Uvicorn доверяет proxy-заголовкам только потому, что его порт недоступен извне и private-сеть выделена для этого приложения; не публикуйте порт API.

4. Проверьте HTTPS, `/api/v1/health`, регистрацию, создание студии и сохранение сделки после перезагрузки. Для новой пустой базы используйте регистрацию и создайте студию в настройках. `app.bootstrap` нужен только при переносе старого локального аккаунта.

## Существующий NPMplus перед VPS

DNS остаётся направленным на NPMplus. Маршрут: браузер → HTTPS NPMplus → HTTPS Caddy на VPS:443 → API:8000 → PostgreSQL:5432. Только Caddy публикует порты; база и API находятся в отдельной внутренней Docker-сети.

В `.env.production` задайте `DOMAIN=crm.karpiev.ru`, `TRUSTED_PROXY=94.41.128.114`. На VPS `94.198.219.216` нужен `ENABLE_IPV6=true`: в ходе установки исходящий HTTPS к центру сертификации работал по IPv6, но не по IPv4. Эта настройка включает IPv6 только для внешней Docker-сети веб-сервера. Caddy принимает IP клиента только от заданного прокси и передаёт вычисленный адрес API для ограничения попыток входа.

Для независимого обновления сертификатов NPMplus и Caddy добавьте в Advanced **только хоста CRM**:

```nginx
location ~ ^/\.well-known/acme-challenge/ {
    root /data;
    try_files /tls/certbot/acme-challenge$uri /letsencrypt-acme-challenge$uri @studioflow_acme;
}
location @studioflow_acme {
    proxy_pass http://94.198.219.216:80;
    proxy_set_header Host crm.karpiev.ru;
}
```

Сначала проверяется локальный файл Certbot NPMplus (поддержаны старый и новый пути), затем запрос проверки передаётся Caddy. Caddy использует HTTP-01; порт 80 VPS должен оставаться доступным для этих проверок. Проверьте фактический каталог Certbot при смене версии NPMplus.

После получения сертификата Caddy переключите Destination CRM на `https://94.198.219.216:443`, сохраните существующий сертификат домена и Force HTTPS. Добавьте проверку сертификата upstream:

```nginx
proxy_ssl_server_name on;
proxy_ssl_name crm.karpiev.ru;
proxy_ssl_verify on;
proxy_ssl_verify_depth 3;
proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;
```

Проверьте `/api/v1/health` через домен и напрямую с SNI: `curl --resolve crm.karpiev.ru:443:94.198.219.216 https://crm.karpiev.ru/api/v1/health`. Не отключайте проверку TLS для обхода ошибок.

При сетевой ошибке сборки на VPS можно передать образы, собранные на Linux/amd64 через Docker Desktop: `docker save`, затем `scp` и `docker load`. После загрузки используйте `up -d --no-build`. Храните соответствующую версию исходников вместе с release-образами. Пароль базы генерируется на VPS и не входит в архив исходников или образов.

## Обновление и резервная копия

Перед миграцией сделайте резервную копию. Команды ниже выполняются в Linux на VPS; файл дампа содержит данные пользователей, храните его с ограниченным доступом и копируйте в отдельное защищённое хранилище.

```sh
mkdir -p backups
chmod 700 backups
umask 077
docker compose --env-file .env.production -f docker-compose.production.yml exec -T db \
  pg_dump -U studioflow -d studioflow -Fc > "backups/studioflow-$(date +%Y%m%d-%H%M%S).dump"
```

Проверяйте код завершения pg_dump. Наличие файла само по себе не подтверждает успешную копию. Периодически проверяйте восстановление в отдельной тестовой базе.

После получения проверенной версии повторите `up --build -d`. При неуспешной миграции изучите логи `migrate`; не удаляйте volume и не запускайте автоматический downgrade. Для отката схемы используйте проверенную резервную копию и соответствующую версию приложения. Перезапуск и обычный `down` сохраняют данные; `down -v` удаляет базу и сертификаты.

`.env.production`, дампы и закрытые ключи не должны попадать в Git. Публикация исходников не заменяет запуск на VPS и проверку домена.
