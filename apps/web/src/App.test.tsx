import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the harness header", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: /ai-harness/i })).toBeInTheDocument();
  });
});
