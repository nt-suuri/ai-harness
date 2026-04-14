import { expect, test } from "@playwright/test";

test("api /api/ping returns pong", async ({ request }) => {
  const res = await request.get("/api/ping");
  expect(res.status()).toBe(200);
  expect(await res.json()).toEqual({ status: "pong" });
});
