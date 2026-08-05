import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiClient, type CatalogDocument, type Workspace } from "../api/client";
import { AButton, ACard, AFileUpload, AInfo, AInput, ASelect, ATextarea } from "../components/ui";

function useWorkspaces() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => { try { setWorkspaces(await apiClient.listWorkspaces()); setError(null); } catch { setError("Çalışma alanları alınamadı."); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  return { workspaces, error, refresh };
}

function WorkspaceSelect({ workspaces, value, onChange }: { workspaces: Workspace[]; value: string; onChange: (id: string) => void }) {
  return <ASelect value={value} onChange={(event) => onChange(event.value)} options={workspaces.map((w) => ({ label: w.name, value: w.id }))} placeholder="Çalışma alanı seçin" className="max-w-md" />;
}

export function DashboardPage() {
  const [data, setData] = useState<Awaited<ReturnType<typeof apiClient.overview>> | null>(null);
  useEffect(() => { void apiClient.overview().then(setData).catch(() => setData(null)); }, []);
  return <div className="page-stack">
    <section className="page-hero"><div><p className="eyebrow">Genel görünüm</p><h1>Bilgi çalışma alanınız</h1><p>Belgeler, indeksler ve arka plan işlemleri tek yerde.</p></div><Link to="/upload"><AButton label="Belge yükle" icon="upload" /></Link></section>
    <div className="metric-grid">{[["Çalışma alanı", data?.workspace_count], ["Belge", data?.document_count], ["Parça", data?.chunk_count]].map(([label, value]) => <ACard key={String(label)}><span className="metric-label">{label}</span><strong className="metric-value">{value ?? "—"}</strong></ACard>)}</div>
    <ACard title="Son güncellenen belgeler">{data?.recent_documents.length ? <div className="resource-list">{data.recent_documents.map((doc) => <Link key={doc.id} to={`/documents/${doc.id}?workspace=${doc.workspace_id}`}><strong>{doc.title}</strong><span>{doc.workspace_name} · {new Date(doc.updated_at).toLocaleDateString("tr-TR")}</span></Link>)}</div> : <AInfo title="Henüz içerik yok">Bir çalışma alanı oluşturup belge yükleyerek başlayın.</AInfo>}</ACard>
  </div>;
}

export function WorkspacesPage() {
  const { workspaces, error, refresh } = useWorkspaces(); const [name, setName] = useState(""); const [description, setDescription] = useState(""); const [saving, setSaving] = useState(false);
  const create = async (event: FormEvent) => { event.preventDefault(); const slug = name.trim().toLocaleLowerCase("tr-TR").replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, ""); if (!slug) return; setSaving(true); try { await apiClient.createWorkspace(name.trim(), slug, description.trim()); setName(""); setDescription(""); await refresh(); } finally { setSaving(false); } };
  return <div className="page-stack two-column"><ACard title="Çalışma alanları">{error && <p role="alert">{error}</p>}<div className="resource-list">{workspaces.map((w) => <Link key={w.id} to={`/workspace/${w.id}`}><strong>{w.name}</strong><span>{w.description || w.slug}</span></Link>)}{!workspaces.length && <AInfo title="İlk çalışma alanınızı oluşturun">Her alan, belgelerini ve indekslerini birbirinden izole tutar.</AInfo>}</div></ACard><ACard title="Yeni çalışma alanı"><form className="form-stack" onSubmit={create}><AInput value={name} onChange={(e) => setName(e.target.value)} placeholder="Örn. Osmanlı arşivi" required /><ATextarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Kısa açıklama (isteğe bağlı)" rows={3} /><AButton type="submit" label="Oluştur" disabled={saving} /></form></ACard></div>;
}

export function WorkspaceOverviewPage() {
  const { workspaceId = "" } = useParams(); const [data, setData] = useState<Awaited<ReturnType<typeof apiClient.workspaceOverview>> | null>(null);
  useEffect(() => { if (workspaceId) void apiClient.workspaceOverview(workspaceId).then(setData); }, [workspaceId]);
  return <div className="page-stack"><section className="page-hero"><div><p className="eyebrow">Çalışma alanı</p><h1>İndeks ve içerik durumu</h1></div><Link to={`/upload?workspace=${workspaceId}`}><AButton label="Belge yükle" icon="upload" /></Link></section><div className="metric-grid">{[["Belge", data?.document_count], ["Parça", data?.chunk_count], ["Graf bekleyen", data?.pending_graph_documents]].map(([label, value]) => <ACard key={String(label)}><span className="metric-label">{label}</span><strong className="metric-value">{value ?? "—"}</strong></ACard>)}</div><ACard title="İndeksler"><div className="status-grid"><span>Yoğun arama <b>{data?.dense_state ?? "—"}</b></span><span>Seyrek arama <b>{data?.sparse_state ?? "—"}</b></span><span>GraphRAG <b>{data?.graphrag_state ?? "—"}</b></span></div></ACard></div>;
}

