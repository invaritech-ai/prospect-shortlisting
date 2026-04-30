interface Props {
  message?: string
}

export function GlobalLoadingOverlay({ message }: Props) {
  return (
    <div
      className="fixed inset-0 z-[9999] flex flex-col items-center justify-center gap-3 bg-black/40 backdrop-blur-sm"
      aria-busy="true"
      aria-label={message ?? 'Loading'}
    >
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-white/30 border-t-white" />
      {message ? (
        <p className="text-sm font-semibold text-white drop-shadow">{message}</p>
      ) : null}
    </div>
  )
}
