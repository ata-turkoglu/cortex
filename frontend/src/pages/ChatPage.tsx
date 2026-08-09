import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import {
  apiClient,
  type ChatMessage,
  type Conversation,
  type QueryDebug,
  type Workspace,
} from "../api/client";
import { AButton, ADialog, AInfoPanel, ALabel, ASelect, ATextarea, useConfirmation } from "../components/ui";
import { AIcon } from "../icons/AIcon";

type Mode = "automatic" | "document_search" | "deep_analysis";
type Source = { content: string; document_title: string; version_number: number };

const suggestions = [
  "Bu çalışma alanındaki önemli konuları özetle",
  "Belgelerdeki ortak temaları bul",
  "En önemli bulguları kaynaklarıyla açıkla",
];

function conversationTitleFromQuestion(question: string) {
  const normalized = question.replace(/\s+/g, " ").trim();
  return normalized.length <= 72 ? normalized : `${normalized.slice(0, 71).trimEnd()}…`;
}

export function ChatPage() {
  const [workspaceId, setWorkspaceId] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [content, setContent] = useState("");
  const [mode, setMode] = useState<Mode>("automatic");
  const [debug, setDebug] = useState<QueryDebug>();
  const [source, setSource] = useState<Source>();
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const threadAreaRef = useRef<HTMLDivElement>(null);
  const confirm = useConfirmation();

  useEffect(() => {
    apiClient.listWorkspaces()
      .then((items) => { setWorkspaces(items); if (!workspaceId && items[0]) setWorkspaceId(items[0].id); })
      .catch(() => setError("Çalışma alanları alınamadı."));
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    apiClient.listConversations(workspaceId).then(setConversations).catch(() => setError("Sohbet geçmişi yüklenemedi."));
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId || !active) return;
    apiClient.listMessages(workspaceId, active.id).then(setMessages).catch(() => setError("Mesajlar yüklenemedi."));
  }, [workspaceId, active]);

  useEffect(() => {
    const threadArea = threadAreaRef.current;
    if (threadArea) threadArea.scrollTo({ top: threadArea.scrollHeight, behavior: "smooth" });
  }, [active?.id, messages, sending]);

  async function createConversation() {
    try {
      const conversation = await apiClient.createConversation(workspaceId);
      setConversations((items) => [conversation, ...items]);
      setActive(conversation);
      setMessages([]);
      setError("");
    } catch { setError("Sohbet oluşturulamadı."); }
  }

  async function deleteConversation(conversation: Conversation) {
    if (!(await confirm({ title: "Sohbeti sil", message: `“${conversation.title}” sohbetini silmek istiyor musunuz?`, confirmLabel: "Sil", danger: true }))) return;
    try {
      await apiClient.deleteConversation(workspaceId, conversation.id);
      setConversations((items) => items.filter((item) => item.id !== conversation.id));
      if (active?.id === conversation.id) {
        setActive(undefined);
        setMessages([]);
        setDebug(undefined);
      }
    } catch { setError("Sohbet silinemedi."); }
  }

  async function submit() {
    if (!active || !content.trim() || sending) return;
    const question = content.trim();
    setSending(true);
    setError("");
    try {
      const answer = await apiClient.ask(workspaceId, active.id, question, mode);
      const title = conversationTitleFromQuestion(question);
      setConversations((items) => items.map((item) => (
        item.id === active.id && item.title === "New conversation" ? { ...item, title } : item
      )));
      setActive((item) => (
        item?.id === active.id && item.title === "New conversation" ? { ...item, title } : item
      ));
      setMessages((items) => [...items, {
        id: `pending-${crypto.randomUUID()}`, role: "user", content: question, status: "completed",
        citations: [], metadata: {}, created_at: new Date().toISOString(),
      }, answer]);
      setContent("");
      const queryRunId = String(answer.metadata.query_run_id ?? "");
      if (queryRunId) setDebug(await apiClient.queryDebug(workspaceId, queryRunId));
    } catch { setError("Sorgu tamamlanamadı."); }
    finally { setSending(false); }
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); }
  }

  async function openSource(chunkId: string) {
    try { setSource(await apiClient.sourceDetails(workspaceId, chunkId)); }
    catch { setError("Kaynak ayrıntıları yüklenemedi."); }
  }

  return <>
    <div className="cortex-chat">
      <aside className="cortex-chat__history" aria-label="Sohbet geçmişi">
        <ALabel className="cortex-chat__workspace">Çalışma alanı
          <ASelect value={workspaceId} onChange={(event) => { setWorkspaceId(event.value); setActive(undefined); setMessages([]); }} options={workspaces.map((workspace) => ({ label: workspace.name, value: workspace.id }))} placeholder="Çalışma alanı seçin" />
        </ALabel>
        <AButton label="Yeni sohbet" icon="plus" disabled={!workspaceId} onClick={createConversation} />
        <p className="cortex-chat__history-heading">Sohbet geçmişi</p>
        <nav className="cortex-chat__conversation-list">
          {conversations.map((item) => <div key={item.id} className="cortex-chat__conversation">
            <button type="button" className={`cortex-chat__conversation-title${item.id === active?.id ? " is-active" : ""}`} onClick={() => setActive(item)} title={item.title}><AIcon name="chat" size={15} /><span>{item.title}</span></button>
            <AButton className="cortex-chat__conversation-delete" icon="trash" text aria-label={`${item.title} sohbetini sil`} title="Sohbeti sil" onClick={() => void deleteConversation(item)} />
          </div>)}
          {workspaceId && !conversations.length && <p className="cortex-chat__empty-history">Henüz sohbet yok.</p>}
        </nav>
      </aside>
      <section className="cortex-chat__main" aria-label="Bilgi tabanı sohbeti">
        <div ref={threadAreaRef} className="cortex-chat__thread-area">
          {error && <AInfoPanel title="Hata">{error}</AInfoPanel>}
          {!active ? <Welcome onStart={createConversation} disabled={!workspaceId} /> : messages.length === 0 ? <Welcome activeTitle={active.title} onSuggestion={setContent} /> : (
            <div className="cortex-chat__thread">
              {messages.map((message) => <Message key={message.id} message={message} onSource={openSource} />)}
              {sending && <div className="cortex-chat__thinking"><span /><span /><span /> Yanıt hazırlanıyor</div>}
            </div>
          )}
        </div>
        {active && <div className="cortex-chat__composer-wrap">
          <div className="cortex-chat__composer-toolbar"><ASelect value={mode} options={[{ label: "Otomatik", value: "automatic" }, { label: "Belge arama", value: "document_search" }, { label: "Derin analiz", value: "deep_analysis" }]} onChange={(event) => setMode(event.value as Mode)} /></div>
          <div className="cortex-chat__composer"><ATextarea value={content} onChange={(event) => setContent(event.target.value)} onKeyDown={onComposerKeyDown} rows={3} placeholder="Belgeleriniz hakkında bir soru sorun…" autoResize /><AButton icon="send" aria-label="Gönder" disabled={!content.trim() || sending} onClick={submit} /></div>
          <p>Göndermek için Enter, yeni satır için Shift + Enter kullanın.</p>
        </div>}
        {debug && <div className="cortex-chat__debug">Rota: {debug.routes.join(" + ")} · {debug.reason} · {debug.latency_ms} ms · ${debug.estimated_cost_usd}</div>}
      </section>
    </div>
    <ADialog header={source?.document_title ?? "Kaynak"} visible={Boolean(source)} onHide={() => setSource(undefined)}><p>Sürüm {source?.version_number}</p><p className="whitespace-pre-wrap">{source?.content}</p></ADialog>
  </>;
}

