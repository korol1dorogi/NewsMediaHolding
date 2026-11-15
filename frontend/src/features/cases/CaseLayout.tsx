import { type FormEvent, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { type CaseDetail, useCase, useCases, useCreateCase } from "./api";
import { STATE_LABELS } from "./labels";
import { appendText, VoiceInput } from "./VoiceInput";

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-red-700">
      {error instanceof Error ? error.message : "Не удалось выполнить запрос."}
    </p>
  );
}

export function CasesList() {
  const cases = useCases();
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Мои обращения</h2>
        <Link to="/user/new" className="rounded-md bg-primary px-4 py-2 text-primary-foreground">
          Новое обращение
        </Link>
      </div>
      {cases.isPending && <p>Загружаем…</p>}
      <ErrorText error={cases.error} />
      {cases.data?.items.length === 0 && <p>Обращений пока нет.</p>}
      <ul className="space-y-2">
        {cases.data?.items.map((item) => (
          <li key={item.id}>
            <Link
              to={`/user/cases/${item.id}`}
              className="block rounded border p-3 hover:bg-border/40"
            >
              <span className="font-medium">{STATE_LABELS[item.state]}</span>
              <span className="ml-3 text-sm text-muted">
                от {new Date(item.created_at).toLocaleDateString("ru-RU")}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function NewCase() {
  const [text, setText] = useState("");
  const [consent, setConsent] = useState(false);
  const create = useCreateCase();
  const navigate = useNavigate();
  async function submit(event: FormEvent) {
    event.preventDefault();
    const created = await create.mutateAsync(text.trim()).catch(() => null);
    if (created) navigate(`/user/cases/${created.id}`);
  }
  return (
    <form onSubmit={submit} className="max-w-2xl space-y-4">
      <h2 className="text-xl font-semibold">Расскажите, что случилось</h2>
      <label className="block">
        <span className="text-sm">
          Что произошло, с какой компанией, когда и сколько вы заплатили
        </span>
        <textarea
          className="mt-1 block min-h-40 w-full rounded border p-2"
          value={text}
          onChange={(event) => setText(event.target.value)}
          required
        />
      </label>
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={consent}
          onChange={(event) => setConsent(event.target.checked)}
        />
        <span>
          Согласен на обработку сведений об обращении. Персональные данные никому не передаются без
          отдельного согласия.
        </span>
      </label>
      <VoiceInput onText={(spoken) => setText((current) => appendText(current, spoken))} />
      <ErrorText error={create.error} />
      <Button type="submit" disabled={!consent || !text.trim() || create.isPending}>
        Отправить
      </Button>
    </form>
  );
}

const TABS = [
  { to: "", label: "Диалог", end: true },
  { to: "card", label: "Карточка" },
  { to: "paths", label: "Пути решения" },
  { to: "claim", label: "Претензия" },
  { to: "specialist", label: "Юрист" },
];

export type CaseContext = { caseId: string; caseData: CaseDetail };

export function useCaseContext() {
  return useOutletContext<CaseContext>();
}

export function CaseLayout() {
  const { caseId = "" } = useParams();
  const query = useCase(caseId);
  if (query.isPending) return <p>Загружаем обращение…</p>;
  if (query.error || !query.data) {
    return (
      <section className="space-y-2">
        <ErrorText error={query.error ?? new Error("Обращение не найдено.")} />
        <Link to="/user" className="underline">
          К списку обращений
        </Link>
      </section>
    );
  }
  const context: CaseContext = { caseId, caseData: query.data };
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-xl font-semibold">Обращение</h2>
        <span className="rounded border px-2 py-0.5 text-sm" data-testid="case-state">
          {STATE_LABELS[query.data.state]}
        </span>
      </div>
      <nav aria-label="Шаги обращения" className="flex flex-wrap gap-2 border-b pb-2">
        {TABS.map((tab) => (
          <NavLink
            key={tab.label}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) =>
              `rounded px-3 py-1 ${isActive ? "bg-primary text-primary-foreground" : "hover:bg-border/40"}`
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet context={context} />
    </section>
  );
}