export function DocumentsPage() {
  const { workspaces } = useWorkspaces(); const [workspaceId, setWorkspaceId] = useState(""); const [documents, setDocuments] = useState<CatalogDocument[]>([]); const navigate = useNavigate();
  useEffect(() => { if (!workspaceId && workspaces[0]) setWorkspaceId(workspaces[0].id); }, [workspaceId, workspaces]);
  const refresh = useCallback(() => { if (workspaceId) void apiClient.listDocuments(workspaceId).then(setDocuments); }, [workspaceId]); useEffect(refresh, [refresh]);
  const remove = async (documentId: string) => { if (workspaceId && window.confirm("Belge silme işlemi arka plan sürecinde yürütülecek. Devam edilsin mi?")) { await apiClient.deleteDocument(workspaceId, documentId); refresh(); } };
  return <div className="page-stack"><section className="page-hero compact"><div><p className="eyebrow">Arşiv</p><h1>Belgeler</h1></div><Link to={`/upload?workspace=${workspaceId}`}><AButton label="Belge yükle" icon="upload" /></Link></section><WorkspaceSelect workspaces={workspaces} value={workspaceId} onChange={setWorkspaceId} /><ACard>{documents.length ? <div className="document-table">{documents.map((doc) => <div key={doc.id}><button type="button" className="document-link" onClick={() => navigate(`/documents/${doc.id}?workspace=${workspaceId}`)}><strong>{doc.title}</strong><span>{doc.state ?? "hazır"} · sürüm {doc.version_number ?? "—"} · {doc.size_bytes ? `${Math.ceil(doc.size_bytes / 1024)} KB` : ""}</span></button><AButton label="Sil" text severity="secondary" onClick={() => void remove(doc.id)} /></div>)}</div> : <AInfo title="Belge bulunamadı">Seçili çalışma alanına henüz belge yüklenmedi.</AInfo>}</ACard></div>;
}

export function DocumentDetailPage() {
  const { documentId = "" } = useParams(); const [detail, setDetail] = useState<Awaited<ReturnType<typeof apiClient.documentDetails>> | null>(null); const params = new URLSearchParams(window.location.search); const workspaceId = params.get("workspace") || "";
  useEffect(() => { if (workspaceId && documentId) void apiClient.documentDetails(workspaceId, documentId).then(setDetail); }, [workspaceId, documentId]);
  if (!workspaceId) return <AInfo title="Çalışma alanı gerekli">Belgeye çalışma alanı bağlamı olmadan erişilemez.</AInfo>;
  return <div className="page-stack"><Link to="/documents">← Belgelere dön</Link><ACard title={detail?.title ?? "Belge"}><div className="status-grid"><span>Sürüm <b>{detail?.version_number ?? "—"}</b></span><span>Parça <b>{detail?.chunk_count ?? "—"}</b></span><span>Durum <b>{detail?.state ?? "—"}</b></span></div></ACard><ACard title="Normalize edilmiş içerik"><pre className="document-preview">{detail?.normalized_content ?? "İçerik yükleniyor veya dosya artık erişilebilir değil."}</pre></ACard></div>;
}

export function UploadPage() {
  const { workspaces } = useWorkspaces(); const params = new URLSearchParams(window.location.search); const [workspaceId, setWorkspaceId] = useState(params.get("workspace") || ""); const [files, setFiles] = useState<File[]>([]); const [message, setMessage] = useState("");
  useEffect(() => { if (!workspaceId && workspaces[0]) setWorkspaceId(workspaces[0].id); }, [workspaceId, workspaces]);
  const upload = async () => { if (!workspaceId || !files.length) return; try { const result = await apiClient.upload(workspaceId, files); setMessage(`${result.uploads.length} belge alındı; indeksleme arka planda başlatıldı.`); setFiles([]); } catch { setMessage("Yükleme tamamlanamadı. Dosya biçimini ve yinelenen içeriği kontrol edin."); } };
  return <div className="page-stack two-column"><ACard title="Belge yükle"><div className="form-stack"><WorkspaceSelect workspaces={workspaces} value={workspaceId} onChange={setWorkspaceId} /><AFileUpload multiple accept=".md,.txt,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} /><AButton label="Yükle ve indeksle" icon="upload" onClick={() => void upload()} disabled={!workspaceId || !files.length} />{message && <AInfo>{message}</AInfo>}</div></ACard><ACard title="Yükleme akışı"><p>Kaynak dosya korunur, Markdown’a dönüştürülür, parçalara ayrılır ve kalıcı bir indeksleme süreci başlatılır.</p><p className="text-sm opacity-70">Desteklenen biçimler: Markdown, metin, PDF ve DOCX.</p></ACard></div>;
}

export function GraphPage() { const { workspaces } = useWorkspaces(); const [id, setId] = useState(""); const [data, setData] = useState<Awaited<ReturnType<typeof apiClient.workspaceOverview>> | null>(null); useEffect(() => { if (!id && workspaces[0]) setId(workspaces[0].id); }, [id, workspaces]); useEffect(() => { if (id) void apiClient.workspaceOverview(id).then(setData); }, [id]); return <div className="page-stack"><WorkspaceSelect workspaces={workspaces} value={id} onChange={setId} /><ACard title="GraphRAG durumu"><AInfo title={data?.graphrag_state === "ready" ? "Graf sorguya hazır" : "Graf henüz hazır değil"}>Bekleyen belge: {data?.pending_graph_documents ?? "—"}. Grafik düğümleri, GraphRAG indeksleme tamamlandığında burada görselleştirilir.</AInfo></ACard></div>; }

export function HealthPage() { const [health, setHealth] = useState<{ status: string; services: Record<string, string> } | null>(null); useEffect(() => { void apiClient.getHealth().then(setHealth); }, []); return <div className="page-stack"><ACard title="Sistem sağlığı"><div className="status-grid">{Object.entries(health?.services ?? {}).map(([name, state]) => <span key={name}>{name}<b>{state}</b></span>)}</div></ACard></div>; }
