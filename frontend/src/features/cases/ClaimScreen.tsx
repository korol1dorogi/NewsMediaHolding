import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { AfterReview } from "./AfterReview";
import {
  type Claim,
  has,
  useClaim,
  useConfirmPersonalData,
  useCreateClaim,
  useSubmitClaim,
} from "./api";
import { ErrorText, useCaseContext } from "./CaseLayout";
import { date } from "./labels";

// biome-ignore lint/suspicious/noControlCharactersInRegex: rejecting control characters is the point
const NO_CONTROL = /^[^\u0000-\u001f\u007f]*$/;
const text = (label: string, max: number) =>
  z
    .string()
    .trim()
    .min(1, `Укажите: ${label}`)
    .max(max, `Не длиннее ${max} символов`)
    .regex(NO_CONTROL, "Недопустимые символы");

export const personalDataSchema = z.object({
  full_name: text("ФИО", 200).refine((value) => value.split(/\s+/).length >= 2, {
    message: "Укажите фамилию и имя",
  }),
  reply_address: text("адрес для ответа", 500),
  contract_reference: text("номер договора или заказа", 200),
  confirmed: z.literal(true, { error: "Подтвердите, что данные верны" }),
});

type FormValues = z.input<typeof personalDataSchema>;

const STAGES = [
  ["claim_draft", "Черновик"],
  ["claim_in_review", "У юриста"],
  ["claim_approved", "Проверена"],
  ["awaiting_response", "Отправлена"],
  ["resolved", "Ответ получен"],
] as const;

function Stages({ state }: { state: string }) {
  const order = STAGES.findIndex(
    ([key]) => key === state || (key === "claim_in_review" && state === "claim_edited"),
  );
  return (
    <ol className="flex flex-wrap gap-2 text-sm" aria-label="Статус претензии">
      {STAGES.map(([key, label], index) => (
        <li
          key={key}
          aria-current={index === order ? "step" : undefined}
          className={`rounded px-2 py-1 ${index <= order ? "bg-primary text-primary-foreground" : "border"}`}
        >
          {label}
        </li>
      ))}
    </ol>
  );
}

function PersonalDataForm({ claim }: { claim: Claim }) {
  const { caseId, caseData } = useCaseContext();
  const save = useConfirmPersonalData(caseId);
  const form = useForm<FormValues>({
    resolver: zodResolver(personalDataSchema),
    defaultValues: {
      full_name: claim.personal_data?.full_name ?? "",
      reply_address: claim.personal_data?.reply_address ?? "",
      contract_reference: claim.personal_data?.contract_reference ?? "",
      confirmed: false as unknown as true,
    },
  });
  const { errors } = form.formState;
  const submit = form.handleSubmit(async (values) => {
    const parsed = personalDataSchema.parse(values);
    await save
      .mutateAsync({
        version: caseData.version,
        data: {
          full_name: parsed.full_name,
          reply_address: parsed.reply_address,
          contract_reference: parsed.contract_reference,
        },
      })
      .catch(() => null);
  });
  const field = (name: "full_name" | "reply_address" | "contract_reference", label: string) => (
    <label className="block">
      <span className="text-sm">{label}</span>
      <input className="mt-1 block w-full rounded border p-2" {...form.register(name)} />
      {errors[name] && <span className="text-sm text-red-700">{errors[name]?.message}</span>}
    </label>
  );
  return (
    <form onSubmit={submit} className="space-y-3" aria-label="Ваши данные для претензии" noValidate>
      {field("full_name", "ФИО полностью")}
      {field("reply_address", "Адрес для ответа (почтовый или электронный)")}
      {field("contract_reference", "Номер договора или заказа")}
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" {...form.register("confirmed")} />
        <span>Данные верны — претензия пойдёт от моего имени</span>
      </label>
      {errors.confirmed && <span className="text-sm text-red-700">{errors.confirmed.message}</span>}
      <ErrorText error={save.error} />
      <Button type="submit" disabled={save.isPending}>
        Сохранить данные
      </Button>
    </form>
  );
}

