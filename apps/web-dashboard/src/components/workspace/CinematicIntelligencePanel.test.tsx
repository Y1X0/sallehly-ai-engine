import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CinematicReport, RepairAction } from "@/lib/types";
import { CinematicIntelligencePanel } from "./CinematicIntelligencePanel";

const BASE_REPORT: CinematicReport = {
  project_id: "proj_1",
  scores: {
    character_consistency: 0.9,
    object_consistency: null,
    scene_continuity: 0.7,
    camera_consistency: 0.5,
    style: 1.0,
    overall: 0.775,
  },
  problems: [],
  repair_suggestions: [],
  character_count: 1,
  object_count: 0,
  environment_count: 1,
  shots_analyzed: 4,
};

function noop() {}

describe("CinematicIntelligencePanel", () => {
  it("renders every score as a rounded percentage, with a null score reading 'not analyzed'", () => {
    render(
      <CinematicIntelligencePanel
        report={BASE_REPORT}
        repairs={[]}
        onRepair={noop}
        repairingShotId={null}
        onApproveRepair={noop}
        onRejectRepair={noop}
        reviewingRepairId={null}
      />,
    );

    expect(screen.getByText("78%")).toBeInTheDocument(); // overall: 0.775 rounds to 78%
    expect(screen.getByText("90%")).toBeInTheDocument(); // character_consistency
    expect(screen.getByText("70%")).toBeInTheDocument(); // scene_continuity
    expect(screen.getByText("50%")).toBeInTheDocument(); // camera_consistency
    expect(screen.getByText("100%")).toBeInTheDocument(); // style
    expect(screen.getByText("not analyzed")).toBeInTheDocument(); // object_consistency is null
  });

  it("shows the shots/characters/objects analyzed summary line", () => {
    render(
      <CinematicIntelligencePanel
        report={BASE_REPORT}
        repairs={[]}
        onRepair={noop}
        repairingShotId={null}
        onApproveRepair={noop}
        onRejectRepair={noop}
        reviewingRepairId={null}
      />,
    );

    expect(screen.getByText(/4 shot\(s\) analyzed/)).toBeInTheDocument();
    expect(screen.getByText(/1 character\(s\)/)).toBeInTheDocument();
    expect(screen.getByText(/0 object\(s\) tracked/)).toBeInTheDocument();
  });

  it("lists detected problems with severity labels", () => {
    const report: CinematicReport = {
      ...BASE_REPORT,
      problems: [
        { severity: "critical", description: "Character face changed between shots", source: "quality" },
        { severity: "warning", description: "Focal length jumped sharply", source: "continuity" },
      ],
    };
    render(
      <CinematicIntelligencePanel
        report={report}
        repairs={[]}
        onRepair={noop}
        repairingShotId={null}
        onApproveRepair={noop}
        onRejectRepair={noop}
        reviewingRepairId={null}
      />,
    );

    expect(screen.getByText("Detected problems (2)")).toBeInTheDocument();
    expect(screen.getByText("Character face changed between shots")).toBeInTheDocument();
    expect(screen.getByText("[critical]")).toBeInTheDocument();
    expect(screen.getByText("[warning]")).toBeInTheDocument();
  });

  it("shows 'no consistency problems detected' once shots have been analyzed with none found", () => {
    render(
      <CinematicIntelligencePanel
        report={BASE_REPORT}
        repairs={[]}
        onRepair={noop}
        repairingShotId={null}
        onApproveRepair={noop}
        onRejectRepair={noop}
        reviewingRepairId={null}
      />,
    );

    expect(screen.getByText("No consistency problems detected.")).toBeInTheDocument();
  });

  it("calls onRepair with the shot id when Repair is clicked on a suggestion", async () => {
    const onRepair = vi.fn();
    const report: CinematicReport = {
      ...BASE_REPORT,
      repair_suggestions: [
        { shot_id: "shot_2", report_id: "report_1", overall_score: 0.4, worst_dimension: "camera_consistency" },
      ],
    };
    render(
      <CinematicIntelligencePanel
        report={report}
        repairs={[]}
        onRepair={onRepair}
        repairingShotId={null}
        onApproveRepair={noop}
        onRejectRepair={noop}
        reviewingRepairId={null}
      />,
    );

    expect(screen.getByText("shot_2")).toBeInTheDocument();
    expect(screen.getByText(/worst dimension: camera_consistency \(40%\)/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Repair" }));
    expect(onRepair).toHaveBeenCalledWith("shot_2");
  });

  it("hides the Repair button for a shot that already has a pending repair", () => {
    const report: CinematicReport = {
      ...BASE_REPORT,
      repair_suggestions: [
        { shot_id: "shot_2", report_id: "report_1", overall_score: 0.4, worst_dimension: "camera_consistency" },
      ],
    };
    const repairs: RepairAction[] = [
      {
        schema_version: "1.0",
        repair_id: "repair_1",
        project_id: "proj_1",
        shot_id: "shot_2",
        quality_report_id: "report_1",
        repair_type: "camera_repair",
        strategy_id: "strategy_1",
        status: "proposed",
        review_status: "pending",
      },
    ];
    render(
      <CinematicIntelligencePanel
        report={report}
        repairs={repairs}
        onRepair={noop}
        repairingShotId={null}
        onApproveRepair={noop}
        onRejectRepair={noop}
        reviewingRepairId={null}
      />,
    );

    expect(screen.queryByRole("button", { name: "Repair" })).not.toBeInTheDocument();
  });

  it("shows Approve/Reject for a pending repair and calls the right handler with the repair id", async () => {
    const onApproveRepair = vi.fn();
    const onRejectRepair = vi.fn();
    const repairs: RepairAction[] = [
      {
        schema_version: "1.0",
        repair_id: "repair_1",
        project_id: "proj_1",
        shot_id: "shot_2",
        quality_report_id: "report_1",
        repair_type: "camera_repair",
        strategy_id: "strategy_1",
        status: "proposed",
        after_summary: "Smoothed the camera jump between shot_1 and shot_2",
        review_status: "pending",
      },
    ];
    render(
      <CinematicIntelligencePanel
        report={BASE_REPORT}
        repairs={repairs}
        onRepair={noop}
        repairingShotId={null}
        onApproveRepair={onApproveRepair}
        onRejectRepair={onRejectRepair}
        reviewingRepairId={null}
      />,
    );

    expect(screen.getByText("Smoothed the camera jump between shot_1 and shot_2")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onApproveRepair).toHaveBeenCalledWith("repair_1");

    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onRejectRepair).toHaveBeenCalledWith("repair_1");
  });

  it("hides Approve/Reject once a repair has already been reviewed", () => {
    const repairs: RepairAction[] = [
      {
        schema_version: "1.0",
        repair_id: "repair_1",
        project_id: "proj_1",
        shot_id: "shot_2",
        quality_report_id: "report_1",
        repair_type: "camera_repair",
        strategy_id: "strategy_1",
        status: "applied",
        review_status: "approved",
      },
    ];
    render(
      <CinematicIntelligencePanel
        report={BASE_REPORT}
        repairs={repairs}
        onRepair={noop}
        repairingShotId={null}
        onApproveRepair={noop}
        onRejectRepair={noop}
        reviewingRepairId={null}
      />,
    );

    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(screen.getByText(/approved/)).toBeInTheDocument();
  });
});
