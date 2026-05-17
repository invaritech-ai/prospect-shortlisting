export function promptListCardClassNames(isEditing: boolean): string {
  return isEditing ? 'oc-prompt-card oc-prompt-card-active' : 'oc-prompt-card'
}
