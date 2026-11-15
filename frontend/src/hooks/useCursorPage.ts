import { useEffect, useState } from 'react'
import type { Api } from '../api'

export function useCursorPage<T extends { next_before: number | null }>(
  api: Api, path: string, revision: number, enabled: boolean,
) {
  const [cursors, setCursors] = useState<(number | null)[]>([null])
  const [page, setPage] = useState<{ cursor: number | null; data: T }>()
  const [failure, setFailure] = useState<{ cursor: number | null; message: string }>()
  const cursor = cursors.at(-1) ?? null
  const data = page?.cursor === cursor ? page.data : undefined
  const next = data?.next_before

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    const { signal } = controller
    const query = new URLSearchParams({ limit: '20' })
    if (cursor !== null) query.set('before', String(cursor))

    void api<T>(path + '?' + query, { signal }).then((result) => {
      if (signal.aborted) return
      setPage({ cursor, data: result })
      setFailure(undefined)
    }).catch((error: Error) => {
      if (!signal.aborted) setFailure({ cursor, message: error.message })
    })
    return () => controller.abort()
  }, [api, cursor, enabled, path, revision])

  return {
    data,
    error: failure?.cursor === cursor ? failure.message : undefined,
    newer: cursors.length > 1 ? () => setCursors(cursors.slice(0, -1)) : undefined,
    older: next != null ? () => setCursors([...cursors, next]) : undefined,
  }
}
