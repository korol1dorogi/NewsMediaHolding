import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import {
  type Claim,
  has,
  type Outcome,
  useAcceptEdits,
  useMarkSent,
  useOutcome,
  useRejectEdits,
} from "./api";
import { ErrorText, useCaseContext } from "./CaseLayout";
import { date } from "./labels";

function today() {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

function EditsReview({ claim }: { claim: Claim }) {
  const { caseId, caseData } = useCaseContext();
  const accept = useAcceptEdits(caseId);
  const reject = useRejectEdits(caseId);
  const [comment, setComment] = useState("");
  const before = claim.versions.find((v) => v.version === claim.current_version - 1);
  const after = claim.versions.find((v) => v.version === claim.current_version);
  if (!before || !after) return null;
  const body = { version: caseData.version, claimVersion: claim.current_version };

  async function submitReject(event: FormEvent) {
    event.preventDefault();
    await reject.mutateAsync({ ...body, comment: comment.trim() }).catch(() => null);
  }

  return (
    <section className="space-y-3" aria-label="Правки юриста">
      <h3 className="text-lg font-semibold">Юрист внёс правки</h3>
      <p className="rounded border p-2 text-sm">
        <span className="text-muted">Комментарий юриста: </span>
        {after.comment}
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h4 className="mb-1 text-sm font-medium">Было</h4>
          <pre className="whitespace-pre-wrap rounded border p-3 font-sans text-sm">
            {before.text}
          </pre>
        </div>
        <div>
          <h4 className="mb-1 text-sm font-medium">Стало</h4>
          <pre className="whitespace-pre-wrap rounded border border-green-300 p-3 font-sans text-sm">
            {after.text}
          </pre>
        </div>
      </div>
      <ErrorText error={accept.error ?? reject.error} />
      <div className="flex flex-wrap items-start gap-3">
        <Button onClick={() => accept.mutate(body)} disabled={accept.isPending}>
          Принять правки
        </Button>
        <form onSubmit={submitReject} className="flex flex-1 gap-2">
          <input
            aria-label="Почему не согласны"
            placeholder="Почему не согласны"
            className="flex-1 rounded border p-2"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <Button type="submit" variant="outline" disabled={!comment.trim() || reject.isPending}>
            Не согласен
          </Button>
        </form>
      </div>
    </section>
  );
}

function FinalClaim({ claim }: { claim: Claim }) {
  const { caseId, caseData } = useCaseContext();
  const markSent = useMarkSent(caseId);
  const [sentOn, setSentOn] = useState(today());
  const final = claim.versions.find((v) => v.version === claim.current_version);
  if (!final) return null;
  return (
    <section className="space-y-3" aria-label="Итоговая претензия">
      <h3 className="text-lg font-semibold">Претензия проверена юристом</h3>
      <div className="flex gap-2">
        <Button
          variant="outline"
          onClick={() =>
            void globalThis.navigator?.clipboard?.writeText(final.text).catch(() => undefined)
          }
        >
          Копировать текст
        </Button>
        <Button variant="outline" onClick={() => globalThis.print?.()}>
          Печать
        </Button>
      </div>
      <ol className="list-decimal space-y-1 pl-5 text-sm">
        <li>Распечатайте претензию в двух экземплярах и подпишите.</li>
        <li>Отправьте компании заказным письмом с описью вложения или вручите под подпись.</li>
        <li>Сохраните квитанцию и опись — это доказательство отправки.</li>
      </ol>
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          markSent.mutate({
            version: caseData.version,
            claimVersion: claim.current_version,
            sentOn,
          });
        }}
      >
        <label className="block text-sm">
          Дата отправки
          <input
            type="date"
            className="mt-1 block rounded border p-2"
            value={sentOn}
            max={today()}
            onChange={(e) => setSentOn(e.target.value)}
          />
        </label>
        <Button type="submit" disabled={!sentOn || markSent.isPending}>
          Я отправил претензию
        </Button>
      </form>
      <ErrorText error={markSent.error} />
    </section>
  );
}

const OUTCOMES: [Outcome, string, string][] = [
  ["resolved", "Деньги вернули", "Компания вернула деньги"],
  ["refused", "Отказали", "Компания отказала"],
  ["no_response", "Нет ответа", "Компания не ответила в срок"],
];

function WaitingResponse({ claim }: { claim: Claim }) {
  const { caseId, caseData } = useCaseContext();
  const outcome = useOutcome(caseId);
  return (
    <section className="space-y-3" aria-label="Ответ компании">
      <h3 className="text-lg font-semibold">Ждём ответа компании</h3>
      <p className="text-sm">
        Отправлена {claim.sent_on ? date(claim.sent_on) : "—"}.{" "}
        {claim.response_due_on
          ? `Срок ответа — до ${date(claim.response_due_on)}.`
          : "Срок ответа уточнит юрист: правила расчёта ещё не утверждены."}
      </p>
      <div className="flex flex-wrap gap-2">
        {OUTCOMES.map(([value, label, comment]) => (
          <Button
            key={value}
            variant={value === "resolved" ? "default" : "outline"}
            disabled={outcome.isPending}
            onClick={() => outcome.mutate({ version: caseData.version, outcome: value, comment })}
          >
            {label}
          </Button>
        ))}
      </div>
      <ErrorText error={outcome.error} />
    </section>
  );
}

export function AfterReview({ claim }: { claim: Claim }) {
  const { caseData } = useCaseContext();
  if (caseData.state === "claim_in_review") {
    return (
      <p role="status" className="rounded border p-3">
        Претензия у юриста на проверке. Обычно это занимает до 4 часов.
      </p>
    );
  }
  if (has(caseData, "accept_edits")) return <EditsReview claim={claim} />;
  if (has(caseData, "mark_sent")) return <FinalClaim claim={claim} />;
  if (has(caseData, "record_outcome")) return <WaitingResponse claim={claim} />;
  if (caseData.state === "resolved") {
    return <p role="status">Вопрос решён. Обращение можно закрыть.</p>;
  }
  if (caseData.state === "no_response") {
    return (
      <p role="status" className="rounded border p-3">
        Компания не помогла. Следующий шаг — юрист, который ведёт дело целиком:{" "}
        <Link to="../paths" relative="path" className="font-medium underline">
          выбрать «Обращение к специалисту»
        </Link>
        .
      </p>
    );
  }
  return null;
}
