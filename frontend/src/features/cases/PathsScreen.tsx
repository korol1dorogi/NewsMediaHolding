import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { type CasePath, has, type Plan, useChoosePath, usePaths, usePlan } from "./api";
import { ErrorText, useCaseContext } from "./CaseLayout";
import { date, days, rub } from "./labels";

const WHAT_YOU_GET: Record<CasePath, string> = {
  self_guided: "Пошаговый план: какие документы собрать, куда и в какие сроки обратиться.",
  claim: "Досудебная претензия от вашего имени. Её проверит юрист, отправите вы сами.",
  specialist: "Юристы увидят обезличенную карточку и предложат помощь и цену.",
};

function copy(text: string) {
  void globalThis.navigator?.clipboard?.writeText(text).catch(() => undefined);
}

function PlanView({ plan }: { plan: Plan }) {
  const [copied, setCopied] = useState<number | null>(null);
  return (
    <section className="space-y-3" aria-label="План «Реши сам»">
      <h3 className="text-lg font-semibold">План «Реши сам»</h3>
      <ol className="space-y-3">
        {plan.steps.map((step) => (
          <li key={step.order} className="rounded border p-3">
            <div className="flex items-start justify-between gap-3">
              <p>
                <span className="mr-2 font-semibold">{step.order}.</span>
                {step.text}
              </p>
              <Button
                variant="outline"
                onClick={() => {
                  copy(step.text);
                  setCopied(step.order);
                }}
              >
                {copied === step.order ? "Скопировано" : "Копировать"}
              </Button>
            </div>
            <p className="mt-2 text-sm">
              <span className="text-muted">Куда: </span>
              {step.destination}
              {step.due_on && (
                <>
                  <span className="ml-3 text-muted">Срок: </span>
                  {date(step.due_on)}
                </>
              )}
            </p>
            {step.documents.length > 0 && (
              <p className="text-sm">
                <span className="text-muted">Документы: </span>
                {step.documents.join("; ")}
              </p>
            )}
            {step.norms.map((norm) => (
              <p key={norm.id} className="text-sm">
                <a href={norm.url} target="_blank" rel="noreferrer noopener" className="underline">
                  {norm.title}
                </a>
                {!norm.verified_by_lawyer && (
                  <span className="ml-2 rounded border border-amber-300 px-1 text-xs">
                    не проверено юристом
                  </span>
                )}
              </p>
            ))}
          </li>
        ))}
      </ol>
      <p className="text-sm text-muted">{plan.disclaimer}</p>
    </section>
  );
}

export function PathsScreen() {
  const { caseId, caseData } = useCaseContext();
  const confirmed = caseData.card_confirmed_at !== null;
  const paths = usePaths(caseId, confirmed ? caseData.version : undefined);
  const plan = usePlan(caseId, caseData.path === "self_guided");
  const choose = useChoosePath(caseId);
  const navigate = useNavigate();

  if (!confirmed) return <p>Сначала проверьте и подтвердите карточку.</p>;
  if (paths.isPending) return <p>Подбираем пути…</p>;
  if (!paths.data) return <ErrorText error={paths.error} />;

  async function pick(path: CasePath) {
    const done = await choose.mutateAsync({ path, version: caseData.version }).catch(() => null);
    if (done && path === "claim") navigate(`/user/cases/${caseId}/claim`);
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        {paths.data.items.map((option) => {
          const current = caseData.path === option.path;
          const canPick = option.available && has(caseData, "choose_path") && !current;
          return (
            <article
              key={option.path}
              aria-label={option.title}
              className={`flex flex-col gap-2 rounded border p-4 ${current ? "border-primary" : ""}`}
            >
              <h3 className="text-lg font-semibold">{option.title}</h3>
              <p className="text-sm">{WHAT_YOU_GET[option.path]}</p>
              <p className="text-sm">
                <span className="text-muted">Цена: </span>
                {option.price_kopecks === null
                  ? "цену предложит юрист"
                  : option.price_kopecks === 0
                    ? "бесплатно"
                    : rub(option.price_kopecks)}
              </p>
              <p className="text-sm">
                <span className="text-muted">Срок: </span>
                {days(option.estimated_days)}
              </p>
              {option.reason && <p className="text-sm text-amber-700">{option.reason}</p>}
              <div className="mt-auto pt-2">
                {current ? (
                  <span className="text-sm font-medium">Выбрано</span>
                ) : (
                  <Button onClick={() => pick(option.path)} disabled={!canPick || choose.isPending}>
                    Выбрать
                  </Button>
                )}
              </div>
            </article>
          );
        })}
      </div>
      <ErrorText error={choose.error} />
      {caseData.path === "specialist" && (
        <p role="status" className="rounded border p-3">
          Карточку в обезличенном виде проверит модератор, затем она появится у юристов.
        </p>
      )}
      {plan.data && <PlanView plan={plan.data} />}
      <ErrorText error={plan.error} />
    </div>
  );
}