export function ClaimScreen() {
  const { caseId, caseData } = useCaseContext();
  const create = useCreateClaim(caseId);
  const submit = useSubmitClaim(caseId);
  // After «no response» the user may move on to a specialist; the claim stays visible.
  const inClaimFlow =
    caseData.path === "claim" ||
    (caseData.path === "specialist" && caseData.state !== "card_confirmed");
  const ready = inClaimFlow && caseData.ai_state !== "thinking" && !has(caseData, "create_claim");
  const claim = useClaim(caseId, caseData.version, ready);
  const [consent, setConsent] = useState(false);

  if (!inClaimFlow) {
    return <p>Претензия появится, когда вы выберете путь «Официальный запрос».</p>;
  }
  if (caseData.path === "specialist" && !claim.data) {
    return <p>По этому обращению претензия не составлялась.</p>;
  }
  const current = claim.data?.versions.find((item) => item.version === claim.data?.current_version);
  const canSubmit = has(caseData, "submit_claim") && consent;

  return (
    <div className="space-y-6">
      <Stages state={caseData.state} />
      {has(caseData, "create_claim") && (
        <div className="space-y-2">
          {caseData.ai_state === "failed" && (
            <p role="alert" className="text-sm text-red-700">
              Не удалось составить черновик. Попробуйте ещё раз.
            </p>
          )}
          <Button onClick={() => create.mutate(caseData.version)} disabled={create.isPending}>
            Составить черновик претензии
          </Button>
          <ErrorText error={create.error} />
          {create.error instanceof Error && "fields" in create.error && (
            <p className="text-sm">Уточните эти поля в карточке и попробуйте снова.</p>
          )}
        </div>
      )}
      {caseData.ai_state === "thinking" && (
        <p role="status" className="text-sm text-muted">
          AI составляет черновик…
        </p>
      )}
      {current && claim.data && (
        <div className="grid gap-6 md:grid-cols-2">
          <section className="space-y-2">
            {["claim_draft", "claim_in_review"].includes(caseData.state) && (
              <p className="rounded border border-amber-300 bg-amber-50 p-2 text-sm">
                Черновик. Перед отправкой его проверит юрист.
              </p>
            )}
            <pre
              className="whitespace-pre-wrap rounded border p-3 font-sans text-sm"
              data-testid="claim-text"
            >
              {current.text}
            </pre>
            {claim.data.sent_on && <p className="text-sm">Отправлена {date(claim.data.sent_on)}</p>}
          </section>
          {caseData.state === "claim_draft" && (
            <section className="space-y-4">
              <PersonalDataForm claim={claim.data} />
              {claim.data.personal_data_confirmed && (
                <div className="space-y-2 border-t pt-4">
                  <label className="flex items-start gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={consent}
                      onChange={(event) => setConsent(event.target.checked)}
                    />
                    <span>
                      Согласен передать текст претензии юристу-проверяющему. Контакты юрист не
                      увидит.
                    </span>
                  </label>
                  <ErrorText error={submit.error} />
                  <Button
                    onClick={() =>
                      submit.mutate({
                        version: caseData.version,
                        claimVersion: claim.data.current_version,
                      })
                    }
                    disabled={!canSubmit || submit.isPending}
                  >
                    Отправить на проверку юристу
                  </Button>
                  <p className="text-xs text-muted">
                    Оплата проверки по цене из «Пути решения» — демонстрация: деньги условно
                    замораживаются до проверки юристом и не списываются.
                  </p>
                </div>
              )}
            </section>
          )}
        </div>
      )}
      {claim.data && caseData.state !== "claim_draft" && <AfterReview claim={claim.data} />}
      {caseData.path === "claim" && <ErrorText error={claim.error} />}
    </div>
  );
}
