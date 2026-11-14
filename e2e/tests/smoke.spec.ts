import { expect, test } from "@playwright/test";

test("api is ready", async ({ request }) => {
  const response = await request.get("/api/ready");
  expect(response.status()).toBe(200);
  expect((await response.json()).status).toBe("ready");
});

test("home page loads and reaches the api through the same origin", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Каждое обращение");
  await expect(page.getByTestId("api-status")).toHaveText("API: ok");
});

test("unknown page shows not found", async ({ page }) => {
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Страница не найдена");
});
