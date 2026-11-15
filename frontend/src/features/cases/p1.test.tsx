import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CaseDetail, Claim, Offer } from "./api";
import { CASE_ID, caseDetail, mockApi, renderAt } from "./testing";

const BASE = `/api/cases/${CASE_ID}`;
afterEach(() => vi.unstubAllGlobals());

const claim = (overrides: Partial<Claim> = {}): Claim => ({
  id: "c1",
  case_id: CASE_ID,
  case_version: 10,
  current_version: 2,
  versions: [
    {
      version: 1,
      author: "ai",
      text: "Старый текст",
      comment: null,
      created_at: "2026-11-15T10:00:00Z",
    },
    {
      version: 2,
      author: "lawyer",
      text: "Новый текст",
      comment: "Уточнил сумму",
      created_at: "2026-11-15T11:00:00Z",
    },
  ],
  personal_data: {
    full_name: "Демо Пользователь",
    reply_address: "Город",
    contract_reference: "D-1",
  },
  personal_data_confirmed: true,
  faulty: false,
  submitted_at: "2026-11-15T10:30:00Z",
  sent_on: null,
  response_due_on: null,
  available_actions: [],
  ...overrides,
});

const inClaim = (state: CaseDetail["state"], actions: string[]) =>
  caseDetail({
    state,
    path: "claim",
    version: 10,
    card_confirmed_at: "2026-11-15T09:00:00Z",
    available_actions: actions as never,
  });

describe("F7 lawyer edits, sending, outcome", () => {
  it("shows before/after with the comment and accepts edits", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: inClaim("claim_edited", ["accept_edits", "reject_edits"]),
      [`GET ${BASE}/claim`]: claim(),
      [`POST ${BASE}/claim/accept-edits`]: inClaim("claim_approved", ["mark_sent"]),
    });
    renderAt(`/user/cases/${CASE_ID}/claim`);
    const edits = await screen.findByRole("region", { name: "Правки юриста" });
    expect(within(edits).getByText("Старый текст")).toBeInTheDocument();
    expect(within(edits).getByText("Новый текст")).toBeInTheDocument();
    expect(within(edits).getByText("Уточнил сумму")).toBeInTheDocument();
    expect(within(edits).getByRole("button", { name: "Не согласен" })).toBeDisabled();
    fireEvent.click(within(edits).getByRole("button", { name: "Принять правки" }));
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/accept-edits"))?.body).toEqual({
        expected_version: 10,
        claim_version: 2,
      }),
    );
  });

  it("marks the claim as sent", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: inClaim("claim_approved", ["mark_sent", "close_case"]),
      [`GET ${BASE}/claim`]: claim(),
      [`POST ${BASE}/claim/mark-sent`]: inClaim("awaiting_response", ["record_outcome"]),
    });
    renderAt(`/user/cases/${CASE_ID}/claim`);
    const final = await screen.findByRole("region", { name: "Итоговая претензия" });
    expect(within(final).getByText(/заказным письмом с описью/)).toBeInTheDocument();
    fireEvent.change(within(final).getByLabelText("Дата отправки"), {
      target: { value: "2026-11-15" },
    });
    fireEvent.click(within(final).getByRole("button", { name: "Я отправил претензию" }));
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/mark-sent"))?.body).toEqual({
        expected_version: 10,
        claim_version: 2,
        sent_on: "2026-11-15",
      }),
    );
  });

  it("records the outcome and offers a specialist after silence", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: inClaim("awaiting_response", ["record_outcome", "close_case"]),
      [`GET ${BASE}/claim`]: claim({ sent_on: "2026-11-15" }),
      [`POST ${BASE}/claim/outcome`]: inClaim("no_response", ["choose_path"]),
    });
    renderAt(`/user/cases/${CASE_ID}/claim`);
    const waiting = await screen.findByRole("region", { name: "Ответ компании" });
    expect(within(waiting).getByText(/Срок ответа уточнит юрист/)).toBeInTheDocument();
    fireEvent.click(within(waiting).getByRole("button", { name: "Нет ответа" }));
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/outcome"))?.body).toEqual({
        expected_version: 10,
        outcome: "no_response",
        comment: "Компания не ответила в срок",
      }),
    );
  });
});

