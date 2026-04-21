import { useState } from 'react'

interface LoginViewProps {
  isSubmitting: boolean
  error: string
  onLogin: (email: string, password: string) => Promise<void> | void
}

export function LoginView({ isSubmitting, error, onLogin }: LoginViewProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  return (
    <main className="flex min-h-dvh items-center justify-center bg-(--oc-bg) p-4">
      <section className="w-full max-w-md rounded-2xl border border-(--oc-border) bg-(--oc-surface) p-6 shadow-sm">
        <h1 className="text-lg font-extrabold tracking-tight text-(--oc-accent-ink)">Prospect Console Sign In</h1>
        <p className="mt-1 text-sm text-(--oc-muted)">
          Sign in to access campaign-scoped pipeline operations.
        </p>
        <form
          className="mt-4 space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            void onLogin(email, password)
          }}
        >
          <label className="block space-y-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-(--oc-muted)">Email</span>
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
              autoComplete="email"
              className="w-full rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-sm outline-none focus:border-(--oc-accent)"
            />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-semibold uppercase tracking-wide text-(--oc-muted)">Password</span>
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              autoComplete="current-password"
              className="w-full rounded-xl border border-(--oc-border) bg-white px-3 py-2 text-sm outline-none focus:border-(--oc-accent)"
            />
          </label>
          {error ? (
            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>
          ) : null}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full rounded-xl bg-(--oc-accent) px-4 py-2 text-sm font-bold text-white transition hover:opacity-90 disabled:opacity-60"
          >
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </section>
    </main>
  )
}
