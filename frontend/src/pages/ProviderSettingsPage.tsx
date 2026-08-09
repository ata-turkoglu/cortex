import { useEffect, useState } from "react";
import { apiClient } from "../api/client";
import { ABadge, ACard, AInfoPanel } from "../components/ui";

export function ProviderSettingsPage() {
  const [providers, setProviders] = useState<{ provider: string; configured: boolean }[]>([]);
  useEffect(() => { void apiClient.providerStatus().then((data) => setProviders(data.providers)).catch(() => setProviders([])); }, []);
  return <ACard title="Providers and models"><AInfoPanel>Only safe configuration state and model metadata are displayed. Stored secrets are never returned to the browser.</AInfoPanel><div className="mt-4 grid gap-3">{providers.map((provider) => <section key={provider.provider} className="flex items-center justify-between rounded border p-3"><div><strong>{provider.provider}</strong><p className="m-0 text-sm opacity-70">{provider.provider === "ollama" ? "Discovery only; Cortex never pulls or deletes models." : "Credentials are configured outside this screen."}</p></div><ABadge value={provider.configured ? "Configured" : "Not configured"} severity={provider.configured ? "success" : "secondary"} /></section>)}</div></ACard>;
}