function Welcome({ activeTitle, disabled, onStart, onSuggestion }: { activeTitle?: string; disabled?: boolean; onStart?: () => void; onSuggestion?: (suggestion: string) => void }) {
  return <div className="cortex-chat__welcome"><div className="cortex-chat__welcome-mark"><AIcon name="sparkles" size={24} /></div><p className="eyebrow">{activeTitle ?? "Cortex Assistant"}</p><h1>{activeTitle ? "Bugün neyi inceleyelim?" : "Neyi incelemek istersiniz?"}</h1><p>Çalışma alanınızdaki belgeleri tarar, yanıtları kaynaklarıyla birlikte sunarım.</p>{onSuggestion ? <div className="cortex-chat__suggestions">{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => onSuggestion(suggestion)}><span>{suggestion}</span><span aria-hidden="true">↗</span></button>)}</div> : <AButton label="Yeni sohbet başlat" icon="plus" disabled={disabled} onClick={onStart} />}</div>;
}

function Message({ message, onSource }: { message: ChatMessage; onSource: (chunkId: string) => void }) {
  const isUser = message.role === "user";
  return <article className={`cortex-chat__message cortex-chat__message--${message.role}`}><div className="cortex-chat__avatar"><AIcon name={isUser ? "user" : "sparkles"} size={17} /></div><div className="cortex-chat__message-content"><div className="cortex-chat__message-meta"><strong>{isUser ? "Siz" : "Cortex"}</strong><time>{new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" }).format(new Date(message.created_at))}</time></div><p>{message.content}</p>{message.metadata.inference === true && <small className="cortex-chat__inference">Kaynaklara dayalı çıkarım</small>}{message.citations.length > 0 && <details className="cortex-chat__sources"><summary>{message.citations.length} kaynak göster</summary><div>{message.citations.map((citation) => <button key={citation.chunk_id} type="button" onClick={() => onSource(citation.chunk_id)}>{citation.label}</button>)}</div></details>}</div></article>;
}
