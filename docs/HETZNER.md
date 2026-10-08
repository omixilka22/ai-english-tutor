# Тестування на Hetzner VPS

Стартова оцінка для кількох викладачів: Ubuntu 24.04, x86_64, 2 vCPU,
4 GB RAM. Аудіо обробляє Recall, аналіз — Gemini; GPU не потрібен.
Сервер та домен ще треба створити/підключити. Це не виконаний деплой.

## Підготовка
1. Створіть VPS, додайте SSH-ключ, увімкніть резервні копії.
2. Firewall: TCP 22 лише з вашої IP; TCP 80/443 публічно.
   PostgreSQL та 8001 не публікуються.
3. Встановіть Docker Engine і Compose plugin за офіційною інструкцією:
   https://docs.docker.com/engine/install/ubuntu/
4. Клонуйте приватний репозиторій, перейдіть у папку проєкту.
5. Створіть DNS A-запис піддомену на IPv4 сервера.
   AAAA додавайте лише якщо IPv6 налаштовано.
6. Виконайте:
   cp deploy/server.env.example .env
   chmod 600 .env
   Відредагуйте .env на сервері. BOT_DOMAIN — лише ім’я, без https://.
   Для пароля БД використайте випадковий hex-рядок (openssl rand -hex 32).
   Ключі, які показувалися на скриншотах, замініть перед тестуванням замовником.
   Не комітьте .env.

## Перший запуск із новою базою
Цей сценарій створює порожню базу. Дані Mac автоматично не переносяться.
Для перенесення старих учнів спочатку потрібен окремий pg_dump/restore.

    docker compose -f compose.production.yml config --quiet
    docker compose -f compose.production.yml build
    docker compose -f compose.production.yml up -d postgres
    docker compose -f compose.production.yml run --rm migrate
    docker compose -f compose.production.yml up -d gateway caddy

Перевірте https://ВАШ_ДОМЕН/health — очікується {"status":"ok"}.
Публікується лише app.recall_gateway, не старий CRUD app.main.
Caddy автоматично отримує TLS-сертифікат.

У Recall змініть endpoint на https://ВАШ_ДОМЕН/webhooks/recall,
залиште правильний signing secret та підписки:
recording.done, recording.failed, recording.deleted, transcript.done,
transcript.failed, bot.joining_call, bot.in_waiting_room,
bot.in_call_recording, bot.call_ended, bot.done, bot.fatal.
Після перевірки доставки встановіть RECALL_WEBHOOK_READY=true.

Зупиніть Telegram-бота та його workers на Mac перед запуском серверного:
один токен — лише один polling-процес.

    docker compose -f compose.production.yml up -d bot gateway
    docker compose -f compose.production.yml ps
    docker compose -f compose.production.yml logs --tail=100 bot gateway

Учитель реєструється кодом, додає тестового учня та проводить короткий
урок зі змішаною українською й англійською. Перевірте нагадування,
завершення транскрибації, перевірку аналізу, отримання PDF учнем.

## Оновлення
Спочатку резервна копія, потім:

    git pull --ff-only
    docker compose -f compose.production.yml build
    docker compose -f compose.production.yml stop bot gateway
    docker compose -f compose.production.yml run --rm migrate
    docker compose -f compose.production.yml up -d

Якщо міграція завершується помилкою, не запускайте нову версію до
виправлення. Повернення коду саме по собі не повертає схему БД.

## Резервні копії
Виконуйте щодня та перед оновленням (планувальник ще треба налаштувати):

    mkdir -p backups
    chmod 700 backups
    umask 077
    docker compose -f compose.production.yml exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "backups/database-$(date +%Y%m%d-%H%M%S).dump"

Перевірте успішний exit code та скопіюйте backup за межі VPS.
Перевіряйте відновлення в окремій тестовій БД.
Backups можуть містити тимчасові транскрипти: задайте строк зберігання
та видаляйте прострочені копії. Volume переживає перезапуск, але не
замінює backup. Не виконуйте docker compose down -v — це видалить дані.

## Межі поточної версії
Одна копія bot; не масштабуйте її репліками.
FSM зберігається в пам’яті: після рестарту незавершений діалог починається з /start.
Health gateway перевіряє HTTP-процес, а не успішність Recall/Gemini.
Автоматичний зовнішній моніторинг та розклад backup поки не налаштовані.
