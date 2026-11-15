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

*Заполняется к сдаче: тестовые пользователи для жюри.*

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
| `PAYMENTS_PROVIDER` | `demo` | Провайдер оплаты. Есть только `demo`: **оплата — демонстрация**, реальные деньги не списываются |
| `PAYMENTS_CLAIM_PRICE_KOPECKS` | `149000` | Цена претензии в копейках (ориентир 1 490 ₽) |
| `PAYMENTS_REVIEWER_SHARE_BP` | `7000` | Доля юриста-проверяющего в базисных пунктах (70%) |
| `PAYMENTS_PLATFORM_FEE_BP` | `1000` | Комиссия платформы со сделки с юристом (10%) |

## Как проверить качество

```bash
docker compose run --rm backend sh -c "pip install -r requirements-dev.txt && ruff check . && pytest"
cd frontend && npm ci && npm run lint && npm run typecheck && npm test && npm run build
scripts/check-clean-clone.sh    # чистый клон: compose, /api/ready, e2e smoke, newman
```

CI на каждый PR: бэкенд, фронтенд, e2e, newman, gitleaks, pip-audit, npm audit — [.github/workflows/ci.yml](.github/workflows/ci.yml).

## Ограничения и допущения

**Оплата — демонстрация.** Заморозка денег (`backend/apps/payments`) показывает механику «деньги заморожены до приёмки работы» без платёжного провайдера и без реальных денег.

См. [docs/assumptions.md](docs/assumptions.md).
