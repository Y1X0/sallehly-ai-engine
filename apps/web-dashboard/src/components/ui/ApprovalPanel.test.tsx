import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ApprovalPanel } from "./ApprovalPanel";

describe("ApprovalPanel", () => {
  it("calls onApprove when Approve is clicked", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(<ApprovalPanel title="Review" onApprove={onApprove} onReject={onReject} />);

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onApprove).toHaveBeenCalledOnce();
    expect(onReject).not.toHaveBeenCalled();
  });

  it("splits multi-line feedback into an array and calls onReject", async () => {
    const onApprove = vi.fn();
    const onReject = vi.fn();
    render(<ApprovalPanel title="Review" onApprove={onApprove} onReject={onReject} />);

    await userEvent.click(screen.getByRole("button", { name: "Request changes" }));
    const textarea = screen.getByPlaceholderText(/one piece of feedback per line/i);
    await userEvent.type(textarea, "too static{Enter}add more movement");
    await userEvent.click(screen.getByRole("button", { name: "Submit feedback" }));

    expect(onReject).toHaveBeenCalledWith(["too static", "add more movement"]);
  });

  it("does not allow submitting empty feedback", async () => {
    const onReject = vi.fn();
    render(<ApprovalPanel title="Review" onApprove={vi.fn()} onReject={onReject} />);

    await userEvent.click(screen.getByRole("button", { name: "Request changes" }));
    expect(screen.getByRole("button", { name: "Submit feedback" })).toBeDisabled();
    expect(onReject).not.toHaveBeenCalled();
  });

  it("returns to the approve/reject buttons when Cancel is clicked", async () => {
    render(<ApprovalPanel title="Review" onApprove={vi.fn()} onReject={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Request changes" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/one piece of feedback per line/i)).not.toBeInTheDocument();
  });
});
