# START HERE

## 1. Поднять проект

Нужен Docker с Compose. Node 22 и Python 3.12 — только для работы вне контейнеров.

```bash
git clone https://github.com/korol1dorogi/NewsMediaHolding.git
cd NewsMediaHolding
cp .env.example .env
docker compose up -d --build --wait
```

Открыть http://localhost:8080 — на главной должно быть «API: ok».

## 2. Прочитать

1. `AGENTS.md` — правила работы, обязательно.
2. `docs/mvp.md` — что делаем в прототипе.
3. `docs/tasks.md` — найти свою задачу.
4. `docs/openapi.yaml` — контракт.

## 3. Работа без Docker

```bash
# бэкенд: нужны Postgres и Redis из compose
docker compose up -d db redis
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
POSTGRES_HOST=localhost pytest

# фронтенд: /api проксируется на http://localhost:8080
cd frontend
npm ci
npm run dev
```

Для бэкенда без Docker порты `db` наружу не проброшены — проще запускать тесты внутри контейнера:
`docker compose run --rm backend sh -c "pip install -r requirements-dev.txt && pytest"`.

## 4. Промт первой сессии для своего ИИ-агента

Скопируйте и подставьте ID задачи:

```text
Ты работаешь в репозитории команды хакатона. Прочитай AGENTS.md целиком и следуй ему.
Моя задача — <ID> из docs/tasks.md. Прочитай её карточку, docs/mvp.md и docs/openapi.yaml.

Порядок:
1. Перескажи задачу своими словами и перечисли, какие файлы тронешь. Если в карточке
   чего-то не хватает — спроси, не додумывай. Жди моего «ок».
2. Создай ветку <ID>-<кратко>. Если меняется API — сначала правка docs/openapi.yaml
   и `npm run gen:api` во frontend/.
3. Пиши код маленькими коммитами на английском. На каждый эндпоинт с данными
   пользователя — тест «чужой получает 404».
4. Прогони проверки из AGENTS.md и покажи вывод.
5. Подготовь описание PR по шаблону .github/pull_request_template.md.

Не добавляй зависимости, не трогай чужие задачи, не клади секреты.
```
