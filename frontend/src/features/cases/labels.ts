import type { CaseDetail, CompanyCheck } from "./api";

export const FACT_LABELS: Record<string, string> = {
  company_name: "Компания",
  company_inn: "ИНН компании",
  service_description: "Что оплачено",
  payment_date: "Дата оплаты",
  amount: "Сумма",
};

export function factLabel(key: string): string {
  return FACT_LABELS[key] ?? key;
}

export const STATE_LABELS: Record<CaseDetail["state"], string> = {
  draft: "Собираем сведения",
  clarifying: "Нужны уточнения",
  emergency: "Срочная ситуация",
  card_ready: "Карточка готова к проверке",
  card_confirmed: "Карточка подтверждена",
  self_guided: "Реши сам",
  claim_draft: "Черновик претензии",
  claim_in_review: "Претензия у юриста",
  claim_edited: "Юрист внёс правки",
  claim_approved: "Претензия проверена",
  awaiting_response: "Ждём ответа компании",
  resolved: "Решено",
  no_response: "Компания не ответила",
  in_pool: "Ищем юриста",
  has_offers: "Есть предложения юристов",
  no_offers: "Предложений нет",
  offer_accepted: "Юрист выбран",
  in_progress: "Юрист работает",
  work_submitted: "Работа сдана",
  completed: "Работа принята",
  disputed: "Спор",
  closed: "Закрыто",
};

export const COMPANY_LABELS: Record<CompanyCheck["status"], string> = {
  active: "Действует",
  liquidating: "Ликвидируется",
  bankrupt: "Банкротство",
  unavailable: "Не удалось проверить",
};

export function rub(kopecks: number): string {
  const rubles = Math.floor(kopecks / 100);
  const rest = kopecks % 100;
  const text = rubles.toLocaleString("ru-RU").replace(/[  ]/g, " ");
  return rest ? `${text},${String(rest).padStart(2, "0")} ₽` : `${text} ₽`;
}

export function days(count: number): string {
  const tail = count % 10;
  const teen = count % 100 >= 11 && count % 100 <= 14;
  const word = teen ? "дней" : tail === 1 ? "день" : tail >= 2 && tail <= 4 ? "дня" : "дней";
  return `${count} ${word}`;
}

export function date(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}.${year}`;
}
