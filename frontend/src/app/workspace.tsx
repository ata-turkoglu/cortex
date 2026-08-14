import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiClient, type Workspace } from "../api/client";

export const WORKSPACE_STORAGE_KEY = "cortex-selected-workspace";

type WorkspaceContextValue = {
  workspaces: Workspace[];
  workspaceId: string;
  setWorkspaceId: (id: string) => void;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function readStoredWorkspaceId() {
  try {
    return window.localStorage.getItem(WORKSPACE_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceIdState] = useState(readStoredWorkspaceId);

  useEffect(() => {
    void apiClient.listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]));
  }, []);

  useEffect(() => {
    if (!workspaces.length) return;
    const nextId = workspaces.some((workspace) => workspace.id === workspaceId)
      ? workspaceId
      : workspaces[0].id;
    if (nextId !== workspaceId) setWorkspaceIdState(nextId);
    try {
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, nextId);
    } catch { /* Local persistence is optional. */ }
  }, [workspaceId, workspaces]);

  const setWorkspaceId = useCallback((id: string) => {
    if (!workspaces.some((workspace) => workspace.id === id)) return;
    setWorkspaceIdState(id);
    try {
      window.localStorage.setItem(WORKSPACE_STORAGE_KEY, id);
    } catch { /* Local persistence is optional. */ }
  }, [workspaces]);

  const value = useMemo(() => ({ workspaces, workspaceId, setWorkspaceId }), [setWorkspaceId, workspaces, workspaceId]);
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return value;
}
