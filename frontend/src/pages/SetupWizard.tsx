import { useState } from "react";
import { apiClient } from "../api/client";
import { AButton, ACard, AInfoPanel, AInput, ALabel, AProgress } from "../components/ui";

const steps = [
  "Welcome",
  "Data path",
  "Service health",
  "OpenAI",
  "Ollama",
  "Embeddings",
  "Budgets",
  "Validation",
];
export function SetupWizard() {
  const [step, setStep] = useState(0);
  const [path, setPath] = useState("D:\\Cortex\\data");
  const [openAiKey, setOpenAiKey] = useState("");
  const [notice, setNotice] = useState("");
  const complete = () =>
    void apiClient
      .completeSetup(path)
      .then(() => setNotice("Setup complete. Settings can be changed later."))
      .catch(() => setNotice("Setup could not be saved."));
  const validateOpenAi = () =>
    void apiClient
      .validateProvider("openai", openAiKey)
      .then((result) => setNotice(`OpenAI: ${result.status}`))
      .catch(() => setNotice("OpenAI validation failed."));
  const testOllama = () =>
    void apiClient
      .validateProvider("ollama")
      .then((result) => setNotice(`Ollama: ${result.status}`))
      .catch(() => setNotice("Ollama is unavailable."));
  return (
    <ACard title="First-run setup">
      <AProgress value={((step + 1) / steps.length) * 100} showValue={false} />
      <p className="mt-3 text-sm">
        Step {step + 1} of {steps.length}: <strong>{steps[step]}</strong>
      </p>
      {step === 1 ? (
        <ALabel className="grid gap-1">
          Windows data path
          <AInput
            value={path}
            onChange={(event) => setPath(event.target.value)}
          />
        </ALabel>
      ) : step === 3 ? (
        <div className="grid gap-2">
          <AInfoPanel>
            OpenAI is the production default. The key is stored in the OS
            credential store and never returned.
          </AInfoPanel>
          <AInput
            type="password"
            value={openAiKey}
            onChange={(event) => setOpenAiKey(event.target.value)}
            placeholder="OpenAI API key"
          />
          <AButton label="Validate OpenAI" onClick={validateOpenAi} />
        </div>
      ) : step === 4 ? (
        <div className="grid gap-2">
          <AInfoPanel>
            Ollama is optional. Cortex will not download models. Missing
            embedding model command:{" "}
            <code>ollama pull qwen3-embedding:0.6b</code>
          </AInfoPanel>
          <AButton label="Test Ollama availability" onClick={testOllama} />
        </div>
      ) : step === 5 ? (
        <AInfoPanel>
          Default embedding: Ollama qwen3-embedding:0.6b. Changing it later
          requires full dense reindexing.
        </AInfoPanel>
      ) : (
        <AInfoPanel>
          Global settings, health checks, budgets, and model assignments can be
          revised after setup.
        </AInfoPanel>
      )}
      <div className="mt-4 flex items-center gap-2">
        <AButton
          label="Back"
          disabled={step === 0}
          onClick={() => setStep((value) => value - 1)}
        />
        <AButton
          label={step === steps.length - 1 ? "Finish" : "Continue"}
          onClick={() =>
            step === steps.length - 1
              ? complete()
              : setStep((value) => Math.min(value + 1, steps.length - 1))
          }
        />
        <span className="text-sm">{notice}</span>
      </div>
    </ACard>
  );
}
