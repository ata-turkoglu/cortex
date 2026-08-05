import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/api/generated"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": "off",
      "no-restricted-imports": [
        "error",
        {
          paths: [
            { name: "primereact/button", message: "Use Cortex UI adapters." },
            { name: "primereact/dialog", message: "Use Cortex UI adapters." },
            {
              name: "primereact/datatable",
              message: "Use Cortex UI adapters.",
            },
            {
              name: "lucide-react",
              message: "Use AIcon and the icon registry.",
            },
            { name: "@xyflow/react", message: "Use AFlowCanvas." },
          ],
        },
      ],
    },
  },
  {
    files: ["src/ui/**", "src/components/ui/**", "src/icons/**", "src/flow/**"],
    rules: { "no-restricted-imports": "off" },
  },
);
