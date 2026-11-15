import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Card, Claim, PathOption, Plan } from "./api";
import { personalDataSchema } from "./ClaimScreen";
import { CASE_ID, caseDetail, mockApi, renderAt } from "./testing";

const BASE = `/api/cases/${CASE_ID}`;
afterEach(() => vi.unstubAllGlobals());

describe("F2 dialog", () => {
  const messages = {
    items: [
      { id: "m1", author: "user", text: "Курс не вернули", created_at: "2026-11-15T10:00:00Z" },
      { id: "m2", author: "ai", text: "Когда вы оплатили?", created_at: "2026-11-15T10:00:01Z" },
    ],
  };

  it("shows that the AI is thinking", async () => {
    mockApi({
      [`GET ${BASE}`]: caseDetail({ ai_state: "thinking" }),
      [`GET ${BASE}/messages`]: messages,
    });
    renderAt(`/user/cases/${CASE_ID}`);
    expect(await screen.findByText("AI думает…")).toBeInTheDocument();
    expect(screen.queryByLabelText("Ваш ответ")).not.toBeInTheDocument();
  });

  it("shows a failure and lets the user send again", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: caseDetail({
        state: "clarifying",
        ai_state: "failed",
        version: 3,
        available_actions: ["send_message", "upload_document", "close_case"],
      }),
      [`GET ${BASE}/messages`]: messages,
      [`POST ${BASE}/messages`]: { case: caseDetail({ ai_state: "thinking" }), message: {} },
    });
    renderAt(`/user/cases/${CASE_ID}`);
    expect(await screen.findByText(/AI не смог обработать/)).toBeInTheDocument();
    expect(await screen.findByText("Когда вы оплатили?")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Ваш ответ"), { target: { value: "1 октября" } });
    fireEvent.click(screen.getByRole("button", { name: "Отправить" }));
    await waitFor(() =>
      expect(calls.find((call) => call.method === "POST")?.body).toEqual({
        text: "1 октября",
        expected_version: 3,
      }),
    );
  });

  it("links to the card when it is ready and shows upload errors", async () => {
    mockApi({
      [`GET ${BASE}`]: caseDetail({
        state: "card_ready",
        version: 4,
        available_actions: ["upload_document", "confirm_card", "close_case"],
      }),
      [`GET ${BASE}/messages`]: messages,
      [`POST ${BASE}/documents`]: () =>
        Response.json(
          { code: "validation_error", message: "Неподдерживаемый файл.", details: {} },
          { status: 400 },
        ),
    });
    renderAt(`/user/cases/${CASE_ID}`);
    expect(await screen.findByRole("link", { name: "Проверьте карточку" })).toHaveAttribute(
      "href",
      `/user/cases/${CASE_ID}/card`,
    );
    const input = screen.getByLabelText(/Загрузить фото/);
    fireEvent.change(input, { target: { files: [new File(["x"], "x.pdf")] } });
    expect(await screen.findByText("Неподдерживаемый файл.")).toBeInTheDocument();
  });
});

