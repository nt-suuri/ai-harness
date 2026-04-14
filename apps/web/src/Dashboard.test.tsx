import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import { Dashboard } from "./Dashboard";

const mockFetch = vi.fn();

beforeEach(() => {
  mockFetch.mockReset();
  globalThis.fetch = mockFetch as unknown as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Dashboard", () => {
  it("shows loading initially", () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    render(<Dashboard />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("renders status when fetch resolves", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        ci: { success: 5, failure: 1 },
        deploy: { success: 2, failure: 0 },
        open_autotriage_issues: 3,
      }),
    });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/CI/i)).toBeInTheDocument();
      expect(screen.getByText(/5/)).toBeInTheDocument();
    });
  });

  it("shows error message on fetch failure", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 503 });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    });
  });
});
