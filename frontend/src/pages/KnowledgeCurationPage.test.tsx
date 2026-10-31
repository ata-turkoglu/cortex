import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient, type IdentityOperation } from "../api/client";
import { KnowledgeCurationPage } from "./KnowledgeCurationPage";

vi.mock("../app/workspace", () => ({
  useWorkspace: () => ({ workspaceId: "workspace-a" }),
}));

const operation: IdentityOperation = {
  operation_id: "operation-a",
  kind: "alias_add",
  authority: "user_curated",
  source_entity_ids: ["entity-a"],
  result_entity_ids: ["entity-a"],
  evidence_ids: [],
  reason: "reviewed",
  details: {},
};

describe("KnowledgeCurationPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows canonical evidence and submits a reasoned alias decision", async () => {
    vi.spyOn(apiClient, "knowledgeReadiness").mockResolvedValue([]);
    vi.spyOn(apiClient, "unresolvedIdentityCuration").mockResolvedValue([]);
    vi.spyOn(apiClient, "listCanonicalEntities").mockResolvedValue([
      {
        entity_id: "entity-a",
        entity_type: "person",
        display_name: "Ayşe Yılmaz",
        subtype: null,
        authority: "validated",
        status: "active",
        aliases: ["A. Yılmaz"],
      },
    ]);
    vi.spyOn(apiClient, "identityHistory").mockResolvedValue([operation]);
    vi.spyOn(apiClient, "entityEvidence").mockResolvedValue([
      {
        evidence_id: "evidence-a",
        mention_id: "mention-a",
        original_text: "Ayşe Yılmaz",
        document_id: "document-a",
        document_version_id: "version-a",
        logical_document_id: "logical-a",
        chunk_id: "chunk-a",
        start_offset: 5,
        end_offset: 16,
        source_text: "Ayşe Yılmaz",
        extraction_run_id: "run-a",
        provider: "openai",
        model: "model-a",
        prompt_version: "prompt-v1",
        schema_version: "schema-v1",
        confidence: 0.9,
        validation_state: "validated",
        generation: "generation-a",
      },
    ]);
    const addAlias = vi.spyOn(apiClient, "addCanonicalAlias").mockResolvedValue(operation);

    render(<KnowledgeCurationPage />);

    await waitFor(() => expect(screen.getAllByText("Ayşe Yılmaz").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText("chunk-a")).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText("Alias"), { target: { value: "Ayşe Kaya" } });
    fireEvent.change(screen.getByPlaceholderText("Zorunlu curation gerekçesi"), {
      target: { value: "Evlilik soyadı evidence ile doğrulandı" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Alias ekle" }));

    await waitFor(() => expect(addAlias).toHaveBeenCalledWith(
      "workspace-a",
      "entity-a",
      "Ayşe Kaya",
      "Evlilik soyadı evidence ile doğrulandı",
    ));
  });
});
