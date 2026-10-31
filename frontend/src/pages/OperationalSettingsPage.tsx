import { useEffect, useState } from "react";
import {
  apiClient,
  type OllamaCatalogModel,
  type OllamaPullOperation,
  type ProviderName,
  type ProviderStatus,
} from "../api/client";
import {
  AButton,
  ACheckbox,
  ACard,
  ADialog,
  AInfo,
  AInfoPanel,
  AInput,
  ALabel,
  ARadio,
  ASelect,
  useConfirmation,
} from "../components/ui";

const apiProviders: ProviderName[] = ["openai", "anthropic"];
const openAiOnlyLayer = (layer: string) =>
  layer.startsWith("semantic_planner_") || layer === "summary" || layer === "answer";
const layers = [
  ["metadata", "Metadata extraction"],
  ["semantic_planner_simple", "Semantic Planner / Simple"],
  ["semantic_planner_standard", "Semantic Planner / Standard"],
  ["semantic_planner_complex", "Semantic Planner / Complex"],
  ["answer", "Answer synthesis"],
  ["summary", "Conversation summary"],
  ["graphrag_extraction", "Entity and relationship extraction"],
  ["graphrag_community", "Community report generation"],
  ["graphrag_global", "GraphRAG Global selection"],
  ["graphrag_drift", "GraphRAG DRIFT selection"],
  ["embedding", "Embeddings"],
] as const;

const layerDescriptions: Record<string, string> = {
  semantic_planner_simple: "Interprets short, simple requests with the strict semantic JSON Schema.",
  semantic_planner_standard: "Interprets analytical and structured requests with the strict semantic JSON Schema.",
  semantic_planner_complex: "Interprets ambiguous or long relational requests with the strict semantic JSON Schema.",
  metadata: "Belgeden başlık, tür ve etiket gibi yapılandırılmış bilgileri çıkarır.",
  answer: "Açıkken belge araması cevaplarını yalnızca doğrulanmış kanıttan, her cümlesi kaynağa bağlı olarak yazar; doğrulanamayan cevap deterministik metne döner.",
  summary: "Uzun konuşmaları sonraki mesajlar için kısa bağlama dönüştürür.",
  graphrag_extraction: "Microsoft GraphRAG'ın tek extract_graph adımıyla varlıkları ve aralarındaki ilişkileri çıkarır.",
  graphrag_community: "Bulunan toplulukları, graf çapında sorguların kullanacağı özet ve raporlara dönüştürür.",
  graphrag_global: "Akıllı arama açıkken, soruyla ilgili topluluk raporlarını seçmek için özetleri puanlar.",
  graphrag_drift: "Akıllı arama açıkken, soruya en yakın topluluk raporlarını bulmak için tek bir ön çağrı yapar.",
  embedding: "Metni, anlam tabanlı aramada kullanılan sayısal vektörlere dönüştürür.",
};

