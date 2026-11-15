# Модель данных: контракт K1

Контракт доменной модели K1 для будущей реализации B1–B10/S5/S7; accounts.User и LawyerProfile реализованы задачей K2. Доменные модели и их миграции этим описанием не создаются. Имена берутся из [словаря](domain.md), DTO — из [OpenAPI](openapi.yaml). Приватные модели автоматически не сериализуются.

## Общие правила

UUID идентификаторы; UTC ISO8601 для времени, date для календарной даты; суммы в целых копейках RUB без float. Владельца, роль, назначение и оплату определяет сервер. Case.version — версия процесса; Card.version, ClaimVersion.version и assignment_version имеют отдельные области. Команда изменения существующего процесса передаёт expected_version, конфликт — 409 без частичного эффекта. Создание Case не требует ещё не существующей версии; создание Offer проверяется атомарной уникальностью (PoolCard, lawyer) и актуальной доступностью пула, не версией приватного Case. В публичный пул Case.version ради этого не добавляется. Примеры синтетические; ИНН 0000000000 — fixture sentinel, не валидный ИНН реестра и никогда не отправляется внешнему провайдеру.

| Модель | Приложение/задача | Ключевые поля | Владелец и связи | Ограничения |
|---|---|---|---|---|
| User | accounts/K2 | UUID id, username, password hash, role, is_demo; Django auth/session flags | Собственная учётка | AbstractUser; DB CheckConstraint четырёх ролей; AUTH_USER_MODEL=accounts.User, первая миграция accounts/0001; auth endpoint реализованы K2 |
| LawyerProfile | accounts/K2 | user, internal rating | One-to-one User | Модель реализована K2; рейтинг внутренний и через auth/me не выдаётся |
| Case | cases/B1 | owner, state, path, ai_state, version, timestamps | FK owner → User | Назначенный юрист не становится владельцем |
| Message | cases/B1 | case, author, text, created_at | Через Case.owner | Источник неизменяем; повтор failed-сообщения создаёт новое сообщение |
| Document | cases/B1/S4 | case, generated storage name, MIME, size, source version | Через Case.owner | Хранение закрыто; без storage URL в DTO; подтверждённые исходники не заменяются |
| Fact | cases/B2 | case, key, value, source kind/id/version, quote, status | Через Case.owner | Unique(case,key); found/not_found/user_edited; источник только своего дела |
| CardSnapshot | cases/B2 | case, version, frozen facts/source refs, confirmed_at | Через Case.owner | Подтверждённый snapshot неизменяем, цитаты проверены кодом |
| CompanyCheck | companies/B3 | case, inn, status, name, registered_on, source, checked_at, is_demo | Через Case.owner | Снимок; unavailable не означает active |
| Claim | claims/B5 | case, current_version, submitted_at, sent_on, response_due_on, faulty | One-to-one Case | faulty/назначение/оплату клиент не задаёт |
| ClaimVersion | claims/B5/B7 | claim, version, author, template/text, comment, created_at | Через Claim → Case | Unique(claim,version); новая редакция —новая неизменяемая запись |
| ClaimPersonalData | claims/B5 | claim, full_name, reply_address, contract_reference, confirmed | One-to-one Claim | Отдельно от Fact/PoolCard; изменение данных инвалидирует прежнее подтверждение |
| ReviewAssignment | claims/B6 | claim, lawyer, case_version, claim_version, assignment_version, expires_at, ended_at, safe materials snapshot | Текущий назначенный проверяющий | Не более одного активного назначения; take атомарен;4 часа таймаут; faulty-юрист исключён |
| SafeReviewMaterial | claims/documents, вопрос B6/S4 | source document/version, safe rendition, checked flag | Через ReviewAssignment | Требование к будущей выдаче; без готовой безопасной редакции оригинал проверяющему закрыт |
| Hold | payments/B8 | owner, purpose, amount_kopecks, status, reference, idempotency key | Owner+Claim либо Offer | held/released/refunded; атомарный однократный release/refund |
| Allocation | payments/B8 | hold, recipient, amount_kopecks, kind | Через Hold | Сумма распределений равна hold; доли из настроек |
| PoolCard | pool/B9 | private case FK, safe category/description/city/range/company/actions/aggregate, moderation status | Через Case.owner | Одна активная карточка на Case/snapshot; юристам только approved, без private FK/ПД |
| Offer | pool/B10 | pool_card, lawyer, scope, duration_days, price, included/excluded, accepted_at | Юрист создаёт, владелец Case выбирает | Unique(pool_card,lawyer); одно принятое на Case; окно48 часов |
| WorkAssignment | pool/B10 | case, accepted_offer, lawyer, version, active dates | Case.owner и выбранный юрист | Одно активное назначение; согласие+hold до раскрытия |
| WorkSubmission | pool/B10 | assignment, version, text, submitted_at, accepted_at | Через назначение/Case | Версии результата; приёмка просмотренного; автоприёмка3 дня |
| Consent | privacy/S7 | user, kind, text_version, accepted_at, case/claim/offer context | User+конкретное действие | Обработка, передача проверяющему/ведущему —разные основания; сервер не подставляет accepted |
| AccessLog | security/S5 | actor, role, target reference, basis, timestamp | Уполномоченный read-only admin | Без самих ПД/текстов/ключей; полномочия/retention согласует лид |

