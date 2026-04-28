export function promptListCardClassNames(isEditing: boolean): string {
  return `rounded-2xl border p-3 transition ${
    isEditing
      ? 'border-[var(--oc-accent)] bg-[var(--oc-accent-soft)]/40'
      : 'border-[var(--oc-border)] bg-[var(--oc-surface)]'
  }`
}
