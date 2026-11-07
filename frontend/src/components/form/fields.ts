export const fieldClass = "h-11 w-full rounded-lg border border-field-border px-3 text-[15px] text-ink";

/** Fields filled from the typed sentence stay tinted until the driver changes them. */
export const fieldBg = (filled: boolean) => (filled ? "bg-accent/10" : "bg-surface");
