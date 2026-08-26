import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { ASystemMap, SYSTEM_MAP_V2_MANIFEST } from "./ASystemMap";

const queryGroups = [
  "POST /chat",
  "V2 Query Service",
  "Conversation Context",
  "Semantic Planner",
  "Canonical Briefing (blocked capability)",
  "Governed Vocabulary (canonical blocked)",
  "Deferred V2 Semantics",
  "Logical IR",
  "Physical Plan / GenerationScope",
  "canonical.exhaustive (not accepted)",
  "Canonical structured operations (blocked)",
  "canonical.graph (not accepted)",
  "retrieval.grounded (READY)",
  "graphrag.grounded (PARTIAL)",
  "Final-root Reconciliation",
  "ReasoningPackage",
  "AnswerEngine",
  "Citations / Response",
];
const indexingGroups = [
  "Source Processing",
  "Document Structure",
  "Entity / Mention",
  "Identity",
  "Relation",
  "Event",
  "Temporal",
  "Claim / Fact",
  "KG Build",
  "BM25",
  "Dense / Qdrant",
  "GraphRAG",
  "Generation / Readiness",
];

describe("ASystemMap", () => {
  afterEach(() => vi.restoreAllMocks());

  it("declares every V2 subsystem with a real boundary, docs, and scoped context", () => {
    expect(SYSTEM_MAP_V2_MANIFEST.query.map((item) => item.label)).toEqual(
      queryGroups,
    );
    expect(SYSTEM_MAP_V2_MANIFEST.indexing.map((item) => item.label)).toEqual(
      indexingGroups,
    );

    for (const subsystem of [
      ...SYSTEM_MAP_V2_MANIFEST.query,
      ...SYSTEM_MAP_V2_MANIFEST.indexing,
    ]) {
      expect(subsystem.boundary.startsWith("backend/")).toBe(true);
      expect(subsystem.documentation.startsWith("docs/")).toBe(true);
      expect(subsystem.context).toContain("AGENTS.md");
      expect(subsystem).not.toHaveProperty("intent");
    }

    const graph = SYSTEM_MAP_V2_MANIFEST.query.find(
      (item) => item.label === "canonical.graph (not accepted)",
    );
    const graphrag = SYSTEM_MAP_V2_MANIFEST.query.find(
      (item) => item.label === "graphrag.grounded (PARTIAL)",
    );
    expect(graph?.boundary).toContain("knowledge/graph");
    expect(graphrag?.boundary).toBe("backend/app/graphrag/");
    expect(graphrag?.guarantee).toContain("not canonical truth");
    const planning = SYSTEM_MAP_V2_MANIFEST.query.find(
      (item) => item.label === "Physical Plan / GenerationScope",
    );
    const retrieval = SYSTEM_MAP_V2_MANIFEST.query.find(
      (item) => item.label === "retrieval.grounded (READY)",
    );
    expect(planning?.boundary).toContain("execution.py");
    expect(retrieval?.guarantee).toContain("knowledge generation");
    expect(graph?.guarantee).toContain("not documented as fully proven");
  });

  it("renders live health and the V2 query and indexing manifests", async () => {
    vi.spyOn(apiClient, "getHealth").mockResolvedValue({
      status: "healthy",
      services: { backend: "healthy", worker: "healthy" },
    });
    vi.spyOn(apiClient, "diagnostics").mockResolvedValue({
      windows: { data_path: "D:/Cortex", ollama_base_url: "http://localhost" },
      workflows: { interrupted: 0, failed: 0, repairing: 0 },
      reconciliation: { state: "idle", message: "idle" },
    });

    render(<ASystemMap />);
    await waitFor(() =>
      expect(screen.getAllByText(/backend/).length).toBeGreaterThan(0),
    );

    fireEvent.click(screen.getByRole("tab", { name: "Indexing V2" }));
    for (const label of indexingGroups)
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    expect(
      screen.getByText((content) =>
        content.includes(
          "separate BM25, Dense/Qdrant, and GraphRAG projections",
        ),
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Query V2" }));
    for (const label of queryGroups)
      expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    expect(screen.getByText(/Production chat is V2-only/)).toBeInTheDocument();
    expect(screen.queryByText("GraphRAG final answer")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Arka plan/ }));
    expect(screen.getByText("Atomik checkpoint")).toBeInTheDocument();
  });
});
