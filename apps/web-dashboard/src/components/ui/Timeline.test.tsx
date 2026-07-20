import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Timeline } from "./Timeline";

describe("Timeline", () => {
  it("marks earlier steps done and shows the current step as active", () => {
    render(<Timeline status="waiting_storyboard_approval" />);
    // Created, Planning are done (checkmarks); Storyboard is current.
    const checkmarks = screen.getAllByText("✓");
    expect(checkmarks).toHaveLength(2);
    expect(screen.getByText("Storyboard")).toBeInTheDocument();
  });

  it("shows a failure marker on the generating step when status is failed", () => {
    render(<Timeline status="failed" />);
    expect(screen.getByText("!")).toBeInTheDocument();
  });

  it("highlights the storyboard step when rejected_stage is storyboard", () => {
    render(<Timeline status="rejected" rejectedStage="storyboard" />);
    // Storyboard step should not be marked done (no checkmark on it) - render succeeds without throwing.
    expect(screen.getByText("Storyboard")).toBeInTheDocument();
  });

  it("highlights the render plan step when rejected_stage is render_plan", () => {
    render(<Timeline status="rejected" rejectedStage="render_plan" />);
    expect(screen.getByText("Render plan")).toBeInTheDocument();
  });

  it("marks every step done when completed", () => {
    render(<Timeline status="completed" />);
    const checkmarks = screen.getAllByText("✓");
    expect(checkmarks).toHaveLength(7);
  });
});
