import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mockApi, renderAt } from "@/features/cases/testing";
import type { LawyerCase, PoolCard, ReviewClaim } from "./api";

afterEach(() => vi.unstubAllGlobals());

const LAWYER = { id: "l1", username: "demo_lawyer_1", role: "lawyer", is_demo: true };
const CLAIM_ID = "00000000-0000-4000-8000-000000000004";

const review: ReviewClaim = {
  id: CLAIM_ID,
  case_id: "00000000-0000-4000-8000-000000000001",
  case_version: 5,
  assignment_version: 1,
  assignment_expires_at: new Date(Date.now() + 3 * 3_600_000).toISOString(),
  version: { version: 1, template_text: "ПРЕТЕНЗИЯ от {{claimant}}", comment: null },
  facts: [{ key: "amount", display_value: "68000 рублей", safe_source_quote: "68000 рублей" }],
  documents: [
    {
      id: "d1",
      label: "Документ 1 (текст)",
      content_type: "text/plain",
      safe_redaction_available: false,
    },
  ],
  available_actions: ["approve_claim", "edit_claim"],
};

describe("F6 queue and review", () => {
  it("drops a claim taken by another lawyer from the list", async () => {
    let taken = false;
    mockApi({
      "GET /api/auth/me": LAWYER,
      "GET /api/lawyer/claims": () => ({
        items: taken
          ? []
          : [
              {
                id: CLAIM_ID,
                category: "prepaid_services",
                amount_kopecks: 6_800_000,
                queued_at: "2026-11-15T10:00:00Z",
                case_version: 5,
              },
            ],
      }),
      [`POST /api/lawyer/claims/${CLAIM_ID}/take`]: () => {
        taken = true;
        return Response.json(
          { code: "conflict", message: "Претензию уже взял другой юрист.", details: {} },
          { status: 409 },
        );
      },
    });
    renderAt("/lawyer/queue");
    const queue = await screen.findByRole("list", { name: "Очередь" });
    expect(await within(queue).findByText("68 000 ₽")).toBeInTheDocument();
    fireEvent.click(within(queue).getByRole("button", { name: "Взять" }));
    expect(await screen.findByText("Претензию уже взял другой юрист.")).toBeInTheDocument();
    expect(await screen.findByText("Свободных претензий нет.")).toBeInTheDocument();
  });

  it("does not send edits without a comment", async () => {
    const calls = mockApi({
      "GET /api/auth/me": LAWYER,
      [`GET /api/lawyer/claims/${CLAIM_ID}`]: review,
      [`POST /api/lawyer/claims/${CLAIM_ID}/edit`]: { id: CLAIM_ID },
    });
    renderAt(`/lawyer/queue/${CLAIM_ID}`);
    const text = await screen.findByLabelText("Текст претензии");
    expect(screen.getByTestId("countdown")).toHaveTextContent(/Осталось 2 ч|Осталось 3 ч/);
    expect(screen.getByText("«68000 рублей»")).toBeInTheDocument();
    expect(screen.getByText("(оригинал скрыт)")).toBeInTheDocument();
    fireEvent.change(text, { target: { value: "ПРЕТЕНЗИЯ от {{claimant}}. Уточнено." } });
    const send = screen.getByRole("button", { name: "Отправить правки" });
    expect(send).toBeDisabled();
    expect(screen.getByRole("button", { name: "Подтвердить без правок" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/Комментарий для пользователя/), {
      target: { value: "Уточнил требование" },
    });
    expect(send).toBeEnabled();
    fireEvent.click(send);
    await waitFor(() =>
      expect(calls.find((call) => call.path.endsWith("/edit"))?.body).toEqual({
        expected_version: 5,
        assignment_version: 1,
        claim_version: 1,
        template_text: "ПРЕТЕНЗИЯ от {{claimant}}. Уточнено.",
        comment: "Уточнил требование",
      }),
    );
    expect(await screen.findByText("Правки отправлены пользователю.")).toBeInTheDocument();
  });
});

const card: PoolCard = {
  id: "00000000-0000-4000-8000-000000000005",
  category: "prepaid_services",
  description: "Потребитель просит вернуть оплату за онлайн-курс.",
  city: "Вымышленск",
  amount_range: { min_kopecks: 5_000_000, max_kopecks: 9_999_999 },
  company: { name: "Учебный проект Демо", status: "active" },
  actions_taken: ["Претензия отправлена, ответа нет."],
  similar_cases: { count: 33, cities_count: 5, period_months: 12 },
};

describe("F8 pool, offer and my cases", () => {
  it("shows anonymised cards and sends an offer", async () => {
    const calls = mockApi({
      "GET /api/auth/me": LAWYER,
      "GET /api/lawyer/pool": { items: [card] },
      [`GET /api/lawyer/pool/${card.id}`]: card,
      [`POST /api/lawyer/pool/${card.id}/offers`]: () =>
        Response.json({ id: "o1" }, { status: 201 }),
    });
    renderAt("/lawyer/pool");
    const pool = await screen.findByRole("list", { name: "Пул" });
    expect(await within(pool).findByTestId("similar")).toHaveTextContent(
      "Похожих обращений: 33 из 5 городов",
    );
    expect(within(pool).getByText(/50 000 ₽ – 99 999,99 ₽/)).toBeInTheDocument();
    fireEvent.click(within(pool).getByRole("link", { name: "Предложить помощь" }));
    const form = await screen.findByRole("form", { name: "Предложение" });
    const submit = within(form).getByRole("button", { name: "Отправить предложение" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(form).getByLabelText("Что сделаю"), { target: { value: "Подам иск" } });
    fireEvent.change(within(form).getByLabelText("Цена, ₽"), { target: { value: "15000" } });
    fireEvent.change(within(form).getByLabelText(/Что входит/), {
      target: { value: "Иск\nРасчёт" },
    });
    fireEvent.click(submit);
    await waitFor(() =>
      expect(calls.find((call) => call.method === "POST")?.body).toEqual({
        scope: "Подам иск",
        duration_days: 14,
        price_kopecks: 1_500_000,
        included: ["Иск", "Расчёт"],
        excluded: [],
      }),
    );
    expect(await screen.findByText(/Предложение отправлено/)).toBeInTheDocument();
  });

  it("shows the client's data after the offer is accepted", async () => {
    const lawyerCase: LawyerCase = {
      case: {
        id: "c1",
        state: "in_progress",
        path: "specialist",
        ai_state: "idle",
        version: 9,
        created_at: "2026-11-15T10:00:00Z",
        updated_at: "2026-11-15T10:00:00Z",
        available_actions: ["submit_work"],
      },
      card: {
        version: 1,
        confirmed_at: "2026-11-15T10:00:00Z",
        facts: [],
        missing_required_fields: [],
      },
      personal_data: {
        full_name: "Демо Пользователь",
        reply_address: "Вымышленный город",
        contract_reference: "DEMO-1",
      },
      documents: [
        {
          id: "d1",
          filename: "чек.txt",
          content_type: "text/plain",
          size_bytes: 4,
          created_at: "2026-11-15T10:00:00Z",
        },
      ],
      claim: null,
      accepted_offer: {
        id: "o1",
        lawyer_label: "Юрист demo",
        scope: "Подам иск",
        duration_days: 14,
        price_kopecks: 1_500_000,
        included: [],
        excluded: [],
        accepted: true,
        created_at: "2026-11-15T10:00:00Z",
      },
      work: null,
    };
    const calls = mockApi({
      "GET /api/auth/me": LAWYER,
      "GET /api/lawyer/cases/c1": lawyerCase,
      "POST /api/lawyer/cases/c1/submit-work": lawyerCase.case,
    });
    renderAt("/lawyer/cases/c1");
    const personal = await screen.findByTestId("personal-data");
    expect(personal).toHaveTextContent("Демо Пользователь");
    expect(screen.getByRole("link", { name: "чек.txt" })).toHaveAttribute(
      "href",
      "/api/cases/c1/documents/d1/content",
    );
    fireEvent.change(screen.getByLabelText("Результат работы"), { target: { value: "Иск подан" } });
    fireEvent.click(screen.getByRole("button", { name: "Сдать работу" }));
    await waitFor(() =>
      expect(calls.find((call) => call.method === "POST")?.body).toEqual({
        expected_version: 9,
        text: "Иск подан",
      }),
    );
  });
});