describe("F3 card", () => {
  const card = (facts: Card["facts"], missing: string[] = []): Card => ({
    version: 2,
    confirmed_at: null,
    facts,
    missing_required_fields: missing,
  });
  const found = {
    key: "company_name",
    value: "Учебный проект Демо",
    status: "found" as const,
    required: true,
    source: { kind: "message" as const, id: "m1", source_version: 1 },
    source_quote: "Учебный проект Демо",
  };
  const empty = {
    key: "amount",
    value: null,
    status: "not_found" as const,
    required: true,
    source: null,
    source_quote: null,
  };
  const ready = caseDetail({
    state: "card_ready",
    version: 5,
    available_actions: ["confirm_card", "close_case"],
  });

  it("shows the source quote for a found fact", async () => {
    mockApi({ [`GET ${BASE}`]: ready, [`GET ${BASE}/card`]: card([found]) });
    renderAt(`/user/cases/${CASE_ID}/card`);
    const value = await screen.findByRole("button", { name: "Учебный проект Демо" });
    expect(screen.queryByText("«Учебный проект Демо»")).not.toBeInTheDocument();
    fireEvent.click(value);
    expect(screen.getByText("«Учебный проект Демо»")).toBeInTheDocument();
    expect(screen.getByText(/ваше сообщение/)).toBeInTheDocument();
  });

  it("blocks confirmation while required fields are empty and lets the user fill them", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: ready,
      [`GET ${BASE}/card`]: card([found, empty], ["amount"]),
      [`PATCH ${BASE}/card/facts/amount`]: card([found, { ...empty, value: "68 000 ₽" }]),
    });
    renderAt(`/user/cases/${CASE_ID}/card`);
    const confirm = await screen.findByRole("button", { name: "Всё верно, подтвердить" });
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Заполните: Сумма");
    fireEvent.change(screen.getByLabelText("Значение: Сумма"), { target: { value: "68 000 ₽" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({
        value: "68 000 ₽",
        expected_version: 5,
      }),
    );
  });

  it("confirms a complete card", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: ready,
      [`GET ${BASE}/card`]: card([found]),
      [`POST ${BASE}/card/confirm`]: caseDetail({ state: "card_confirmed" }),
      [`GET ${BASE}/paths`]: { items: [] },
    });
    renderAt(`/user/cases/${CASE_ID}/card`);
    const confirm = await screen.findByRole("button", { name: "Всё верно, подтвердить" });
    expect(confirm).toBeEnabled();
    fireEvent.click(confirm);
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/confirm"))?.body).toEqual({
        expected_version: 5,
        card_version: 2,
      }),
    );
  });
});

describe("F4 paths and plan", () => {
  const options: PathOption[] = [
    {
      path: "self_guided",
      title: "Реши сам",
      available: true,
      reason: null,
      estimated_days: 1,
      price_kopecks: 0,
    },
    {
      path: "claim",
      title: "Официальный запрос",
      available: false,
      reason: "Компания в процедуре банкротства",
      estimated_days: 1,
      price_kopecks: 149000,
    },
    {
      path: "specialist",
      title: "Обращение к специалисту",
      available: true,
      reason: null,
      estimated_days: 2,
      price_kopecks: null,
    },
  ];
  const confirmed = caseDetail({
    state: "card_confirmed",
    version: 6,
    card_confirmed_at: "2026-11-15T10:00:00Z",
    available_actions: ["choose_path", "close_case"],
  });

  it("shows price, term and the reason an option is unavailable", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: confirmed,
      [`GET ${BASE}/paths`]: { items: options },
      [`POST ${BASE}/path`]: caseDetail({ state: "self_guided", path: "self_guided" }),
    });
    renderAt(`/user/cases/${CASE_ID}/paths`);
    const claim = await screen.findByRole("article", { name: "Официальный запрос" });
    expect(within(claim).getByText("1 490 ₽")).toBeInTheDocument();
    expect(within(claim).getByText("Компания в процедуре банкротства")).toBeInTheDocument();
    expect(within(claim).getByRole("button", { name: "Выбрать" })).toBeDisabled();
    const self = screen.getByRole("article", { name: "Реши сам" });
    expect(within(self).getByText("бесплатно")).toBeInTheDocument();
    fireEvent.click(within(self).getByRole("button", { name: "Выбрать" }));
    await waitFor(() =>
      expect(calls.find((call) => call.method === "POST")?.body).toEqual({
        path: "self_guided",
        expected_version: 6,
      }),
    );
  });

  it("renders the plan with unverified norms and the disclaimer", async () => {
    const plan: Plan = {
      version: 2,
      steps: [
        {
          order: 1,
          text: "Направьте претензию",
          due_on: null,
          documents: ["Чек"],
          destination: "Исполнитель услуги",
          norms: [
            {
              id: "n1",
              title: "Статья 32",
              url: "https://example.invalid/n1",
              verified_by_lawyer: false,
            },
          ],
        },
      ],
      disclaimer: "Не является юридической консультацией.",
    };
    mockApi({
      [`GET ${BASE}`]: { ...confirmed, state: "self_guided", path: "self_guided" },
      [`GET ${BASE}/paths`]: { items: options },
      [`GET ${BASE}/plan`]: plan,
    });
    renderAt(`/user/cases/${CASE_ID}/paths`);
    expect(await screen.findByText("Направьте претензию")).toBeInTheDocument();
    expect(screen.getByText("не проверено юристом")).toBeInTheDocument();
    expect(screen.getByText("Не является юридической консультацией.")).toBeInTheDocument();
    expect(screen.getByText("Выбрано")).toBeInTheDocument();
  });
});

