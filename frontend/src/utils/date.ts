const CORTEX_TIME_ZONE = "Europe/Istanbul";

const withCortexTimeZone = (options: Intl.DateTimeFormatOptions = {}) => ({
  timeZone: CORTEX_TIME_ZONE,
  ...options,
});

export function formatCortexDate(value: string | Date, options?: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("tr-TR", withCortexTimeZone(options)).format(new Date(value));
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
