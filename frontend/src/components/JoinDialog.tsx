import { useRef, useState, type FormEvent } from 'react'
import type { Api } from '../api'
import { Dialog } from './WorkspaceUI'

export function JoinDialog({ api, joined, close }: { api: Api; joined: (id: number) => void; close: () => void }) {
  const submitting = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function dismiss() {
    if (!submitting.current) close()
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
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
      submitting.current = false
      setBusy(false)
    }
  }

  return (
    <Dialog title="Join with an invite" onDismiss={dismiss}>
      <form className="stack" onSubmit={submit}>
        <p className="muted">Enter the 12-character code shared by the team leader.</p>
        <label>Invite code<input name="code" minLength={12} maxLength={12} autoComplete="off" spellCheck={false} required /></label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="dialog-actions">
          <button type="button" onClick={dismiss} disabled={busy}>Cancel</button>
          <button className="primary" disabled={busy}>{busy ? 'Joining…' : 'Join team'}</button>
        </div>
      </form>
    </Dialog>
  )
}
