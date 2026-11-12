import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { Api } from '../api'

export function JoinDialog({ api, joined, close }: { api: Api; joined: (id: number) => void; close: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const node = dialog.current
    node?.showModal()
    return () => node?.close()
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const code = String(new FormData(event.currentTarget).get('code')).trim().toUpperCase()
    setBusy(true)
    setError('')
    try {
      const result = await api<{ team_id: number }>('/invites/redeem', {
        method: 'POST', body: { code }, idempotent: true,
      })
      joined(result.team_id)
      close()
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <dialog ref={dialog} onCancel={(event) => { event.preventDefault(); close() }} aria-labelledby="join-title">
      <form className="stack" onSubmit={submit}>
        <h2 id="join-title">Join with an invite</h2>
        <label>Invite code<input name="code" minLength={12} maxLength={12} autoComplete="off" spellCheck={false} required /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row">
          <button className="primary" disabled={busy}>{busy ? 'Joining…' : 'Join team'}</button>
          <button type="button" onClick={close}>Cancel</button>
        </div>
      </form>
    </dialog>
  )
}
