import { ApiError } from './api'

export function parseApiError(err: unknown): string {
  if (err instanceof ApiError) {
    if (typeof err.detail === 'string') return err.detail
    if (typeof err.detail === 'object' && err.detail !== null && 'message' in err.detail) {
      return (err.detail as { message: string }).message
    }
    if (Array.isArray(err.detail)) return JSON.stringify(err.detail)
    return JSON.stringify(err.detail)
  }
  if (err instanceof Error) return err.message
  return 'Unknown error'
}
