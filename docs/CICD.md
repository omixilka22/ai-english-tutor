# GitHub → Kamatera

Workflow: .github/workflows/ci-deploy.yml.
PR та push master запускають тести, перевірку Compose й Docker build.
Лише успішний master деплоїться. Сам commit без push нічого не запускає.
Деплой спочатку вимкнений: Repository variable DEPLOY_ENABLED має бути true.

## Передумови
Сервер уже налаштований за HETZNER.md і запускає compose.production.yml.
Потрібні bash, git, flock (util-linux), Docker Compose із --wait.
На сервері checkout master без локальних змін; .env і backups ігноруються Git.
Шлях до checkout для workflow — абсолютний, без пробілів.
Один серверний bot на Telegram token. Локального bot зупинити.

## Kamatera: self-hosted runner без SSH-ключів у GitHub
Сервер: 185.237.96.153, користувач deploy.
Checkout: /home/deploy/ai-english-tutor.
Окремий runner отримує завдання через вихідне з’єднання з GitHub.
Відкривати SSH для IP GitHub не потрібно, .env та приватні ключі
не передаються в GitHub. Runner має власний службовий credential,
який зберігається на сервері після реєстрації.

1. Застосуйте пакет локально, закомітьте три файли, push master.
   Перевірте зелений test job; deploy вимкнений, доки DEPLOY_ENABLED не true.
2. Увійдіть: ssh deploy@185.237.96.153
3. Перевірте:
       cd /home/deploy/ai-english-tutor
       git status --short
       git fetch origin master
       docker compose version
       docker compose -f compose.production.yml ps
   Робоче дерево має бути чистим; не видаляйте місцеві правки без розбору.
4. У GitHub репозиторії: Settings → Actions → Runners → New self-hosted runner.
   Оберіть Linux та архітектуру сервера (uname -m).
   Workflow налаштований на x64; для ARM змініть x64 на ARM64.
5. Створіть /home/deploy/actions-runner, виконайте в ньому актуальні команди
   завантаження/перевірки й config.sh, які показує GitHub.
   Виконуйте config.sh від deploy, не root.
   Registration token із GitHub використовуйте лише в SSH-терміналі.
   Додайте label teacher-bot-production; runner group — Default.
   Робоча папка runner має бути окремою від checkout бота.
6. Встановіть службу з папки actions-runner:
       sudo ./svc.sh install deploy
       sudo ./svc.sh start
       sudo ./svc.sh status
   У GitHub runner має стати Idle.
7. Settings → Secrets and variables → Actions → Variables:
   Repository variable DEPLOY_ENABLED=true.
   Додавати Repository secrets для цього workflow НЕ потрібно.
8. Actions → Test and deploy → Run workflow → master.
   Наступні push master деплояться автоматично.

Сервер уже має працюючий доступ git fetch до origin; він потрібен runner'у.
Користувач deploy має доступ до Docker без sudo (це фактично root-доступ).
Цей runner виконує код із master із доступом до сервера та .env.
Надавайте push/merge у master лише довіреним людям.
Не запускайте PR jobs на цьому runner і не використовуйте його для сторонніх
workflow. Для публічного репозиторію спочатку окремо оцініть ізоляцію runner;
рекомендований сценарій тут — приватний репозиторій із довіреними авторами.
Захистіть master обов’язковими перевірками перед merge, якщо тариф дозволяє.
Встановлювати runner або змінювати налаштування GitHub цей пакет сам не буде.

## Що робить deploy
Серверне блокування flock і concurrency GitHub не допускають одночасних деплоїв.
Якщо origin/master вже новіший, старий workflow пропускає деплой.
Fast-forward до перевіреного SHA, build до зупинки програми, pg_dump,
зупинка bot/gateway, міграція, recreate gateway/bot, reload Caddy, smoke checks.
Виникне коротка перерва, FSM-діалоги скинуться. Перші деплої робіть поза уроками.
Не редагуйте файли checkout напряму на сервері: це блокує наступний деплой.

## Помилки та відновлення
Build/backup failure: програма ще не зупинена, workflow червоний.
Migration failure: bot/gateway залишаться зупиненими, потрібна діагностика.
Автоматичного rollback схеми немає. Не робіть alembic downgrade навмання.
Зупинка runner/таймаут: перевірте ps і логи перед повторенням; rollback не гарантований.
Backup: backups/pre-deploy-*.dump (лише серверна копія).
Окремо потрібні off-site backup та retention: цей пакет їх не налаштовує.
Не видаляйте volume.
Smoke check перевіряє HTTP gateway й стабільний процес bot, але не наскрізний
урок, Telegram API або доступність Gemini/Recall.
DEPLOY_ENABLED=false вимикає наступні деплої, не зупиняючи поточний бот.

Важливо: тести/збірка на GitHub і реальний серверний деплой ще мають бути виконані.