Карточки плана и нормы A3 —версионированные результаты guidance, без отдельного публичного CRUD. Редакция/споры / реальные платежи не входят в API волн 1–4.

## Состояния

Case.state: draft, clarifying, emergency, card_ready, card_confirmed, self_guided, claim_draft, in_pool, closed, claim_in_review, claim_approved, claim_edited, awaiting_response, resolved, no_response, has_offers, no_offers, offer_accepted, in_progress, work_submitted, completed, disputed. Переходы строго по [машине состояний](state-machine.md); disputed остаётся в enum, хотя споры вне MVP.

Case.ai_state: idle/thinking/failed. Case.path: self_guided/claim/specialist. CompanyCheck.status: active/liquidating/bankrupt/unavailable. PoolCard moderation: pending/approved/rejected. Hold.status: held/released/refunded. Эти enum не дают клиенту права устанавливать их значения.

## Снимки и выдача

Задание AI связано с Case.id и входной version/snapshot. Результат сохраняется условно по версии; поздний ответ не меняет подтверждённые факты. Владелец подтверждает Card.version, конкретную ClaimVersion и персональные данные. Новая версия претензии требует нового подтверждения при соответствующем переходе.

Проверяющий получает отдельный ReviewClaim: шаблон с placeholders вместо контактов, очищенные факты и только безопасные редакции документов. Очередь не получает текст/ПД/исходники. ReviewClaim не ссылается на owner Claim/ClaimPersonalData/Card. Противоречие product.md § 10.5 с персонализированной претензией требует решения до реальной выдачи: отсутствие отдельного phone-поля само по себе не очищает текст или скан.

Выбранный ведущий получает полный LawyerCase лишь по актуальному назначению после согласия/hold. Content-route проверяет родителя и основание; проверяющему только safe rendition, иначе — 404. После завершения бессрочный доступ не предполагается до согласования сроков. Уже скачанные копии отозвать нельзя.

Owner-view Case.pool содержит статус модерации. Юристам выдаётся отдельная замкнутая PoolCard без Case/owner ID, исходников, файлов, generic metadata. specialist лишь выбирает процесс, POST /pool создаёт/переиспользует запись на очистку; видимость отдельно разрешает модератор.

## K2: пользователи и роли

`AUTH_USER_MODEL=accounts.User` задаётся до первой миграции аккаунтов. K2 не переносит старую БД автоматически и не создаёт модели обращений/претензий. UUID согласован с DTO K1. K2 начиналась от main; текущее объединение сохраняет доменную модель и операции K1, а auth добавляется отдельной секцией.

Роли не наследуют полномочия: `IsUser`, `IsLawyer`, `IsModerator`, `IsEditor` проверяют реальную аутентифицированную роль. Они не заменяют фильтрацию queryset по владельцу будущих объектов. В K2 нет production endpoint чужого обращения, поэтому проверка его 404 относится к последующим задачам, а не имитируется тестовым обработчиком.

Активный модератор со staff-флагом может войти в отдельный AdminSite. UserAdmin и Group не зарегистрированы; само назначение роли не создаёт разрешений на просмотр/редактирование чужих персональных данных или повышение привилегий. Будущие доменные задачи регистрируют только scoped moderation модели. `is_superuser` не присваивается командой seed_demo.

Пять demo-записей создаются идемпотентно: два профиля юриста, пользователь, модератор, редактор. Изменённые вручную роли/пароли/рейтинг не перезаписываются повторным запуском. Пароли хешируются Django, никогда не возвращаются через API и не печатаются командой.
