import { type Browser, expect, type Page, test } from "@playwright/test";

// Q2: the whole demo from docs/mvp.md. Demo accounts come from `seed_demo` (placeholders).
const ANYA = { login: "demo_anya", password: process.env.DEMO_USER_PASSWORD ?? "demo-user-placeholder" };
const LAWYER = { login: "demo_lawyer_1", password: process.env.DEMO_LAWYER_PASSWORD ?? "demo-lawyer-placeholder" };
const LAWYER_2 = { login: "demo_lawyer_2", password: process.env.DEMO_LAWYER_PASSWORD ?? "demo-lawyer-placeholder" };
const MODERATOR = {
  login: "demo_moderator",
  password: process.env.DEMO_MODERATOR_PASSWORD ?? "demo-moderator-placeholder",
};

async function login(page: Page, account: { login: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Логин").fill(account.login);
  await page.getByLabel("Пароль").fill(account.password);
  await page.getByRole("button", { name: "Войти" }).click();
}

async function as(browser: Browser, account: { login: string; password: string }) {
  const page = await (await browser.newContext()).newPage();
  await login(page, account);
  return page;
}

test("Q2: claim reviewed with edits, no answer, pool, offer, data revealed, work accepted", async ({
  page,
  browser,
}) => {
  test.setTimeout(180_000);

  // 1–4. Anya: story → card → claim drafted, data confirmed, sent to review.
  await login(page, ANYA);
  await page.getByRole("link", { name: "Новое обращение" }).first().click();
  await page
    .getByLabel(/Что произошло/)
    .fill("Оплатила курс в Учебный проект Демо, 68000 рублей, деньги не возвращают уже три недели.");
  await page.getByLabel(/Согласен на обработку/).check();
  await page.getByRole("button", { name: "Отправить" }).click();
  await expect(page).toHaveURL(/\/user\/cases\/[0-9a-f-]+$/);
  const caseUrl = page.url();
  const caseId = caseUrl.split("/").pop() ?? "";
  const dialog = page.getByRole("list", { name: "Диалог" }).getByRole("listitem");
  for (const [index, answer] of [
    "Оплатила 1 октября банковской картой.",
    "ИНН 0000000000, обещали записанные уроки, я уже написала претензию.",
  ].entries()) {
    await expect(dialog).toHaveCount(2 * (index + 1));
    await page.getByLabel("Ваш ответ").fill(answer);
    await page.getByRole("button", { name: "Отправить" }).click();
  }
  await page.getByRole("link", { name: "Проверьте карточку" }).click();
  await page.getByRole("button", { name: "Всё верно, подтвердить" }).click();
  await page.getByRole("article", { name: "Официальный запрос" }).getByRole("button", { name: "Выбрать" }).click();
  await page.getByRole("button", { name: "Составить черновик претензии" }).click();
  await expect(page.getByTestId("claim-text")).toContainText("Учебный проект Демо");
  await page.getByLabel("ФИО полностью").fill("Демо Пользователь");
  await page.getByLabel(/Адрес для ответа/).fill("Вымышленный город, учебный адрес");
  await page.getByLabel("Номер договора или заказа").fill("DEMO-CONTRACT-1");
  await page.getByLabel(/Данные верны/).check();
  await page.getByRole("button", { name: "Сохранить данные" }).click();
  await page.getByLabel(/Согласен передать текст претензии/).check();
  await page.getByRole("button", { name: "Отправить на проверку юристу" }).click();
  await expect(page.getByTestId("case-state")).toHaveText("Претензия у юриста");

  // 5. Lawyer takes Anya's claim (the newest in the queue) and edits it.
  const lawyer = await as(browser, LAWYER);
  await lawyer.getByRole("link", { name: "Очередь" }).click();
  // Other e2e files run in parallel and also queue claims: pick Anya's by its id.
  const claimId = (await (await page.request.get(`/api/cases/${caseId}/claim`)).json()).id;
  const item = lawyer.locator(`li[data-claim-id="${claimId}"]`);
  await expect(item).toBeVisible();
  await item.getByRole("button", { name: "Взять" }).click();
  const text = lawyer.getByLabel("Текст претензии");
  await expect(text).not.toHaveValue("");
  await expect(lawyer.getByText("Демо Пользователь")).toHaveCount(0); // no contacts for reviewers
  await text.fill(`${await text.inputValue()}\nПрошу ответить в письменной форме.`);
  await lawyer.getByLabel(/Комментарий для пользователя/).fill("Добавил требование о письменном ответе");
  await lawyer.getByRole("button", { name: "Отправить правки" }).click();
  await expect(lawyer.getByText("Правки отправлены пользователю.")).toBeVisible();

  // 5–6. Anya accepts the edits, marks the claim sent, the company does not answer.
  await page.goto(`${caseUrl}/claim`);
  const edits = page.getByRole("region", { name: "Правки юриста" });
  await expect(edits.getByText("Добавил требование о письменном ответе")).toBeVisible();
  await edits.getByRole("button", { name: "Принять правки" }).click();
  await page.getByRole("button", { name: "Я отправил претензию" }).click();
  await page.getByRole("button", { name: "Нет ответа" }).click();
  await expect(page.getByTestId("case-state")).toHaveText("Компания не ответила");

  // 6. Anya moves on to a specialist and publishes an anonymised card.
  await page.getByRole("link", { name: "Пути решения" }).click();
  await page
    .getByRole("article", { name: "Обращение к специалисту" })
    .getByRole("button", { name: "Выбрать" })
    .click();
  await page.getByRole("link", { name: "Юрист" }).click();
  await page.getByLabel(/опубликовать обезличенную карточку/).check();
  await page.getByRole("button", { name: "Отправить юристам" }).click();
  await expect(page.getByTestId("pool-status")).toContainText("на модерации");

  // Moderator approves the card in the admin (every card is checked at the start).
  const moderator = await (await browser.newContext()).newPage();
  await moderator.goto("/admin/login/");
  await moderator.locator("#id_username").fill(MODERATOR.login);
  await moderator.locator("#id_password").fill(MODERATOR.password);
  await moderator.locator("input[type=submit]").click();
  await moderator.goto("/admin/pool/poolcard/?moderation_status__exact=pending");
  await moderator.locator("input.action-select").first().check();
  await moderator.locator("select[name=action]").selectOption("approve_cards");
  await moderator.locator("button[name=index]").click();
  await expect(moderator.getByText(/Опубликовано/)).toBeVisible();

  // 7. A lawyer sees the anonymised card and sends an offer. The reviewer may offer too,
  // because the company did not answer; the second lawyer is used to keep roles apart.
  const lawyer2 = await as(browser, LAWYER_2);
  await lawyer2.getByRole("link", { name: "Пул обращений" }).click();
  const cards = lawyer2.getByRole("list", { name: "Пул" }).getByRole("listitem");
  const anyaCard = cards.filter({ hasText: "Претензия отправлена, ответа нет." }).first();
  await expect(anyaCard).toBeVisible();
  await expect(lawyer2.getByText("Демо Пользователь")).toHaveCount(0);
  await anyaCard.getByRole("link", { name: "Предложить помощь" }).click();
  await lawyer2.getByLabel("Что сделаю").fill("Подготовлю и подам иск, рассчитаю неустойку");
  await lawyer2.getByLabel("Цена, ₽").fill("15000");
  await lawyer2.getByLabel(/Что входит/).fill("Иск\nРасчёт неустойки");
  await lawyer2.getByRole("button", { name: "Отправить предложение" }).click();
  await expect(lawyer2.getByText(/Предложение отправлено/)).toBeVisible();
  expect((await lawyer2.request.get(`/api/lawyer/cases/${caseId}`)).status()).toBe(404);

  // 8. Anya accepts the offer: consent + demo payment → the lawyer sees her data.
  await page.reload();
  const offers = page.getByRole("list", { name: "Предложения юристов" });
  await offers.getByRole("button", { name: "Выбрать" }).first().click();
  await page.getByLabel(/Согласен раскрыть/).check();
  await page.getByRole("button", { name: "Оплатить и выбрать юриста" }).click();
  await expect(page.getByTestId("work-status")).toContainText("Юрист выбран");

  await lawyer2.goto(`/lawyer/cases/${caseId}`);
  await expect(lawyer2.getByTestId("personal-data")).toContainText("Демо Пользователь");
  await lawyer2.getByRole("button", { name: "Приступить к работе" }).click();
  await lawyer2.getByLabel("Результат работы").fill("Иск подан, копия и расчёт во вложении.");
  await lawyer2.getByRole("button", { name: "Сдать работу" }).click();
  await expect(lawyer2.getByRole("status")).toContainText("Работа сдана");

  // Anya accepts the work; the frozen money goes to the lawyer.
  await page.reload();
  await page.getByRole("button", { name: "Принять работу" }).click();
  await expect(page.getByTestId("case-state")).toHaveText("Работа принята");
  expect((await lawyer2.request.get(`/api/lawyer/cases/${caseId}`)).status()).toBe(404);
});
