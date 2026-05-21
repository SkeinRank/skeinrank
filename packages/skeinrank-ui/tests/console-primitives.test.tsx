import { render, screen } from "@testing-library/react";
import { Database } from "lucide-react";
import { describe, expect, it } from "vitest";

import {
  ConsolePage,
  EntityDetailPanel,
  getConsoleToneForStatus,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
  WorkspaceHeader,
} from "../src/components/layout/ConsolePrimitives";
import { Badge } from "../src/components/ui/badge";
import { Button } from "../src/components/ui/button";

describe("console layout primitives", () => {
  it("renders shared shell, header, section, metric, and detail primitives", () => {
    render(
      <ConsolePage>
        <WorkspaceHeader
          actions={<Button variant="secondary">Open action</Button>}
          description="Shared workspace description"
          eyebrow="Control plane"
          meta={<Badge>ready</Badge>}
          title="Workspace title"
        />
        <MasterDetailLayout>
          <SectionCard
            actions={<Button variant="ghost">View all</Button>}
            description="Reusable section description"
            title="Reusable section"
          >
            <MetricPill
              helper="15 canonical terms"
              icon={Database}
              label="Profiles"
              tone="cyan"
              value={1}
            />
          </SectionCard>
          <EntityDetailPanel
            badge={<Badge>active</Badge>}
            description="Selected entity details"
            title="Detail panel"
          >
            <p>Selected canonical term</p>
          </EntityDetailPanel>
        </MasterDetailLayout>
      </ConsolePage>,
    );

    expect(screen.getByText("Workspace title")).toBeInTheDocument();
    expect(screen.getByText("Shared workspace description")).toBeInTheDocument();
    expect(screen.getByText("Reusable section")).toBeInTheDocument();
    expect(screen.getByText("Profiles")).toBeInTheDocument();
    expect(screen.getByText("Detail panel")).toBeInTheDocument();
    expect(screen.getByText("Selected canonical term")).toBeInTheDocument();
  });

  it("maps runtime statuses to shared console tones", () => {
    expect(getConsoleToneForStatus("ready")).toBe("emerald");
    expect(getConsoleToneForStatus("succeeded")).toBe("emerald");
    expect(getConsoleToneForStatus("failed")).toBe("red");
    expect(getConsoleToneForStatus("degraded")).toBe("red");
    expect(getConsoleToneForStatus("queued")).toBe("amber");
    expect(getConsoleToneForStatus("unknown")).toBe("amber");
    expect(getConsoleToneForStatus("not_required")).toBe("slate");
  });
});
