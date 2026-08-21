import { useCallback, useEffect, useMemo, useState } from "react";
import {
  apiClient,
  type CanonicalEntity,
  type EntityEvidence,
  type IdentityOperation,
  type KnowledgeGeneration,
} from "../api/client";
import { useWorkspace } from "../app/workspace";
import {
  ABadge,
  AButton,
  ACard,
  AColumn,
  AInfoPanel,
  AInput,
  ASelect,
  ATable,
  ATextarea,
} from "../components/ui";

const splitIds = (value: string) => value.split(",").map((item) => item.trim()).filter(Boolean);

export function KnowledgeCurationPage() {
  const { workspaceId } = useWorkspace();
  const [entities, setEntities] = useState<CanonicalEntity[]>([]);
  const [history, setHistory] = useState<IdentityOperation[]>([]);
  const [evidence, setEvidence] = useState<EntityEvidence[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [alias, setAlias] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");
  const [reason, setReason] = useState("");
  const [splitNameA, setSplitNameA] = useState("");
  const [splitNameB, setSplitNameB] = useState("");
  const [splitMentionsA, setSplitMentionsA] = useState("");
  const [splitMentionsB, setSplitMentionsB] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [generations, setGenerations] = useState<KnowledgeGeneration[]>([]);

  const selected = entities.find((entity) => entity.entity_id === selectedId) ?? null;
  const mergeOptions = useMemo(
    () => entities
      .filter((entity) => entity.entity_id !== selectedId && entity.status === "active")
      .map((entity) => ({ label: entity.display_name, value: entity.entity_id })),
    [entities, selectedId],
  );

  const refresh = useCallback(async () => {
    if (!workspaceId) return;
    try {
      const [nextEntities, nextHistory, nextGenerations] = await Promise.all([
        apiClient.listCanonicalEntities(workspaceId),
        apiClient.identityHistory(workspaceId),
        apiClient.knowledgeReadiness(workspaceId),
      ]);
      setEntities(nextEntities);
      setHistory(nextHistory);
      setGenerations(nextGenerations);
      setSelectedId((current) =>
        nextEntities.some((entity) => entity.entity_id === current)
          ? current
          : (nextEntities[0]?.entity_id ?? ""),
      );
      setError(null);
    } catch {
      setError("Canonical bilgi servisine ulaşılamadı.");
    }
  }, [workspaceId]);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    if (!workspaceId || !selectedId) {
      setEvidence([]);
      return;
    }
    void apiClient.entityEvidence(workspaceId, selectedId).then(setEvidence).catch(() => setEvidence([]));
  }, [selectedId, workspaceId]);

  const mutate = async (operation: () => Promise<unknown>) => {
    if (!reason.trim()) {
      setError("Her manuel curation işlemi için bir gerekçe gereklidir.");
      return;
    }
    setBusy(true);
    try {
      await operation();
      setAlias("");
      setMergeTarget("");
      setReason("");
      await refresh();
    } catch {
      setError("Curation işlemi uygulanamadı; entity ve evidence seçimini kontrol edin.");
    } finally {
      setBusy(false);
    }
  };

  const evidenceIds = evidence.map((item) => item.evidence_id);
  const mentionIds = evidence.map((item) => item.mention_id);

  return (
    <div className="page-stack knowledge-curation">
      <AInfoPanel title="Canonical bilgi curation">
        Manuel kararlar extracted ve validated bilgiden üstündür. Merge, split ve alias kaldırma
        işlemleri kaynak kayıtları silmez; evidence ve karar geçmişi korunur.
      </AInfoPanel>
      {error && <AInfoPanel title="İşlem uyarısı">{error}</AInfoPanel>}
      <ACard title="Knowledge generation readiness">
        <ATable value={generations} emptyMessage="Henüz knowledge generation yok." size="small">
          <AColumn field="generation_id" header="Generation" />
          <AColumn
            header="Durum"
            body={(generation: KnowledgeGeneration) => <ABadge value={generation.state} />}
          />
          <AColumn
            header="Hazır stages"
            body={(generation: KnowledgeGeneration) =>
              `${generation.stages.filter((stage) => stage.state === "ready").length}/${generation.stages.length}`}
          />
          <AColumn
            header="Workflow"
            body={(generation: KnowledgeGeneration) => generation.workflow_run_id ?? "—"}
          />
        </ATable>
      </ACard>
      <div className="two-column">
        <ACard title="Canonical entity’ler">
          <ATable value={entities} emptyMessage="Canonical entity henüz oluşturulmadı." size="small">
            <AColumn field="display_name" header="Ad" />
            <AColumn field="entity_type" header="Tip" />
            <AColumn
              header="Otorite"
              body={(entity: CanonicalEntity) => <ABadge value={entity.authority} />}
            />
            <AColumn field="status" header="Durum" />
            <AColumn
              header="İncele"
              body={(entity: CanonicalEntity) => (
                <AButton
                  label={entity.entity_id === selectedId ? "Seçili" : "Seç"}
                  text
                  onClick={() => setSelectedId(entity.entity_id)}
                />
              )}
            />
          </ATable>
        </ACard>
        <ACard title={selected ? selected.display_name : "Entity ayrıntısı"}>
          {!selected ? (
            <p>Evidence ve curation işlemleri için bir entity seçin.</p>
          ) : (
            <div className="form-stack">
              <div><strong>Alias’lar:</strong> {selected.aliases.join(", ") || "—"}</div>
              <AInput value={alias} onChange={(event) => setAlias(event.target.value)} placeholder="Alias" />
              <div className="flex flex-wrap gap-2">
                <AButton
                  label="Alias ekle"
                  disabled={busy || !alias.trim()}
                  onClick={() => void mutate(() => apiClient.addCanonicalAlias(
                    workspaceId, selected.entity_id, alias, reason,
                  ))}
                />
                <AButton
                  label="Alias kaldır"
                  severity="secondary"
                  disabled={busy || !alias.trim()}
                  onClick={() => void mutate(() => apiClient.removeCanonicalAlias(
                    workspaceId, selected.entity_id, alias, reason,
                  ))}
                />
              </div>
              <ASelect
                value={mergeTarget}
                options={mergeOptions}
                onChange={(event) => setMergeTarget(event.value)}
                placeholder="Birleştirilecek entity"
              />
              <AButton
                label="Seçili entity ile birleştir"
                disabled={busy || !mergeTarget}
                onClick={() => void mutate(() => apiClient.mergeCanonicalEntities(workspaceId, {
                  primary_entity_id: selected.entity_id,
                  merged_entity_ids: [mergeTarget],
                  evidence_ids: evidenceIds,
                  reason,
                }))}
              />
              <ATextarea
                value={reason}
                rows={3}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Zorunlu curation gerekçesi"
              />
            </div>
          )}
        </ACard>
      </div>
      <ACard title="Exact-source evidence ve mention’lar">
        <ATable value={evidence} emptyMessage="Bu entity için evidence bulunamadı." size="small">
          <AColumn field="original_text" header="Mention" />
          <AColumn field="source_text" header="Exact span" />
          <AColumn field="document_version_id" header="Belge sürümü" />
          <AColumn field="chunk_id" header="Chunk" />
          <AColumn
            header="Offset"
            body={(item: EntityEvidence) => `${item.start_offset}:${item.end_offset}`}
          />
          <AColumn field="validation_state" header="Doğrulama" />
        </ATable>
      </ACard>
      {selected && mentionIds.length > 1 && (
        <ACard title="Entity’yi iki kimliğe ayır">
          <div className="knowledge-curation__split-grid">
            <AInput value={splitNameA} onChange={(event) => setSplitNameA(event.target.value)} placeholder="İlk entity adı" />
            <AInput value={splitMentionsA} onChange={(event) => setSplitMentionsA(event.target.value)} placeholder={`Mention ID’leri: ${mentionIds[0]}`} />
            <AInput value={splitNameB} onChange={(event) => setSplitNameB(event.target.value)} placeholder="İkinci entity adı" />
            <AInput value={splitMentionsB} onChange={(event) => setSplitMentionsB(event.target.value)} placeholder={`Mention ID’leri: ${mentionIds.slice(1).join(", ")}`} />
          </div>
          <AButton
            label="Split uygula"
            disabled={busy || !splitNameA || !splitNameB}
            onClick={() => void mutate(() => apiClient.splitCanonicalEntity(workspaceId, selected.entity_id, {
              partitions: [
                { display_name: splitNameA, mention_ids: splitIds(splitMentionsA) },
                { display_name: splitNameB, mention_ids: splitIds(splitMentionsB) },
              ],
              evidence_ids: evidenceIds,
              reason,
            }))}
          />
        </ACard>
      )}
      <ACard title="Merge / split / alias geçmişi">
        <ATable value={history} emptyMessage="Henüz manuel curation işlemi yok." size="small">
          <AColumn field="kind" header="İşlem" />
          <AColumn field="reason" header="Gerekçe" />
          <AColumn field="authority" header="Otorite" />
          <AColumn
            header="Kaynak → sonuç"
            body={(item: IdentityOperation) =>
              `${item.source_entity_ids.length} → ${item.result_entity_ids.length}`}
          />
        </ATable>
      </ACard>
    </div>
  );
}
