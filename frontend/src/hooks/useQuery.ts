/** Tiny data-fetching hook. Deliberately not a server-state library —
 *  specs/00_conventions.md §7 and ADR 0012: two useCases do not need TanStack.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface QueryState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  refetch: () => void
}

export function useQuery<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options: { skip?: boolean } = {},
): QueryState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(!options.skip)
  const [reloadKey, bumpReload] = useState(0)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  useEffect(() => {
    if (options.skip) {
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    fetcher()
      .then((result) => {
        if (cancelled || !alive.current) return
        setData(result)
        setError(null)
      })
      .catch((err: unknown) => {
        if (cancelled || !alive.current) return
        setError(err instanceof ApiError ? err : new ApiError(0, 'error', String(err)))
      })
      .finally(() => {
        if (!cancelled && alive.current) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reloadKey, options.skip])

  const refetch = useCallback(() => bumpReload((n) => n + 1), [])

  return { data, error, loading, refetch }
}