const offer: Offer = {
  id: "00000000-0000-4000-8000-000000000006",
  lawyer_label: "Юрист demo_lawyer_1",
  scope: "Подготовлю иск",
  duration_days: 14,
  price_kopecks: 1_500_000,
  included: ["Иск"],
  excluded: ["Апелляция"],
  accepted: false,
  created_at: "2026-11-15T10:00:00Z",
};
const specialist = (state: CaseDetail["state"], actions: string[], extra = {}) =>
  caseDetail({
    state,
    path: "specialist",
    version: 12,
    card_confirmed_at: "2026-11-15T09:00:00Z",
    available_actions: actions as never,
    pool: { id: "p1", moderation_status: "approved", rejection_reason: null },
    ...extra,
  });

describe("F9 offers and work", () => {
  it("accepts an offer with consent and data for the lawyer", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: specialist("has_offers", ["accept_offer"]),
      [`GET ${BASE}/claim`]: () => Response.json({ code: "not_found" }, { status: 404 }),
      [`GET ${BASE}/offers`]: { items: [offer] },
      [`POST ${BASE}/offers/${offer.id}/accept`]: specialist("offer_accepted", []),
    });
    renderAt(`/user/cases/${CASE_ID}/specialist`);
    const list = await screen.findByRole("list", { name: "Предложения юристов" });
    expect(within(list).getByText("15 000 ₽ · 14 дн.")).toBeInTheDocument();
    fireEvent.click(within(list).getByRole("button", { name: "Выбрать" }));
    const pay = screen.getByRole("region", { name: "Оплата и согласие" });
    expect(within(pay).getByText(/демонстрация/)).toBeInTheDocument();
    const confirm = within(pay).getByRole("button", { name: "Оплатить и выбрать юриста" });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(pay).getByLabelText("ФИО полностью"), {
      target: { value: "Демо Пользователь" },
    });
    fireEvent.change(within(pay).getByLabelText("Адрес для связи"), { target: { value: "Город" } });
    fireEvent.change(within(pay).getByLabelText("Номер договора или заказа"), {
      target: { value: "D-1" },
    });
    fireEvent.click(within(pay).getByLabelText(/Согласен раскрыть/));
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/accept"))?.body).toEqual({
        expected_version: 12,
        consent: { accepted: true, text_version: "demo-v1" },
        personal_data: {
          full_name: "Демо Пользователь",
          reply_address: "Город",
          contract_reference: "D-1",
        },
      }),
    );
  });

  it("accepts the submitted work", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: specialist("work_submitted", ["accept_work"], {
        work: { version: 1, text: "Иск подан", submitted_at: "2026-11-15T12:00:00Z" },
      }),
      [`GET ${BASE}/offers`]: { items: [{ ...offer, accepted: true }] },
      [`POST ${BASE}/work/accept`]: specialist("completed", ["close_case"]),
    });
    renderAt(`/user/cases/${CASE_ID}/specialist`);
    const result = await screen.findByRole("region", { name: "Результат работы" });
    expect(within(result).getByText("Иск подан")).toBeInTheDocument();
    expect(screen.getByTestId("work-status")).toHaveTextContent("Юрист сдал работу");
    fireEvent.click(within(result).getByRole("button", { name: "Принять работу" }));
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/work/accept"))?.body).toEqual({
        expected_version: 12,
        work_version: 1,
      }),
    );
  });

  it("publishes to the pool only with consent", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: specialist("in_pool", ["publish_pool", "close_case"], { pool: null }),
      [`POST ${BASE}/pool`]: () =>
        Response.json(
          { id: "p1", moderation_status: "pending", rejection_reason: null },
          { status: 202 },
        ),
    });
    renderAt(`/user/cases/${CASE_ID}/specialist`);
    const send = await screen.findByRole("button", { name: "Отправить юристам" });
    expect(send).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/опубликовать обезличенную карточку/));
    fireEvent.click(send);
    await waitFor(() => expect(calls.some((call) => call.path.endsWith("/pool"))).toBe(true));
  });
});
