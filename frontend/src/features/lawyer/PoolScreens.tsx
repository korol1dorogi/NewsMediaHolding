import { type FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ErrorText } from "@/features/cases/CaseLayout";
import { COMPANY_LABELS, factLabel, rub, STATE_LABELS } from "@/features/cases/labels";
import {
  type PoolCard,
  type PoolFilters,
  useLawyerCase,
  useLawyerCases,
  useMakeOffer,
  usePool,
  usePoolCard,
  useStartWork,
  useSubmitWork,
} from "./api";

function range(card: PoolCard) {
  return `${rub(card.amount_range.min_kopecks)} – ${rub(card.amount_range.max_kopecks)}`;
}

function CardSummary({ card }: { card: PoolCard }) {
  return (
    <div className="space-y-1">
      <p>{card.description}</p>
      <p className="text-sm">
        <span className="text-muted">Сумма: </span>
        {range(card)}
        <span className="ml-3 text-muted">Город: </span>
        {card.city}
      </p>
      <p className="text-sm">
        <span className="text-muted">Компания: </span>
        {card.company.name} · {COMPANY_LABELS[card.company.status]}
      </p>
      {card.actions_taken.length > 0 && (
        <p className="text-sm">
          <span className="text-muted">Уже сделано: </span>
          {card.actions_taken.join("; ")}
        </p>
      )}
      <p className="text-sm font-medium" data-testid="similar">
        Похожих обращений: {card.similar_cases.count}
        {card.similar_cases.count > 0 && ` из ${card.similar_cases.cities_count} городов`}
      </p>
    </div>
  );
}

