import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders a human-readable label for a known status", () => {
    render(<StatusBadge status="waiting_storyboard_approval" />);
    expect(screen.getByText("Storyboard review")).toBeInTheDocument();
  });

  it("falls back to the raw status string for an unknown value", () => {
    render(<StatusBadge status="some_future_status" />);
    expect(screen.getByText("some_future_status")).toBeInTheDocument();
  });

  it("renders completed and failed with distinct text", () => {
    const { rerender } = render(<StatusBadge status="completed" />);
    expect(screen.getByText("Completed")).toBeInTheDocument();

    rerender(<StatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
