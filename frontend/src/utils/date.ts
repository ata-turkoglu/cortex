const CORTEX_TIME_ZONE = "Europe/Istanbul";
const TIME_ZONE_SUFFIX = /(?:Z|[+-]\d{2}:?\d{2})$/i;

const withCortexTimeZone = (options: Intl.DateTimeFormatOptions = {}) => ({
  timeZone: CORTEX_TIME_ZONE,
  ...options,
});

export function formatCortexDate(value: string | Date, options?: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("tr-TR", withCortexTimeZone(options)).format(
    new Date(normalizeCortexTimestamp(value)),
  );
}

function normalizeCortexTimestamp(value: string | Date) {
  if (typeof value !== "string" || !value.includes("T") || TIME_ZONE_SUFFIX.test(value)) {
    return value;
  }
  // SQLite serializes Cortex's UTC timestamps without an offset.
  return `${value}Z`;
}

export function formatCortexDateTime(value: string | Date) {
  return formatCortexDate(value, { dateStyle: "short", timeStyle: "medium" });
}

export function formatCortexTime(value: string | Date, includeSeconds = false) {
  return formatCortexDate(value, {
    hour: "2-digit",
    minute: "2-digit",
    ...(includeSeconds ? { second: "2-digit" } : {}),
  });
}
