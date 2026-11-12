import { useEffect, useEffectEvent, useState } from 'react'

export function useEvents(token: string, hackathonId: number | undefined, refresh: () => void) {
  const [connected, setConnected] = useState(false)
  const onChange = useEffectEvent(refresh)

  useEffect(() => {
    if (!token || !hackathonId) return
    const abort = new AbortController()
    let retry: number | undefined
    let debounce: number | undefined

    function notify() {
      window.clearTimeout(debounce)
      debounce = window.setTimeout(() => onChange(), 150)
    }

    async function connect() {
      try {
        const response = await fetch('/api/hackathons/' + hackathonId + '/events', {
          headers: { Authorization: 'Bearer ' + token },
          signal: abort.signal,
        })
        if (response.status === 401) {
          onChange()
          return
        }
        if (!response.ok || !response.body) throw new Error('Live updates unavailable')

        setConnected(true)
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
        let buffer = ''
        try {
          for (;;) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += value
            let boundary = buffer.indexOf('\n\n')
            while (boundary >= 0) {
              if (buffer.slice(0, boundary).includes('event: changed')) notify()
              buffer = buffer.slice(boundary + 2)
              boundary = buffer.indexOf('\n\n')
            }
          }
        } finally {
          reader.releaseLock()
        }
      } catch {
        // A snapshot during reconnect also covers missed notifications.
      } finally {
        if (!abort.signal.aborted) {
          setConnected(false)
          notify()
          retry = window.setTimeout(() => void connect(), 3000)
        }
      }
    }

    void connect()
    return () => {
      abort.abort()
      window.clearTimeout(retry)
      window.clearTimeout(debounce)
    }
  }, [token, hackathonId])

  return Boolean(token && hackathonId && connected)
}
