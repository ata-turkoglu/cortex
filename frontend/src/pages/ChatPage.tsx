import { useEffect, useState } from "react";

import {
  apiClient,
  type ChatMessage,
  type Conversation,
  type QueryDebug,
} from "../api/client";
import {
  AButton,
  ACard,
  ADialog,
  AInfo,
  AInput,
  ASelect,
  ATextarea,
} from "../ui/primitives";

type Mode = "automatic" | "document_search" | "deep_analysis";
type Source = {
  content: string;
  document_title: string;
  version_number: number;
};

export function ChatPage() {
  const [workspaceId, setWorkspaceId] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [active, setActive] = useState<Conversation>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [content, setContent] = useState("");
  const [mode, setMode] = useState<Mode>("automatic");
  const [debug, setDebug] = useState<QueryDebug>();
  const [source, setSource] = useState<Source>();
  const [error, setError] = useState("");

  useEffect(() => {
    if (!workspaceId) return;
    apiClient
      .listConversations(workspaceId)
      .then(setConversations)
      .catch(() => setError("Workspace could not be loaded."));
  }, [workspaceId]);

  useEffect(() => {
    if (!workspaceId || !active) return;
    apiClient
      .listMessages(workspaceId, active.id)
      .then(setMessages)
      .catch(() => setError("Messages could not be loaded."));
  }, [workspaceId, active]);

  async function createConversation() {
    try {
      const conversation = await apiClient.createConversation(workspaceId);
      setConversations((items) => [conversation, ...items]);
      setActive(conversation);
    } catch {
      setError("Conversation could not be created.");
    }
  }

  async function submit() {
    if (!active || !content.trim()) return;
    const question = content;
    try {
      const answer = await apiClient.ask(
        workspaceId,
        active.id,
        question,
        mode,
      );
      setMessages((items) => [
        ...items,
        {
          id: "pending",
          role: "user",
          content: question,
          status: "completed",
          citations: [],
          metadata: {},
          created_at: new Date().toISOString(),
        },
        answer,
      ]);
      setContent("");
      const queryRunId = String(answer.metadata.query_run_id ?? "");
      if (queryRunId)
        setDebug(await apiClient.queryDebug(workspaceId, queryRunId));
    } catch {
      setError("The query could not be completed.");
    }
  }

  async function openSource(chunkId: string) {
    try {
      setSource(await apiClient.sourceDetails(workspaceId, chunkId));
    } catch {
      setError("Source details could not be loaded.");
    }
  }

  return (
    <>
      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <ACard title="Workspace and conversations">
          <label>
            Workspace ID{" "}
            <AInput
              value={workspaceId}
              onChange={(event) => setWorkspaceId(event.target.value)}
            />
          </label>
          <div className="mt-3">
            <AButton
              label="New conversation"
              disabled={!workspaceId}
              onClick={createConversation}
            />
          </div>
          <div className="mt-3 grid gap-2">
            {conversations.map((item) => (
              <AButton
                key={item.id}
                label={item.title}
                text
                onClick={() => setActive(item)}
              />
            ))}
          </div>
        </ACard>
        <ACard title={active?.title ?? "Chat"}>
          {error && <AInfo title="Error">{error}</AInfo>}
          {!active && (
            <AInfo>
              Create a conversation for the selected workspace to start.
            </AInfo>
          )}
          <div className="my-4 grid gap-3">
            {messages.map((message) => (
              <article key={message.id} className="rounded border p-3">
                <strong>{message.role === "user" ? "You" : "Cortex"}</strong>
                <p className="whitespace-pre-wrap">{message.content}</p>
                {message.metadata.inference === true && (
                  <small className="text-amber-700">Inference from cited evidence</small>
                )}
                {message.citations.map((citation) => (
                  <AButton
                    key={citation.chunk_id}
                    label={`Source: ${citation.label}`}
                    text
                    onClick={() => openSource(citation.chunk_id)}
                  />
                ))}
              </article>
            ))}
          </div>
          {active && (
            <>
              <ASelect
                value={mode}
                options={[
                  { label: "Automatic", value: "automatic" },
                  { label: "Document Search", value: "document_search" },
                  { label: "Deep Analysis", value: "deep_analysis" },
                ]}
                onChange={(event) => setMode(event.value as Mode)}
              />
              <ATextarea
                className="mt-3 w-full"
                value={content}
                onChange={(event) => setContent(event.target.value)}
              />
              <AButton className="mt-3" label="Send" onClick={submit} />
            </>
          )}
          {debug && (
            <AInfo title="Query details">
              Route: {debug.routes.join(" + ")} · {debug.reason} ·{" "}
              {debug.latency_ms} ms · cost ${debug.estimated_cost_usd}
            </AInfo>
          )}
        </ACard>
      </div>
      <ADialog
        header={source?.document_title ?? "Source"}
        visible={Boolean(source)}
        onHide={() => setSource(undefined)}
      >
        <p>Version {source?.version_number}</p>
        <p className="whitespace-pre-wrap">{source?.content}</p>
      </ADialog>
    </>
  );
}
