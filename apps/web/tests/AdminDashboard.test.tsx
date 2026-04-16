import { render, screen } from "@testing-library/react";
import AdminDashboard from "../src/pages/AdminDashboard";
import React from "react";

describe("AdminDashboard", () => {
  test("renders the admin dashboard with title and text", () => {
    render(<AdminDashboard />);

    const titleElement = screen.getByText(/Admin Dashboard/i);
    const infoElement = screen.getByText(/Welcome to the enhanced admin dashboard. Stay tuned for more updates/i);

    expect(titleElement).toBeInTheDocument();
    expect(infoElement).toBeInTheDocument();
  });
});