import { render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";

import { Dashboard } from "./Dashboard";

const mockFetch = vi.fn();

function mockOK(body: object) {
  return { ok: true, json: async () => body };
}

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
    expect(screen.getAllByText(/loading/i).length).toBeGreaterThan(0);
  });

  it("renders status and agents when both fetches resolve", async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === "/api/status") {
        return Promise.resolve(mockOK({
          ci: { success: 5, failure: 1 },
          deploy: { success: 2, failure: 0 },
          open_autotriage_issues: 3,
        }));
      }
      if (url === "/api/agents") {
        return Promise.resolve(mockOK({
          count: 2,
          agents: [
            { name: "reviewer", purpose: "3-pass PR reviewer", trigger: "pull_request", module: "agents.reviewer" },
            { name: "triager", purpose: "Sentry → GH issue dedupe", trigger: "schedule", module: "agents.triager" },
          ],
        }));
      }
      return Promise.reject(new Error("unexpected url"));
    });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/CI/i)).toBeInTheDocument();
      expect(screen.getByText(/5/)).toBeInTheDocument();
      expect(screen.getByText("reviewer")).toBeInTheDocument();
      expect(screen.getByText("triager")).toBeInTheDocument();
    });
  });

  it("shows error message when status fetch fails", async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === "/api/status") {
        return Promise.resolve({ ok: false, status: 503 });
      }
      return Promise.resolve(mockOK({ count: 0, agents: [] }));
    });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/Status unavailable/i)).toBeInTheDocument();
    });
  });

  it("shows error message when agents fetch fails", async () => {
    mockFetch.mockImplementation((url: string) => {
      if (url === "/api/agents") {
        return Promise.resolve({ ok: false, status: 500 });
      }
      return Promise.resolve(mockOK({
        ci: { success: 0, failure: 0 },
        deploy: { success: 0, failure: 0 },
        open_autotriage_issues: 0,
      }));
    });
    render(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/Agents unavailable/i)).toBeInTheDocument();
    });
  });
});
