import { AButton, ABadge, ACard, AInfo } from "../ui/primitives";
const providers = [
  {
    name: "OpenAI",
    status: "Not configured",
    detail: "Required for default production models.",
  },
  {
    name: "Anthropic",
    status: "Optional",
    detail: "Available after a secret is configured.",
  },
  {
    name: "Ollama",
    status: "Optional",
    detail: "Discovery only; Cortex never pulls or deletes models.",
  },
];
export function ProviderSettingsPage() {
  return (
    <ACard title="Providers and models">
      <AInfo>
        Only configuration state and safe metadata are displayed. Stored secrets
        are never returned to the browser.
      </AInfo>
      <div className="mt-4 grid gap-3">
        {providers.map((provider) => (
          <section
            key={provider.name}
            className="flex items-center justify-between rounded border p-3"
          >
            <div>
              <strong>{provider.name}</strong>
              <p className="m-0 text-sm opacity-70">{provider.detail}</p>
            </div>
            <div className="flex items-center gap-2">
              <ABadge value={provider.status} severity="secondary" />
              <AButton label="Configure" outlined />
            </div>
          </section>
        ))}
      </div>
    </ACard>
  );
}
