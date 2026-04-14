import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { vi, beforeEach } from "vitest";

import { App } from "./App";

beforeEach(() => {
  globalThis.fetch = vi.fn().mockReturnValue(new Promise(() => {})) as unknown as typeof fetch;
});

describe("App", () => {
  it("renders the harness header", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /ai-harness/i })).toBeInTheDocument();
  });
});
