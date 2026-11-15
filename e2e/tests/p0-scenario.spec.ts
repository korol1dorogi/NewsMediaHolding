import { expect, type Page, test } from "@playwright/test";

// Demo accounts from `python manage.py seed_demo` with the .env.example placeholders.
const ANYA = { login: "demo_anya", password: process.env.DEMO_USER_PASSWORD ?? "demo-user-placeholder" };
const LAWYER = {
  login: "demo_lawyer_1",
  password: process.env.DEMO_LAWYER_PASSWORD ?? "demo-lawyer-placeholder",
};

async function login(page: Page, account: { login: string; password: string }) {
  await page.goto("/login");
  await page.getByLabel("Логин").fill(account.login);
  await page.getByLabel("Пароль").fill(account.password);
  await page.getByRole("button", { name: "Войти" }).click();
}

test("P0: Anya goes from her story to a claim sent for review", async ({ page, browser }) => {
  test.setTimeout(90_000);
  await login(page, ANYA);
  await expect(page.getByRole("heading", { name: "Кабинет пользователя" })).toBeVisible();

  // Dialog: the first message, the AI asks, Anya answers.
  await page.getByRole("link", { name: "Новое обращение" }).first().click();
  await page
    .getByLabel(/Что произошло/)
    .fill(
      "Оплатила 68 000 ₽ компании Учебный проект Демо (ИНН 0000000000). Деньги не возвращают уже три недели.",
    );
  await page.getByLabel(/Согласен на обработку/).check();
  await page.getByRole("button", { name: "Отправить" }).click();
  await expect(page).toHaveURL(/\/user\/cases\/[0-9a-f-]+$/);
  const caseUrl = page.url();
  await expect(page.getByText("Когда вы оплатили услугу и что вам обещали?")).toBeVisible();
  await page.getByLabel("Ваш ответ").fill("Оплатила 1 октября онлайн-курс по программированию.");
  await page.getByRole("button", { name: "Отправить" }).click();

  // Card: every fact has a verbatim quote; Anya checks one and confirms.
  await page.getByRole("link", { name: "Проверьте карточку" }).click();
  await page.getByRole("button", { name: "Учебный проект Демо" }).click();
  await expect(page.getByText("«Учебный проект Демо»")).toBeVisible();
  await page.getByRole("button", { name: "Всё верно, подтвердить" }).click();

  // Paths: the company is active, the claim costs 1 490 ₽.
  await expect(page).toHaveURL(/\/paths$/);
  const claimPath = page.getByRole("article", { name: "Официальный запрос" });
  await expect(claimPath.getByText("1 490 ₽")).toBeVisible();
  await page.getByRole("link", { name: "Карточка" }).click();
  await expect(page.getByTestId("company")).toContainText("Действует");
  await page.getByRole("link", { name: "Пути решения" }).click();
  await claimPath.getByRole("button", { name: "Выбрать" }).click();

  // Claim: AI drafts, Anya confirms her data and sends it to a lawyer.
  await expect(page).toHaveURL(/\/claim$/);
  await page.getByRole("button", { name: "Составить черновик претензии" }).click();
  const draft = page.getByTestId("claim-text");
  await expect(draft).toContainText("Учебный проект Демо");
  await expect(draft).toContainText("68000.00 руб.");
  await page.getByLabel("ФИО полностью").fill("Демо Пользователь");
  await page.getByLabel(/Адрес для ответа/).fill("Вымышленный город, учебный адрес");
  await page.getByLabel("Номер договора или заказа").fill("DEMO-CONTRACT-1");
  await page.getByLabel(/Данные верны/).check();
  await page.getByRole("button", { name: "Сохранить данные" }).click();
  await expect(draft).toContainText("Демо Пользователь");
  const send = page.getByRole("button", { name: "Отправить на проверку юристу" });
  await expect(send).toBeDisabled();
  await page.getByLabel(/Согласен передать текст претензии/).check();
  await send.click();
  await expect(page.getByTestId("case-state")).toHaveText("Претензия у юриста");

  // Somebody else cannot open Anya's case.
  const other = await browser.newPage();
  await login(other, LAWYER);
  await expect(other.getByRole("heading", { name: "Кабинет юриста" })).toBeVisible();
  const caseId = caseUrl.split("/").pop();
  expect((await other.request.get(`/api/cases/${caseId}`)).status()).toBe(404);
  expect((await other.request.get(`/api/cases/${caseId}/claim`)).status()).toBe(404);
  await other.close();
});
