import { type FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ErrorText } from "@/features/cases/CaseLayout";
import { factLabel, rub } from "@/features/cases/labels";
import { useApprove, useEdit, useQueue, useReview, useTake } from "./api";

function minutesLeft(iso: string, now: number) {
  return Math.max(0, Math.round((new Date(iso).getTime() - now) / 60_000));
}

function Countdown({ until }: { until: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(timer);
  }, []);
  const left = minutesLeft(until, now);
  return (
    <span className="text-sm" data-testid="countdown">
      Осталось {Math.floor(left / 60)} ч {left % 60} мин
    </span>
  );
}

export function QueueScreen() {
  const queue = useQueue();
  const take = useTake();
  const navigate = useNavigate();
  return (
    <section className="space-y-4">
      <h2 className="text-xl font-semibold">Очередь проверки претензий</h2>
      <p className="text-sm text-muted">
        Возьмите претензию — на проверку есть 4 часа, потом она вернётся в общую очередь. Контакты
        заявителя проверяющему не показываются.
      </p>
      {queue.isPending && <p>Загружаем…</p>}
      <ErrorText error={queue.error} />
      <ErrorText error={take.error} />
      {queue.data?.items.length === 0 && <p>Свободных претензий нет.</p>}
      <ul className="space-y-2" aria-label="Очередь">
        {queue.data?.items.map((item) => (
          <li
            key={item.id}
            data-claim-id={item.id}
            className="flex items-center justify-between rounded border p-3"
          >
            <span>
              <span className="font-medium">{rub(item.amount_kopecks)}</span>
              <span className="ml-3 text-sm text-muted">
                в очереди с {new Date(item.queued_at).toLocaleString("ru-RU")}
              </span>
            </span>
            <Button
              disabled={take.isPending}
              onClick={async () => {
                const claim = await take.mutateAsync(item).catch(() => null);
                if (claim) navigate(`/lawyer/queue/${claim.id}`);
              }}
            >
              Взять
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ReviewScreen() {
  const { claimId = "" } = useParams();
  const review = useReview(claimId);
  const approve = useApprove();
  const edit = useEdit();
  const [text, setText] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [done, setDone] = useState<string | null>(null);

  if (done) {
    return (
      <section className="space-y-3">
        <p role="status">{done}</p>
        <Link to="/lawyer/queue" className="underline">
          К очереди
        </Link>
      </section>
    );
  }
  if (review.isPending) return <p>Загружаем претензию…</p>;
  if (!review.data) {
    return (
      <section className="space-y-2">
        <ErrorText error={review.error} />
        <p className="text-sm">Срок проверки истёк или претензию взял другой юрист.</p>
        <Link to="/lawyer/queue" className="underline">
          К очереди
        </Link>
      </section>
    );
  }
  const claim = review.data;
  const draft = text ?? claim.version.template_text;
  const changed = draft.trim() !== claim.version.template_text.trim();

  async function submitEdit(event: FormEvent) {
    event.preventDefault();
    const ok = await edit
      .mutateAsync({ claim, text: draft, comment: comment.trim() })
      .catch(() => null);
    if (ok) setDone("Правки отправлены пользователю.");
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_18rem]">
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Проверка претензии</h2>
          <Countdown until={claim.assignment_expires_at} />
        </div>
        <p className="text-sm text-muted">
          {"{{claimant}}"} и {"{{reply_address}}"} — места для данных заявителя, их подставит
          сервис.
        </p>
        <form onSubmit={submitEdit} className="space-y-3">
          <label className="block">
            <span className="text-sm">Текст претензии</span>
            <textarea
              className="mt-1 block min-h-80 w-full rounded border p-2 font-mono text-sm"
              value={draft}
              onChange={(event) => setText(event.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-sm">Комментарий для пользователя (обязателен для правок)</span>
            <input
              className="mt-1 block w-full rounded border p-2"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
          </label>
          <ErrorText error={edit.error ?? approve.error} />
          <div className="flex gap-3">
            <Button
              type="button"
              disabled={changed || approve.isPending}
              onClick={async () => {
                const ok = await approve.mutateAsync(claim).catch(() => null);
                if (ok) setDone("Претензия подтверждена. Комиссия начислена.");
              }}
            >
              Подтвердить без правок
            </Button>
            <Button
              type="submit"
              variant="outline"
              disabled={!changed || !comment.trim() || edit.isPending}
            >
              Отправить правки
            </Button>
          </div>
        </form>
      </section>
      <aside className="space-y-4">
        <div className="rounded border p-3">
          <h3 className="mb-2 font-semibold">Факты карточки</h3>
          <ul className="space-y-2 text-sm">
            {claim.facts.map((fact) => (
              <li key={fact.key}>
                <span className="text-muted">{factLabel(fact.key)}: </span>
                {fact.display_value}
                <blockquote className="border-l-2 pl-2 text-xs">
                  «{fact.safe_source_quote}»
                </blockquote>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded border p-3 text-sm">
          <h3 className="mb-2 font-semibold">Документы</h3>
          {claim.documents.length === 0 && <p className="text-muted">Нет документов.</p>}
          <ul>
            {claim.documents.map((doc) => (
              <li key={doc.id}>
                {doc.label}
                {!doc.safe_redaction_available && (
                  <span className="ml-1 text-xs text-muted">(оригинал скрыт)</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