export function OperationalSettingsPage() {
  const confirm = useConfirmation();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [savedEmbedding, setSavedEmbedding] = useState<{ provider: unknown; model: unknown }>();
  const [notice, setNotice] = useState("");
  const [diagnostics, setDiagnostics] = useState<{
    windows: { data_path: string; ollama_base_url: string };
    workflows: Record<string, number>;
    reconciliation: { state: string; message: string };
  }>();
  const [embedding, setEmbedding] = useState<{
    installed: boolean;
    dimension: number | null;
    model: string;
  }>();
  const [providerStatus, setProviderStatus] = useState<ProviderStatus>();
  const [apiProvider, setApiProvider] = useState<ProviderName>("openai");
  const [apiKey, setApiKey] = useState("");
  const [downloadDialogOpen, setDownloadDialogOpen] = useState(false);
  const [modelToDownload, setModelToDownload] = useState<string>();
  const [modelFilter, setModelFilter] = useState("");
  const [ollamaCatalog, setOllamaCatalog] = useState<OllamaCatalogModel[]>([]);
  const [pullOperation, setPullOperation] = useState<OllamaPullOperation>();
  useEffect(() => {
    void apiClient
      .getSettings()
      .then((data) => {
        // Conversation summaries and answer synthesis run only through OpenAI; normalize a
        // legacy assignment so a save never re-submits a provider the backend cannot run.
        const loaded = { ...data.settings };
        for (const layer of ["summary", "answer"]) {
          const provider = loaded[`${layer}_provider`];
          if (provider && provider !== "openai") {
            loaded[`${layer}_provider`] = "openai";
            loaded[`${layer}_model`] = "";
          }
        }
        setValues(loaded);
        setSavedEmbedding({ provider: data.settings.embedding_provider, model: data.settings.embedding_model });
        const configuredProvider = layers
          .map(([layer]) => data.settings[`${layer}_provider`])
          .find((provider) => provider === "openai" || provider === "anthropic");
        if (configuredProvider) setApiProvider(configuredProvider as ProviderName);
      })
      .catch(() => setNotice("Settings service is unavailable."));
    void apiClient.diagnostics().then(setDiagnostics);
    void apiClient.embeddingStatus().then(setEmbedding);
    void apiClient.providerStatus().then((status) => {
      setProviderStatus(status);
      setValues((current) => {
        const next = { ...current };
        for (const [layer] of layers) {
          const provider = next[`${layer}_provider`] as ProviderName;
          if (provider !== "openai" && provider !== "anthropic") continue;
          const compatible = (status.capabilities[provider] ?? []).filter((model) =>
            layer === "embedding" ? model.embeddings : model.chat,
          );
          const selected = String(next[`${layer}_model`] ?? "");
          if (layer !== "embedding" && !selected && compatible.length) {
            next[`${layer}_model`] = compatible[0].model;
          }
        }
        return next;
      });
    });
  }, []);
  useEffect(() => {
    if (pullOperation?.status !== "running") return;
    const timer = window.setTimeout(() => {
      void apiClient
        .ollamaPullStatus(pullOperation.operation_id)
        .then((operation) => {
          setPullOperation(operation);
          if (operation.status === "completed") {
            setNotice(`${operation.model} downloaded.`);
            void apiClient.providerStatus().then(setProviderStatus);
            void apiClient.embeddingStatus().then(setEmbedding);
          }
        })
        .catch(() => setNotice("Ollama model download status is unavailable."));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [pullOperation]);
  useEffect(() => {
    if (!downloadDialogOpen || ollamaCatalog.length) return;
    void apiClient
      .ollamaCatalog()
      .then(({ models }) => setOllamaCatalog(models))
      .catch(() => setNotice("Ollama model catalog is unavailable."));
  }, [downloadDialogOpen, ollamaCatalog.length]);
  const set = (key: string, value: unknown) =>
    setValues({ ...values, [key]: value });
  const field = (key: string, label: string) => (
    <ALabel className="grid gap-1" key={key}>
      {label}
      <AInput
        value={String(values[key] ?? "")}
        onChange={(event) => set(key, Number(event.target.value))}
      />
    </ALabel>
  );
  const modelsFor = (provider: ProviderName, layer: string) =>
    (providerStatus?.capabilities[provider] ?? []).filter((model) =>
      layer === "embedding" ? model.embeddings : model.chat,
    );
  const apiKeyConfigured = Boolean(
    providerStatus?.providers.find((provider) => provider.provider === apiProvider)?.configured,
  );
  const selectAssignmentProvider = (layer: string, provider: ProviderName) => {
    const models = modelsFor(provider, layer);
    setValues({
      ...values,
      [`${layer}_provider`]: provider,
      [`${layer}_model`]: layer === "embedding" ? "" : models[0]?.model ?? "",
    });
  };
  const selectProjectApiProvider = (provider: ProviderName) => {
    setApiProvider(provider);
    const next = { ...values };
    for (const [layer] of layers) {
      if (layer.startsWith("graphrag_") || openAiOnlyLayer(layer)) continue;
      if (next[`${layer}_provider`] === "ollama") continue;
      next[`${layer}_provider`] = provider;
      next[`${layer}_model`] = modelsFor(provider, layer)[0]?.model ?? "";
    }
    setValues(next);
  };
  const assignment = (layer: string, label: string) => {
    const graphRagLayer = layer.startsWith("graphrag_");
    const plannerLayer = layer.startsWith("semantic_planner_");
    const openAiOnly = openAiOnlyLayer(layer);
    const provider = (values[`${layer}_provider`] ?? (graphRagLayer || openAiOnly ? "openai" : apiProvider)) as ProviderName;
    const isLocal = provider === "ollama";
    const compatibleModels = modelsFor(provider, layer);
    const modelOptions = compatibleModels.map((model) => ({
      label: model.model,
      value: model.model,
    }));
    return (
      <section className="settings-assignment" key={layer}>
        <div className="settings-assignment__heading">
          <strong>{label}</strong>
          <AInfo description={layerDescriptions[layer]} position="right" />
        </div>
        <div className="settings-assignment__fields">
          {!openAiOnly && <div className="settings-assignment__source" role="radiogroup" aria-label={`${label} model source`}>
            <ALabel className="a-label--inline">
              <ARadio checked={isLocal} name={`${layer}-source`} value="local" onChange={() => selectAssignmentProvider(layer, "ollama")} />
              Local
            </ALabel>
            <ALabel className="a-label--inline">
              <ARadio checked={!isLocal} name={`${layer}-source`} value="api" onChange={() => selectAssignmentProvider(layer, graphRagLayer ? "openai" : apiProvider)} />
              API
            </ALabel>
          </div>}
          {plannerLayer && <small>OpenAI Responses strict structured output</small>}
          {openAiOnly && !plannerLayer && <small>OpenAI</small>}
          <ALabel aria-label={`${label} model`}>
            <ASelect
              value={String(values[`${layer}_model`] ?? "")}
              options={modelOptions}
              disabled={modelOptions.length === 0}
              placeholder={modelOptions.length ? "Select a model" : "No compatible model available"}
              onChange={(event) => set(`${layer}_model`, event.value)}
            />
          </ALabel>
        </div>
        {isLocal && !openAiOnly && modelOptions.length === 0 && <small>Ollama could not provide a compatible installed model.</small>}
      </section>
    );
  };
  const startModelDownload = () => {
    if (!modelToDownload) return;
    void apiClient
      .pullOllamaModel(modelToDownload)
      .then((operation) => {
        setPullOperation(operation);
        setNotice(`${operation.model} download started.`);
      })
      .catch(() => setNotice("Ollama model download could not be started."));
  };
  const saveApiKey = () => {
    if (!apiKey.trim()) {
      setNotice("Enter an API key before saving.");
      return;
    }
    void apiClient
      .validateProvider(apiProvider, apiKey.trim())
      .then((result) => {
        setApiKey("");
        setNotice(`${result.provider} connection: ${result.status}.`);
        return apiClient.providerStatus();
      })
      .then(setProviderStatus)
      .catch((error: unknown) =>
        setNotice(
          error instanceof Error
            ? error.message
            : "The API key could not be saved or validated.",
        ),
      );
  };
  const save = async () => {
    const changed =
      savedEmbedding !== undefined &&
      (values.embedding_provider !== savedEmbedding.provider || values.embedding_model !== savedEmbedding.model);
    if (changed) {
      const accepted = await confirm({
        title: "Embedding ayarını değiştir",
        message: "Embedding ayarını değiştirmek, tam bir dense reindex işlemi gerektirir. Devam edilsin mi?",
        confirmLabel: "Kaydet ve yeniden indeksle",
      });
      if (!accepted) return;
    }
    void apiClient
      .updateSettings({ ...values, embedding_change_confirmed: changed })
      .then((result) => {
        setValues(result.settings);
        setSavedEmbedding({ provider: result.settings.embedding_provider, model: result.settings.embedding_model });
        setNotice(
          result.reindex_required
            ? "Saved. Workspaces were marked for reindexing."
            : "Saved.",
        );
      })
      .catch(() =>
        setNotice(
          "Settings were rejected; check model/provider compatibility.",
        ),
      );
  };
  return (
    <div className="grid gap-4">
      <ACard title="Operational and embedding controls">
        <div className="settings-operational-layout">
          <section>
            <h3>Global operational settings</h3>
            <AInfoPanel>These settings apply to every workspace. Embedding or chunking changes require a full reindex.</AInfoPanel>
            <div className="mt-4 grid grid-cols-2 gap-4">
              {field("upload_max_bytes", "Maximum upload bytes")}
              {field("dense_top_k", "Dense retrieval top-k")}
              {field("bm25_top_k", "BM25 retrieval top-k")}
              {field("final_evidence_top_k", "Final evidence top-k")}
              {field("graphrag_pending_document_threshold", "GraphRAG pending threshold")}
              {field("workflow_retention_days", "Workflow retention days")}
              {field("conversation_memory_window_messages", "Conversation memory messages")}
            </div>
          </section>
          <section>
            <h3>Embedding controls</h3>
            <AInfoPanel>
              {embedding
                ? `${embedding.model}: ${embedding.installed ? "installed" : "missing"}; dimensions: ${embedding.dimension ?? "run health test"}; digest/version: unavailable until provider reports it.`
                : "Loading model status…"}{" "}
              Changing it requires full dense reindexing.
            </AInfoPanel>
            <div className="mt-4 grid grid-cols-2 gap-4">
              {field("embedding_batch_size", "Batch size")}
              {field("embedding_timeout_seconds", "Timeout seconds")}
              {field("embedding_concurrency", "Concurrency")}
              <ALabel>
                Keep alive
                <AInput value={String(values.embedding_keep_alive ?? "5m")} onChange={(event) => set("embedding_keep_alive", event.target.value)} />
              </ALabel>
            </div>
            <AButton className="mt-4" label="Run embedding health test" onClick={() => void apiClient.embeddingHealth().then((result) => {
              setEmbedding({ installed: true, model: result.model, dimension: result.dimension });
              setNotice(`Embedding healthy: ${result.model}, ${result.dimension} dimensions.`);
            }).catch(() => setNotice("Embedding health test failed."))} />
          </section>
        </div>
      </ACard>
      <ACard title="Model assignments and API provider credentials">
        <AInfoPanel>
          Select one API provider for the project. Each layer can then use that API
          provider or a Local Ollama model.
        </AInfoPanel>
        <div className="settings-model-layout mt-4">
          <aside className="settings-provider-panel">
            <ALabel>
              API provider
              <ASelect value={apiProvider} options={apiProviders.map((provider) => ({ label: provider, value: provider }))} onChange={(event) => selectProjectApiProvider(event.value as ProviderName)} />
            </ALabel>
            <ALabel>
              API key
              <AInput type="password" value={apiKey} autoComplete="new-password" placeholder={apiKeyConfigured ? "••••••••••••" : "Enter API key"} onChange={(event) => setApiKey(event.target.value)} />
            </ALabel>
            <AButton label="Save & validate" onClick={saveApiKey} />
            <div className="settings-provider-panel__separator" />
            <AButton label="Add Ollama model" outlined onClick={() => { setModelToDownload(undefined); setModelFilter(""); setDownloadDialogOpen(true); }} />
            <small>{apiKeyConfigured ? "API key saved securely: ••••••••••••" : "API keys are stored securely and are never returned to the browser."}</small>
          </aside>
          <div className="settings-model-assignments">
            {layers.map(([layer, label]) => assignment(layer, label))}
            <section className="settings-assignment">
              <ALabel className="a-label--inline">
                <ACheckbox checked={Boolean(values.answer_synthesis_enabled)} onChange={(event) => set("answer_synthesis_enabled", Boolean(event.checked))} />
                Enable grounded answer synthesis (OpenAI; off by default)
              </ALabel>
              <ALabel>
                Answer style
                <ASelect value={String(values.answer_style ?? "balanced")} options={["concise", "balanced", "detailed"]} onChange={(event) => set("answer_style", event.value)} />
              </ALabel>
            </section>
            <section className="settings-assignment">
              <strong>Smart GraphRAG search</strong>
              <ALabel className="a-label--inline">
                <ACheckbox checked={Boolean(values.graphrag_smart_search_enabled)} onChange={(event) => set("graphrag_smart_search_enabled", Boolean(event.checked))} />
                Enabled (off by default)
              </ALabel>
              <small>
                Only GraphRAG's selection step runs; its written answer is never generated. Local uses
                embeddings only (no model calls). Global rates community summaries with the Global
                model. DRIFT makes one call with the DRIFT model. Repeated questions reuse cached
                selections, and spend is recorded in cost controls.
              </small>
            </section>
            <section className="settings-assignment">
              <strong>DRIFT selection</strong>
              <div className="mt-3 grid grid-cols-2 gap-4">
                {field("graphrag_drift_k_followups", "Community reports selected")}
                {field("graphrag_drift_primer_folds", "Primer folds")}
              </div>
            </section>
          </div>
        </div>
      </ACard>
      {/* Legacy embedding controls consolidated into the card above.
        <AInfoPanel>
          {embedding
            ? `${embedding.model}: ${embedding.installed ? "installed" : "missing"}; dimensions: ${embedding.dimension ?? "run health test"}; digest/version: unavailable until provider reports it.`
            : "Loading model status…"}{" "}
          Changing it requires full dense reindexing.
        </AInfoPanel>
        <div className="mt-3 grid grid-cols-2 gap-4">
          {field("embedding_batch_size", "Batch size")}
          {field("embedding_timeout_seconds", "Timeout seconds")}
          {field("embedding_concurrency", "Concurrency")}
          <ALabel>
            Keep alive
            <AInput
              value={String(values.embedding_keep_alive ?? "5m")}
              onChange={(event) =>
                set("embedding_keep_alive", event.target.value)
              }
            />
          </ALabel>
        </div>
        <AButton
          className="mt-3"
          label="Run embedding health test"
          onClick={() =>
            void apiClient
              .embeddingHealth()
              .then((result) => {
                setEmbedding({
                  installed: true,
                  model: result.model,
                  dimension: result.dimension,
                });
                setNotice(
                  `Embedding healthy: ${result.model}, ${result.dimension} dimensions.`,
                );
              })
              .catch(() => setNotice("Embedding health test failed."))
          }
        />
      */}
      <ACard title="Windows and workflow diagnostics">
        <AInfoPanel>
          {diagnostics
            ? `Data: ${diagnostics.windows.data_path}; Ollama: ${diagnostics.windows.ollama_base_url}; interrupted: ${diagnostics.workflows.interrupted}; failed: ${diagnostics.workflows.failed}. ${diagnostics.reconciliation.message}`
            : "Loading diagnostics…"}
        </AInfoPanel>
      </ACard>
      <div className="flex items-center gap-3">
        <AButton label="Save settings" onClick={save} />
        <AButton
          label="Reset defaults"
          outlined
          onClick={() =>
            void apiClient.resetSettings().then((result) => {
              setValues(result.settings);
              setNotice("Defaults restored.");
            })
          }
        />
        <span className="text-sm">{notice}</span>
      </div>
      <ADialog
        visible={downloadDialogOpen}
        header="Add Ollama model"
        onHide={() => !pullOperation || pullOperation.status !== "running" ? setDownloadDialogOpen(false) : undefined}
        style={{ width: "min(520px, calc(100vw - 32px))" }}
        footer={<div className="flex justify-end gap-2"><AButton label="Close" outlined disabled={pullOperation?.status === "running"} onClick={() => setDownloadDialogOpen(false)} /><AButton label={pullOperation?.status === "running" ? "Downloading…" : "Download"} disabled={pullOperation?.status === "running" || !modelToDownload} onClick={startModelDownload} /></div>}
      >
        <AInfoPanel>Select a model from the official Ollama library. Downloads start only after you select Download.</AInfoPanel>
        <ALabel className="mt-4">
          Search models
          <AInput value={modelFilter} placeholder="Search Ollama library" disabled={pullOperation?.status === "running"} onChange={(event) => setModelFilter(event.target.value)} />
        </ALabel>
        <div className="ollama-model-list mt-3" role="listbox" aria-label="Ollama model catalog">
          {ollamaCatalog.filter((model) => `${model.name} ${model.description}`.toLocaleLowerCase().includes(modelFilter.toLocaleLowerCase())).map((model) => <button className={modelToDownload === model.name ? "is-selected" : undefined} key={model.name} type="button" role="option" aria-selected={modelToDownload === model.name} disabled={pullOperation?.status === "running"} onClick={() => setModelToDownload(model.name)}><span><strong>{model.name}</strong><small>{model.description}</small></span><em>{[...model.capabilities, ...model.sizes].join(" · ")}</em></button>)}
          {!ollamaCatalog.length && <span className="ollama-model-list__empty">Loading official model catalog…</span>}
        </div>
        {pullOperation && <div className="settings-download-progress mt-4"><strong>{pullOperation.model}</strong><span>{pullOperation.status === "failed" ? pullOperation.error : pullOperation.status === "completed" ? "Downloaded" : `${pullOperation.total ? Math.round((pullOperation.completed / pullOperation.total) * 100) : 0}% downloaded`}</span>{pullOperation.status === "running" && <progress value={pullOperation.completed} max={pullOperation.total || 1} />}</div>}
      </ADialog>
    </div>
  );
}
