import { type ChangeEvent, type FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { has, useMessages, useSendMessage, useUploadDocument } from "./api";
import { ErrorText, useCaseContext } from "./CaseLayout";

const REQUESTED_DOCUMENTS = [
  ["Чек или банковская выписка", "подтверждает сумму и дату оплаты"],
  ["Договор, оферта или скриншот условий", "показывает, что обещала компания"],
  ["Переписка с компанией", "показывает, что вы уже требовали вернуть деньги"],
] as const;

const ACCEPT = ".png,.jpg,.jpeg,.txt,image/png,image/jpeg,text/plain";

export function DialogScreen() {
  const { caseId, caseData } = useCaseContext();
  const messages = useMessages(caseId, caseData.version);
  const send = useSendMessage(caseId);
  const upload = useUploadDocument(caseId);
  const [text, setText] = useState("");
  const [uploaded, setUploaded] = useState<string[]>([]);
  const thinking = caseData.ai_state === "thinking";
  const failed = caseData.ai_state === "failed";

  async function submit(event: FormEvent) {
    event.preventDefault();
    const sent = await send
      .mutateAsync({ text: text.trim(), version: caseData.version })
      .catch(() => null);
    if (sent) setText("");
  }

  async function attach(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const doc = await upload.mutateAsync({ file, version: caseData.version }).catch(() => null);
    if (doc) setUploaded((items) => [...items, doc.filename]);
  }

  return (
    <div className="grid gap-6 md:grid-cols-[1fr_16rem]">
      <section className="space-y-4">
        <p className="rounded border border-amber-300 bg-amber-50 p-3 text-sm">
          Если есть угроза жизни или здоровью, звоните 112. Сервис помогает с деньгами и
          документами, но не заменяет экстренные службы.
        </p>
        <ol className="space-y-3" aria-label="Диалог">
          {messages.data?.items.map((message) => (
            <li
              key={message.id}
              className={`max-w-[85%] whitespace-pre-line rounded-lg p-3 ${
                message.author === "user" ? "ml-auto bg-primary text-primary-foreground" : "border"
              }`}
            >
              <span className="sr-only">{message.author === "user" ? "Вы: " : "AI: "}</span>
              {message.text}
            </li>
          ))}
        </ol>
        <ErrorText error={messages.error} />
        {thinking && (
          <p role="status" className="text-sm text-muted">
            AI думает…
          </p>
        )}
        {failed && (
          <p role="alert" className="text-sm text-red-700">
            AI не смог обработать сообщение. Отправьте его ещё раз — можно короче.
          </p>
        )}
        {caseData.state === "emergency" && (
          <p role="alert" className="rounded border border-red-300 bg-red-50 p-3">
            Похоже, ситуация срочная. Если есть угроза — звоните 112. Если деньги списывают
            прямо сейчас — немедленно позвоните в банк и заблокируйте карту. Приём обращения
            остановлен; его можно закрыть.
          </p>
        )}
        {caseData.state === "card_ready" && (
          <p role="status" className="rounded border border-green-300 bg-green-50 p-3">
            Карточка готова.{" "}
            <Link to="card" className="font-medium underline">
              Проверьте карточку
            </Link>
          </p>
        )}
        {has(caseData, "send_message") && (
          <form onSubmit={submit} className="space-y-2">
            <label className="block">
              <span className="text-sm">Ваш ответ</span>
              <textarea
                className="mt-1 block min-h-24 w-full rounded border p-2"
                value={text}
                onChange={(event) => setText(event.target.value)}
                required
              />
            </label>
            <ErrorText error={send.error} />
            <Button type="submit" disabled={!text.trim() || send.isPending}>
              Отправить
            </Button>
          </form>
        )}
      </section>
      <aside className="space-y-3">
        <h3 className="font-semibold">Документы</h3>
        <ul className="space-y-2 text-sm">
          {REQUESTED_DOCUMENTS.map(([name, why]) => (
            <li key={name}>
              <span className="font-medium">{name}</span> — {why}
            </li>
          ))}
        </ul>
        {has(caseData, "upload_document") && (
          <label className="block text-sm">
            <span>Загрузить фото или текст (PNG, JPEG, TXT)</span>
            <input type="file" accept={ACCEPT} onChange={attach} className="mt-1 block w-full" />
          </label>
        )}
        <ErrorText error={upload.error} />
        {uploaded.length > 0 && (
          <ul className="text-sm" aria-label="Загруженные документы">
            {uploaded.map((name) => (
              <li key={name}>✓ {name}</li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}