describe("F5 claim", () => {
  const claim: Claim = {
    id: "c1",
    case_id: CASE_ID,
    case_version: 8,
    current_version: 1,
    versions: [
      {
        version: 1,
        author: "ai",
        text: "ПРЕТЕНЗИЯ {{claimant}}",
        comment: null,
        created_at: "2026-11-15T10:00:00Z",
      },
    ],
    personal_data: null,
    personal_data_confirmed: false,
    faulty: false,
    submitted_at: null,
    sent_on: null,
    response_due_on: null,
    available_actions: ["confirm_personal_data", "close_case"],
  };

  it("validates personal data", () => {
    const valid = {
      full_name: "Демо Пользователь",
      reply_address: "Вымышленный город",
      contract_reference: "DEMO-1",
      confirmed: true,
    };
    expect(personalDataSchema.safeParse(valid).success).toBe(true);
    expect(personalDataSchema.safeParse({ ...valid, full_name: "Демо" }).success).toBe(false);
    expect(personalDataSchema.safeParse({ ...valid, reply_address: "  " }).success).toBe(false);
    expect(personalDataSchema.safeParse({ ...valid, contract_reference: "a\u0000b" }).success).toBe(
      false,
    );
    expect(personalDataSchema.safeParse({ ...valid, confirmed: false }).success).toBe(false);
  });

  it("shows form errors and keeps submit unavailable without data", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: caseDetail({
        state: "claim_draft",
        path: "claim",
        version: 8,
        card_confirmed_at: "2026-11-15T10:00:00Z",
        available_actions: ["confirm_personal_data", "close_case"],
      }),
      [`GET ${BASE}/claim`]: claim,
    });
    renderAt(`/user/cases/${CASE_ID}/claim`);
    expect(await screen.findByText(/Черновик. Перед отправкой/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Отправить на проверку юристу" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить данные" }));
    expect(await screen.findByText("Укажите: ФИО")).toBeInTheDocument();
    expect(screen.getByText("Подтвердите, что данные верны")).toBeInTheDocument();
    expect(calls.some((call) => call.method === "PUT")).toBe(false);
  });

  it("requires consent before sending to review", async () => {
    const calls = mockApi({
      [`GET ${BASE}`]: caseDetail({
        state: "claim_draft",
        path: "claim",
        version: 9,
        card_confirmed_at: "2026-11-15T10:00:00Z",
        available_actions: ["confirm_personal_data", "submit_claim", "close_case"],
      }),
      [`GET ${BASE}/claim`]: {
        ...claim,
        personal_data_confirmed: true,
        personal_data: {
          full_name: "Демо Пользователь",
          reply_address: "Город",
          contract_reference: "D-1",
        },
      },
      [`POST ${BASE}/claim/submit`]: caseDetail({ state: "claim_in_review" }),
    });
    renderAt(`/user/cases/${CASE_ID}/claim`);
    const send = await screen.findByRole("button", { name: "Отправить на проверку юристу" });
    expect(send).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Согласен передать текст претензии/));
    expect(send).toBeEnabled();
    fireEvent.click(send);
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/submit"))?.body).toEqual({
        expected_version: 9,
        claim_version: 1,
        consent: { accepted: true, text_version: "demo-v1" },
      }),
    );
  });
});