export function PoolScreen() {
  const [city, setCity] = useState("");
  const [minRub, setMinRub] = useState("");
  const [maxRub, setMaxRub] = useState("");
  const filters: PoolFilters = {
    ...(city.trim() ? { city: city.trim() } : {}),
    ...(minRub ? { min_kopecks: Number(minRub) * 100 } : {}),
    ...(maxRub ? { max_kopecks: Number(maxRub) * 100 } : {}),
  };
  const pool = usePool(filters);
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-semibold">Пул обращений</h2>
      <p className="text-sm text-muted">
        Карточки обезличены и проверены модератором. Данные пользователя откроются, только если он
        примет ваше предложение.
      </p>
      <div className="flex flex-wrap gap-3 text-sm">
        <label>
          Город
          <input
            className="ml-2 rounded border p-1"
            value={city}
            onChange={(e) => setCity(e.target.value)}
          />
        </label>
        <label>
          Сумма от, ₽
          <input
            className="ml-2 w-28 rounded border p-1"
            inputMode="numeric"
            value={minRub}
            onChange={(e) => setMinRub(e.target.value.replace(/\D/g, ""))}
          />
        </label>
        <label>
          до, ₽
          <input
            className="ml-2 w-28 rounded border p-1"
            inputMode="numeric"
            value={maxRub}
            onChange={(e) => setMaxRub(e.target.value.replace(/\D/g, ""))}
          />
        </label>
      </div>
      <ErrorText error={pool.error} />
      {pool.data?.items.length === 0 && <p>Подходящих карточек нет.</p>}
      <ul className="space-y-3" aria-label="Пул">
        {pool.data?.items.map((card) => (
          <li key={card.id} className="rounded border p-3">
            <CardSummary card={card} />
            <Link to={`/lawyer/pool/${card.id}`} className="mt-2 inline-block underline">
              Предложить помощь
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

export function PoolCardScreen() {
  const { cardId = "" } = useParams();
  const card = usePoolCard(cardId);
  const offer = useMakeOffer(cardId);
  const [scope, setScope] = useState("");
  const [days, setDays] = useState("14");
  const [price, setPrice] = useState("");
  const [included, setIncluded] = useState("");
  const [excluded, setExcluded] = useState("");

  if (card.isPending) return <p>Загружаем карточку…</p>;
  if (!card.data) return <ErrorText error={card.error} />;
  const valid = scope.trim() && Number(days) >= 1 && Number(price) >= 1;

  async function submit(event: FormEvent) {
    event.preventDefault();
    await offer
      .mutateAsync({
        scope: scope.trim(),
        duration_days: Number(days),
        price_kopecks: Number(price) * 100,
        included: lines(included),
        excluded: lines(excluded),
      })
      .catch(() => null);
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="rounded border p-4">
        <CardSummary card={card.data} />
      </section>
      {offer.isSuccess ? (
        <p role="status">Предложение отправлено. Пользователь увидит его в своём кабинете.</p>
      ) : (
        <form onSubmit={submit} className="space-y-3" aria-label="Предложение">
          <label className="block">
            <span className="text-sm">Что сделаю</span>
            <textarea
              className="mt-1 block min-h-24 w-full rounded border p-2"
              value={scope}
              onChange={(e) => setScope(e.target.value)}
            />
          </label>
          <div className="flex gap-3">
            <label className="block">
              <span className="text-sm">Срок, дней</span>
              <input
                className="mt-1 block w-24 rounded border p-2"
                inputMode="numeric"
                value={days}
                onChange={(e) => setDays(e.target.value.replace(/\D/g, ""))}
              />
            </label>
            <label className="block">
              <span className="text-sm">Цена, ₽</span>
              <input
                className="mt-1 block w-36 rounded border p-2"
                inputMode="numeric"
                value={price}
                onChange={(e) => setPrice(e.target.value.replace(/\D/g, ""))}
              />
            </label>
          </div>
          <label className="block">
            <span className="text-sm">Что входит (по строке)</span>
            <textarea
              className="mt-1 block w-full rounded border p-2"
              value={included}
              onChange={(e) => setIncluded(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm">Что не входит (по строке)</span>
            <textarea
              className="mt-1 block w-full rounded border p-2"
              value={excluded}
              onChange={(e) => setExcluded(e.target.value)}
            />
          </label>
          <ErrorText error={offer.error} />
          <Button type="submit" disabled={!valid || offer.isPending}>
            Отправить предложение
          </Button>
          <p className="text-xs text-muted">
            Сделка — только через платформу: оплата замораживается до приёмки работы.
          </p>
        </form>
      )}
    </div>
  );
}

export function LawyerCasesScreen() {
  const cases = useLawyerCases();
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-semibold">Мои дела</h2>
      <ErrorText error={cases.error} />
      {cases.data?.items.length === 0 && <p>Пока нет дел с принятыми предложениями.</p>}
      <ul className="space-y-2">
        {cases.data?.items.map((item) => (
          <li key={item.id}>
            <Link
              to={`/lawyer/cases/${item.id}`}
              className="block rounded border p-3 hover:bg-border/40"
            >
              {STATE_LABELS[item.state]}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function LawyerCaseScreen() {
  const { caseId = "" } = useParams();
  const query = useLawyerCase(caseId);
  const start = useStartWork(caseId);
  const submit = useSubmitWork(caseId);
  const [result, setResult] = useState("");
  if (query.isPending) return <p>Загружаем дело…</p>;
  if (!query.data) return <ErrorText error={query.error} />;
  const data = query.data;
  const actions = data.case.available_actions;
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Дело: {STATE_LABELS[data.case.state]}</h2>
        <div className="rounded border p-3" data-testid="personal-data">
          <h3 className="font-semibold">Клиент</h3>
          <p>{data.personal_data.full_name}</p>
          <p className="text-sm">{data.personal_data.reply_address}</p>
          <p className="text-sm">Договор: {data.personal_data.contract_reference}</p>
        </div>
        <div className="rounded border p-3 text-sm">
          <h3 className="font-semibold">Карточка</h3>
          <ul>
            {data.card.facts.map((fact) => (
              <li key={fact.key}>
                <span className="text-muted">{factLabel(fact.key)}: </span>
                {fact.value ?? "—"}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded border p-3 text-sm">
          <h3 className="font-semibold">Документы</h3>
          {data.documents.length === 0 && <p className="text-muted">Нет документов.</p>}
          <ul>
            {data.documents.map((doc) => (
              <li key={doc.id}>
                <a
                  className="underline"
                  href={`/api/cases/${data.case.id}/documents/${doc.id}/content`}
                >
                  {doc.filename}
                </a>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <section className="space-y-3">
        <div className="rounded border p-3 text-sm">
          <h3 className="font-semibold">Ваше предложение</h3>
          <p>{data.accepted_offer.scope}</p>
          <p>
            {rub(data.accepted_offer.price_kopecks)} · {data.accepted_offer.duration_days} дн.
          </p>
        </div>
        {data.work && (
          <p role="status">Работа сдана, ждём приёмки пользователем (автоприёмка через 3 дня).</p>
        )}
        <ErrorText error={start.error ?? submit.error} />
        {actions.includes("start_work") && (
          <Button onClick={() => start.mutate(data.case.version)} disabled={start.isPending}>
            Приступить к работе
          </Button>
        )}
        {actions.includes("submit_work") && (
          <form
            className="space-y-2"
            onSubmit={(event) => {
              event.preventDefault();
              submit.mutate({ version: data.case.version, text: result.trim() });
            }}
          >
            <label className="block">
              <span className="text-sm">Результат работы</span>
              <textarea
                className="mt-1 block min-h-32 w-full rounded border p-2"
                value={result}
                onChange={(e) => setResult(e.target.value)}
              />
            </label>
            <Button type="submit" disabled={!result.trim() || submit.isPending}>
              Сдать работу
            </Button>
          </form>
        )}
      </section>
    </div>
  );
}
