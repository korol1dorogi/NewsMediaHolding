import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  has,
  type Offer,
  type PersonalData,
  useAcceptOffer,
  useAcceptWork,
  useOffers,
  usePublishPool,
} from "./api";
import { ErrorText, useCaseContext } from "./CaseLayout";
import { rub } from "./labels";

const MODERATION = {
  pending: "Карточка на модерации: модератор проверит, что в ней нет ваших данных.",
  approved: "Карточка в пуле: юристы видят её без ваших данных и присылают предложения.",
  rejected: "Модератор вернул карточку на доработку.",
} as const;

function AcceptForm({ offer, onCancel }: { offer: Offer; onCancel: () => void }) {
  const { caseId, caseData } = useCaseContext();
  const accept = useAcceptOffer(caseId);
  const [consent, setConsent] = useState(false);
  const [data, setData] = useState<PersonalData>({
    full_name: "",
    reply_address: "",
    contract_reference: "",
  });
  const needsData =
    accept.error instanceof Error && "fields" in accept.error
      ? (accept.error as { fields: string[] }).fields.includes("personal_data")
      : false;
  const filled = Object.values(data).every((value) => value.trim());
  const field = (key: keyof PersonalData, label: string) => (
    <label className="block text-sm">
      {label}
      <input
        className="mt-1 block w-full rounded border p-2"
        value={data[key]}
        onChange={(e) => setData({ ...data, [key]: e.target.value })}
      />
    </label>
  );
  return (
    <section className="space-y-3 rounded border border-primary p-3" aria-label="Оплата и согласие">
      <p className="font-medium">
        Оплата {rub(offer.price_kopecks)} — демонстрация. Деньги замораживаются на платформе и
        уходят юристу только после того, как вы примете работу.
      </p>
      <p className="text-sm">
        Юристу откроются ваши данные и документы. Если вы ещё не указывали данные в претензии,
        заполните их:
      </p>
      {field("full_name", "ФИО полностью")}
      {field("reply_address", "Адрес для связи")}
      {field("contract_reference", "Номер договора или заказа")}
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>Согласен раскрыть свои данные и документы выбранному юристу.</span>
      </label>
      {needsData && <p className="text-sm text-red-700">Заполните данные для юриста.</p>}
      <ErrorText error={accept.error} />
      <div className="flex gap-2">
        <Button
          disabled={!consent || accept.isPending}
          onClick={() =>
            accept.mutate({
              offerId: offer.id,
              version: caseData.version,
              personalData: filled
                ? {
                    full_name: data.full_name.trim(),
                    reply_address: data.reply_address.trim(),
                    contract_reference: data.contract_reference.trim(),
                  }
                : null,
            })
          }
        >
          Оплатить и выбрать юриста
        </Button>
        <Button variant="outline" onClick={onCancel}>
          Отмена
        </Button>
      </div>
    </section>
  );
}

function OffersList() {
  const { caseId, caseData } = useCaseContext();
  const offers = useOffers(caseId, caseData.version, caseData.pool !== null);
  const [chosen, setChosen] = useState<string | null>(null);
  if (!offers.data) return <ErrorText error={offers.error} />;
  if (offers.data.items.length === 0) {
    return <p className="text-sm text-muted">Предложений пока нет. Окно сбора — 48 часов.</p>;
  }
  return (
    <ul className="space-y-3" aria-label="Предложения юристов">
      {offers.data.items.map((offer) => (
        <li key={offer.id} className="space-y-2 rounded border p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <span className="font-medium">{offer.lawyer_label}</span>
            <span>
              {rub(offer.price_kopecks)} · {offer.duration_days} дн.
            </span>
          </div>
          <p>{offer.scope}</p>
          {offer.included.length > 0 && (
            <p className="text-sm">
              <span className="text-muted">Входит: </span>
              {offer.included.join("; ")}
            </p>
          )}
          {offer.excluded.length > 0 && (
            <p className="text-sm">
              <span className="text-muted">Не входит: </span>
              {offer.excluded.join("; ")}
            </p>
          )}
          {offer.accepted && <p className="text-sm font-medium">Выбран</p>}
          {has(caseData, "accept_offer") &&
            (chosen === offer.id ? (
              <AcceptForm offer={offer} onCancel={() => setChosen(null)} />
            ) : (
              <Button onClick={() => setChosen(offer.id)}>Выбрать</Button>
            ))}
        </li>
      ))}
    </ul>
  );
}

const PROGRESS: Record<string, string> = {
  offer_accepted: "Юрист выбран и скоро приступит к работе.",
  in_progress: "Юрист работает над делом.",
  work_submitted: "Юрист сдал работу. Проверьте результат и примите его.",
  completed: "Работа принята, оплата переведена юристу.",
};

export function SpecialistScreen() {
  const { caseId, caseData } = useCaseContext();
  const publish = usePublishPool(caseId);
  const acceptWork = useAcceptWork(caseId);
  const [consent, setConsent] = useState(false);

  if (caseData.path !== "specialist") {
    return <p>Этот раздел откроется, когда вы выберете «Обращение к специалисту».</p>;
  }
  return (
    <div className="space-y-6">
      {has(caseData, "publish_pool") && (
        <section className="space-y-3" aria-label="Отправка в пул">
          <p>
            Мы составим обезличенную карточку: без имени, контактов и документов, сумма —
            диапазоном. После проверки модератором её увидят юристы.
          </p>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            <span>Согласен опубликовать обезличенную карточку в пуле юристов.</span>
          </label>
          <ErrorText error={publish.error} />
          <Button
            disabled={!consent || publish.isPending}
            onClick={() => publish.mutate(caseData.version)}
          >
            Отправить юристам
          </Button>
        </section>
      )}
      {caseData.pool && ["in_pool", "has_offers", "no_offers"].includes(caseData.state) && (
        <p role="status" className="rounded border p-3" data-testid="pool-status">
          {MODERATION[caseData.pool.moderation_status]}
          {caseData.pool.rejection_reason && ` ${caseData.pool.rejection_reason}`}
        </p>
      )}
      {caseData.state === "no_offers" && (
        <p className="text-sm">Юристы не откликнулись. Можно вернуться к «Официальному запросу».</p>
      )}
      {caseData.pool?.moderation_status === "approved" && <OffersList />}
      {PROGRESS[caseData.state] && (
        <p role="status" className="rounded border p-3" data-testid="work-status">
          {PROGRESS[caseData.state]}
        </p>
      )}
      {caseData.work && (
        <section className="space-y-2" aria-label="Результат работы">
          <h3 className="font-semibold">Результат работы (версия {caseData.work.version})</h3>
          <pre className="whitespace-pre-wrap rounded border p-3 font-sans text-sm">
            {caseData.work.text}
          </pre>
          {has(caseData, "accept_work") && (
            <>
              <p className="text-xs text-muted">
                Если не ответить за 3 дня, работа будет принята автоматически.
              </p>
              <ErrorText error={acceptWork.error} />
              <Button
                disabled={acceptWork.isPending}
                onClick={() =>
                  caseData.work &&
                  acceptWork.mutate({
                    version: caseData.version,
                    workVersion: caseData.work.version,
                  })
                }
              >
                Принять работу
              </Button>
            </>
          )}
        </section>
      )}
    </div>
  );
}
