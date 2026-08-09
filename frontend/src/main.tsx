import "./styles.css";
import "primereact/resources/themes/saga-blue/theme.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./app/App";
import { AppearanceProvider } from "./app/appearance";
import { AConfirmationProvider, AUiProvider } from "./components/ui";
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AUiProvider>
      <QueryClientProvider client={queryClient}>
        <AConfirmationProvider>
          <AppearanceProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </AppearanceProvider>
        </AConfirmationProvider>
      </QueryClientProvider>
    </AUiProvider>
  </StrictMode>,
);
