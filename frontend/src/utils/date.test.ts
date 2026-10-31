import { describe, expect, it } from "vitest";

import { formatCortexTime } from "./date";

describe("formatCortexTime", () => {
  it("treats SQLite's offset-free Cortex timestamps as UTC", () => {
    expect(formatCortexTime("2026-08-24T08:45:00")).toBe("11:45");
  });

  it("preserves timestamps that already declare UTC", () => {
    expect(formatCortexTime("2026-08-24T08:45:00Z")).toBe("11:45");
  });
});
