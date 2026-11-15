import { type FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { type Fact, has, useCard, useCompany, useConfirmCard, useEditFact } from "./api";
import { ErrorText, useCaseContext } from "./CaseLayout";
import { COMPANY_LABELS, date, factLabel } from "./labels";

function FactRow({ fact, editable }: { fact: Fact; editable: boolean }) {
  const { caseId, caseData } = useCaseContext();
  const edit = useEditFact(caseId);
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const found = fact.status === "found" && fact.source_quote;

  async function save(event: FormEvent) {
    event.preventDefault();
    const saved = await edit
      .mutateAsync({ key: fact.key, value: value.trim(), version: caseData.version })
      .catch(() => null);
    if (saved) setValue("");
  }

  return (
    <li className="rounded border p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm text-muted">
          {factLabel(fact.key)}
          {fact.required && " *"}
        </span>
        {fact.value ? (
          found ? (
            <button
              type="button"
              className="font-medium underline decoration-dotted"
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              {fact.value}
            </button>
          ) : (
            <span className="font-medium">
              {fact.value}
              {fact.status === "user_edited" && (
                <span className="ml-2 text-xs text-muted">уточнено вами</span>
              )}
            </span>
          )
        ) : (
          <span className="text-sm text-amber-700">не найдено — уточните</span>
        )}
      </div>
      {found && open && (
        <blockquote className="mt-2 border-l-4 pl-3 text-sm">
          «{fact.source_quote}»
          <footer className="text-xs text-muted">
            Источник: {fact.source?.kind === "document" ? "загруженный документ" : "ваше сообщение"}
          </footer>
        </blockquote>
      )}
      {editable && !fact.value && (
        <form onSubmit={save} className="mt-2 flex gap-2">
          <input
            aria-label={`Значение: ${factLabel(fact.key)}`}
            className="flex-1 rounded border p-2"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            required
          />
          <Button type="submit" disabled={!value.trim() || edit.isPending}>
            Сохранить
          </Button>
        </form>
      )}
      <ErrorText error={edit.error} />
    </li>
  );
}

function CompanyBlock() {
  const { caseId, caseData } = useCaseContext();
  const company = useCompany(caseId, caseData.card_confirmed_at !== null);
  if (caseData.card_confirmed_at === null) {
    return <p className="text-sm text-muted">Компанию проверим по ИНН после подтверждения.</p>;
  }
  if (company.isPending) return <p className="text-sm">Проверяем компанию…</p>;
  if (!company.data) return <ErrorText error={company.error} />;
  const data = company.data;
  return (
    <div className="text-sm" data-testid="company">
      <p>
        <span className="font-medium">{data.name ?? "Компания"}</span>
        {data.inn && <span className="ml-2 text-muted">ИНН {data.inn}</span>}
      </p>
      <p>
        Статус: <span className="font-medium">{COMPANY_LABELS[data.status]}</span>
        {data.registered_on && `, зарегистрирована ${date(data.registered_on)}`}
      </p>
      {data.is_demo && <p className="text-xs text-muted">Демонстрационная компания</p>}
    </div>
  );
}

export function CardScreen() {
  const { caseId, caseData } = useCaseContext();
  const card = useCard(caseId, caseData.version);
  const confirm = useConfirmCard(caseId);
  const navigate = useNavigate();
  const editable = caseData.state === "card_ready" && caseData.card_confirmed_at === null;

  if (card.isPending) return <p>Загружаем карточку…</p>;
  if (!card.data) return <ErrorText error={card.error} />;
  const missing = card.data.missing_required_fields;
  const canConfirm = has(caseData, "confirm_card") && missing.length === 0;

  async function submit() {
    if (!card.data) return;
    const done = await confirm
      .mutateAsync({ version: caseData.version, cardVersion: card.data.version })
      .catch(() => null);
    if (done) navigate(`/user/cases/${caseId}/paths`);
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_18rem]">
      <section className="space-y-3">
        <p className="text-sm text-muted">
          Нажмите на найденное значение, чтобы увидеть, откуда AI его взял.
        </p>
        {card.data.facts.length === 0 && <p>Фактов пока нет — продолжите диалог.</p>}
        <ul className="space-y-2">
          {card.data.facts.map((fact) => (
            <FactRow key={fact.key} fact={fact} editable={editable} />
          ))}
        </ul>
        {card.data.confirmed_at ? (
          <p role="status">Карточка подтверждена.</p>
        ) : (
          <div className="space-y-2">
            {missing.length > 0 && (
              <p role="alert" className="text-sm text-amber-700">
                Заполните: {missing.map(factLabel).join(", ")}
              </p>
            )}
            <ErrorText error={confirm.error} />
            <Button onClick={submit} disabled={!canConfirm || confirm.isPending}>
              Всё верно, подтвердить
            </Button>
          </div>
        )}
      </section>
      <aside className="space-y-4">
        <div className="rounded border p-3">
          <h3 className="mb-2 font-semibold">Проверка компании</h3>
          <CompanyBlock />
        </div>
        <div className="rounded border p-3 text-sm" data-testid="similar-cases">
          <h3 className="mb-1 font-semibold">Вы не один</h3>
          {card.data.similar_cases ? (
            card.data.similar_cases.count > 0 ? (
              <p>
                По этой компании ещё{" "}
                <span className="font-semibold">{card.data.similar_cases.count}</span> обращений из{" "}
                {card.data.similar_cases.cities_count} городов за{" "}
                {card.data.similar_cases.period_months} мес.
              </p>
            ) : (
              <p className="text-muted">Похожих обращений пока нет.</p>
            )
          ) : (
            <p className="text-muted">Посчитаем после подтверждения карточки.</p>
          )}
        </div>
        <div className="rounded border p-3 text-sm text-muted">
          <h3 className="mb-1 font-semibold text-foreground">Шансы в суде</h3>
          Статистика похожих дел появится, когда будет собран корпус решений.
        </div>
      </aside>
    </div>
  );
}
