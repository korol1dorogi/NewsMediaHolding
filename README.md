# Сервис обращений

Сервис холдинга NMH: человек пишет о том, что его обманули или нарушили его права, и за несколько минут получает карточку случая, проверку компании и понятный следующий шаг.

```bash
cp .env.example .env && docker compose up -d --build --wait   # затем http://localhost:8080
```

## Главное

*Заполняется к сдаче: проблема, решение, роль AI, преимущество холдинга — по 1–2 предложения.*

## Что посмотреть за 10 минут

*Заполняется к сдаче: сценарий демо по шагам со ссылками на экраны.*

1. Открыть http://localhost:8080.
2. …

## Как закрыты критерии и требования

Полные таблицы — в [docs/judging.md](docs/judging.md) и [docs/case.md](docs/case.md).

| Критерий | Чем закрываем |
|---|---|
| *заполнить к сдаче* | |

## Если что-то не так

| Симптом | Что сделать |
|---|---|
| `docker compose up` падает на `backend` | `docker compose logs backend`; чаще всего не поднялась база — `docker compose down -v` и снова `up` |
| Порт 8080 занят | В `.env` поменять `WEB_PORT`, а в `CSRF_TRUSTED_ORIGINS` — порт в адресе |
| На главной «API: недоступно» | Проверить http://localhost:8080/api/ready — покажет, какая зависимость не отвечает |

## Учётки

Демо-учётки создаются явно после миграций:

```bash
docker compose exec backend python manage.py seed_demo
```

| Логин | Роль | Переменная пароля | Локальная заглушка |
|---|---|---|---|
| `demo_anya` | Пользователь | `DEMO_USER_PASSWORD` | `demo-user-placeholder` |
| `demo_lawyer_1`, `demo_lawyer_2` | Юристы | `DEMO_LAWYER_PASSWORD` | `demo-lawyer-placeholder` |
| `demo_moderator` | Модератор | `DEMO_MODERATOR_PASSWORD` | `demo-moderator-placeholder` |
| `demo_editor` | Редактор | `DEMO_EDITOR_PASSWORD` | `demo-editor-placeholder` |

Это синтетические аккаунты, а значения выше — публичные локальные заглушки. Для собственного стенда задайте пароли через окружение. Повтор `seed_demo` не сбрасывает изменённые пароли, роли и рейтинг. Явный `seed_demo --reset-passwords` обновляет только пароли существующих демо-аккаунтов из текущих настроек. При совпадении имени с обычной учёткой команда завершается без частичных изменений.

API входа: сначала `GET /api/auth/csrf`, затем `POST /api/auth/login` с JSON username/password и заголовком `X-CSRFToken`. Cookie сессии HttpOnly, вход ротирует CSRF cookie; для выхода нужен актуальный token. `GET /api/auth/me` возвращает только текущую учётку, `POST /api/auth/logout` завершает её сессию. JWT и регистрация не добавлены.

Админка: `/admin/` на том же origin. Вход только активному `moderator` с `is_staff`. Роль не даёт `superuser` или права менять пользователей/группы; доменные задачи позже регистрируют только нужные модератору модели. Статика админки собирается бэкендом в отдельный volume, Caddy получает его только для чтения. Пользовательские файлы в этот volume не попадают.

Лимит входа `AUTH_LOGIN_ATTEMPTS` за `AUTH_LOGIN_WINDOW_SECONDS` секунд применяется независимо по IP и нормализованному имени. Счётчики общего Redis работают между процессами Gunicorn. При недоступности cache вход возвращает 503; malformed JSON тоже расходует IP-лимит. Значения пользователей/пароли не пишутся в ключах и логах.

`AUTH_TRUST_PROXY_HEADER=true` допустим только для комплектного Caddy ingress: он **перезаписывает** `X-NMH-Client-IP` адресом подключившегося клиента, а порт backend наружу не публикуется. Произвольные `X-Forwarded-For` не используются. При прямом запуске Django настройка по умолчанию false: применяется `REMOTE_ADDR`. Если публикуете backend напрямую или добавляете внешний прокси перед Caddy, сначала пересмотрите границу доверия, а не включайте доверие к входным заголовкам автоматически.

После уже выполненных миграций старой схемы нельзя переключать существующую рабочую БД на custom User автоматически. Для K2 используйте отдельный compose project и новую БД; действующие данные не сбрасывайте. Контракт сохраняет все 41 операции K1 и добавляет 4 операции `/api/auth/*`; клиент перегенерирован из объединённой схемы.

## Архитектура

```
браузер ──> Caddy (web, :8080) ──/api/*──> Django + DRF (backend) ──> PostgreSQL (db)
                 │                                │
                 └── статика фронта (React)       └──> Redis ──> Celery (worker)
```

- Один origin: фронт и API отдаёт Caddy, поэтому сессии и CSRF работают без CORS.
- Контракт API — [docs/openapi.yaml](docs/openapi.yaml); клиент фронта генерируется из него.
- LLM — через OpenAI-совместимый API; по умолчанию детерминированный мок.

Решения и их причины — в [docs/decisions.md](docs/decisions.md).

## Конфигурация

Все переменные — в [.env.example](.env.example). Пустая или отсутствующая переменная берёт значение по умолчанию из `backend/config/settings.py`.

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `WEB_PORT` | `8080` | Порт приложения на хосте |
| `LLM_PROVIDER` | `mock` | `mock` или OpenAI-совместимый провайдер |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | пусто | Настройки реальной модели |

## Как проверить качество

```bash
docker compose run --rm backend sh -c "pip install -r requirements-dev.txt && ruff check . && pytest"
cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build
scripts/check-clean-clone.sh    # чистый клон: compose, /api/ready, e2e smoke, newman
```

CI на каждый PR: бэкенд, фронтенд, e2e, newman, gitleaks, pip-audit, npm audit — [.github/workflows/ci.yml](.github/workflows/ci.yml).

## Ограничения и допущения

См. [docs/assumptions.md](docs/assumptions.md).
