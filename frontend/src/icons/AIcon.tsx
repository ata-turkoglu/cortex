import {
  Activity,
  Bot,
  ChartNoAxesCombined,
  CircleHelp,
  Database,
  FileText,
  FolderOpen,
  GitBranch,
  HeartPulse,
  LayoutDashboard,
  MessageSquare,
  Network,
  PanelsTopLeft,
  Settings,
  Upload,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { ComponentProps } from "react";
export const icons = {
  activity: Activity,
  chat: MessageSquare,
  dashboard: LayoutDashboard,
  documents: FileText,
  graph: Network,
  health: HeartPulse,
  help: CircleHelp,
  jobs: Workflow,
  settings: Settings,
  system: PanelsTopLeft,
  upload: Upload,
  workspaces: FolderOpen,
  database: Database,
  provider: Bot,
  routes: GitBranch,
  metrics: ChartNoAxesCombined,
} satisfies Record<string, LucideIcon>;
export type IconName = keyof typeof icons;
export function AIcon({
  name,
  label,
  ...props
}: { name: IconName; label?: string } & Omit<
  ComponentProps<LucideIcon>,
  "ref"
>) {
  const Icon = icons[name];
  return (
    <Icon
      aria-hidden={label ? undefined : true}
      aria-label={label}
      {...props}
    />
  );
}
