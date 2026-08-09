import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../api/client";
import { ASystemMap } from "./ASystemMap";

describe("ASystemMap", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders live health and switches detailed map tabs", async () => {
    vi.spyOn(apiClient, "getHealth").mockResolvedValue({
      status: "healthy",
      services: { backend: "healthy", worker: "healthy" },
    });
    vi.spyOn(apiClient, "diagnostics").mockResolvedValue({
      windows: { data_path: "D:\\Cortex", ollama_base_url: "http://localhost" },
      workflows: { interrupted: 0, failed: 0, repairing: 0 },
      reconciliation: { state: "idle", message: "idle" },
    });
    render(<ASystemMap />);
    await waitFor(() => expect(screen.getAllByText(/backend/).length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText(/recovery/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getByRole("tab", { name: "Belge akışı" }));
    expect(screen.getByText("Düz metin kaynağı mı?")).toBeInTheDocument();
    expect(screen.getByText("Docling ayrıştırma")).toBeInTheDocument();
    expect(screen.getByText("Doğrudan UTF-8 okuma")).toBeInTheDocument();
    expect(screen.getByText("Kaynak dosya kaydı · Disk")).toBeInTheDocument();
    expect(screen.getByText("Normalize Markdown · Disk")).toBeInTheDocument();
    expect(screen.getByText("Chunk kayıtları · SQLite")).toBeInTheDocument();
    expect(
      screen.getByText("Heading 2 → mantıksal belgeler · SQLite"),
    ).toBeInTheDocument();
    expect(screen.getByText("Replacement isteği mi?")).toBeInTheDocument();
    expect(screen.getByText("Ingestion run · SQLite")).toBeInTheDocument();
    expect(screen.getByText("Index checkpoint · SQLite")).toBeInTheDocument();
    expect(screen.getByText("Qdrant dense vektörleri")).toBeInTheDocument();
    expect(screen.getByText("GraphRAG reindex workflow")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Sorgu akışı" }));
    expect(screen.getAllByText("Dense retrieval").length).toBeGreaterThan(0);
    expect(screen.getByText(/Kayıt kaynağı: Qdrant Vector DB/)).toBeInTheDocument();
    expect(screen.getByText(/Kayıt kaynağı: workspace’e özel bm25s cache dosyaları/)).toBeInTheDocument();
    expect(screen.getByText("Graph DRIFT")).toBeInTheDocument();
    expect(screen.getAllByText("GraphRAG query job").length).toBeGreaterThan(0);
    expect(screen.getAllByText("GraphRAG Worker").length).toBeGreaterThan(0);
    expect(screen.getAllByText("GraphRAG final answer").length).toBeGreaterThan(0);
    expect(screen.getByText("Yanıt biçimi niyeti")).toBeInTheDocument();
    expect(screen.getByText("Belgeye göre grupla")).toBeInTheDocument();
  });
});
