import { useState } from 'react'
import type { Api } from '../api'
import { useCursorPage } from '../hooks/useCursorPage'
import type { Run } from '../pages/BoardPage'

type RequestRow = { id: number; team_name: string; status: string }
type ArchivedTeam = { id: number; name: string; deleted_at: string }
type AuditValue = string | boolean | string[]
type AuditRow = {
  id: number; actor_id: number; actor_name: string | null; action: string; created_at: string
  details: {
    changes?: Record<string, { before: AuditValue; after: AuditValue }>
    user_id?: number; request_id?: number; leader_id?: number
  }
}
type PageAction = (() => void) | undefined
type ActivityProps = { api: Api; revision: number }

function PageControls({ label, newer, older }: { label: string; newer: PageAction; older: PageAction }) {
  if (!newer && !older) return null
  return (
    <nav className="row" aria-label={label}>
      <button type="button" disabled={!newer} onClick={newer}>Newer</button>
      <button type="button" disabled={!older} onClick={older}>Older</button>
    </nav>
  )
}

function valueText(value: AuditValue) {
  if (Array.isArray(value)) return value.join(', ') || 'None'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  return value || 'Empty'
}

export function AuditHistory({ api, revision, teamId, title = 'Team activity' }: ActivityProps & {
  teamId: number; title?: string
}) {
  const [open, setOpen] = useState(false)
  const { data, error, newer, older } = useCursorPage<{ events: AuditRow[]; next_before: number | null }>(
    api, '/teams/' + teamId + '/audit', revision, open,
  )

  return (
    <details className="panel" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>{title}</summary>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading team activity…</p>}
      {data?.events.length === 0 && <p>No team activity yet.</p>}
      <ul className="item-list">
        {data?.events.map((entry) => (
          <li key={entry.id}>
            <div>
              <span>{entry.action} by {entry.actor_name ?? 'user ' + entry.actor_id}</span>
              {entry.details.user_id != null && <p>Affected member #{entry.details.user_id}</p>}
              {entry.details.request_id != null && <p>Join request #{entry.details.request_id}</p>}
              {entry.details.leader_id != null && <p>New leader #{entry.details.leader_id}</p>}
              {entry.details.changes && <ul>
                {Object.entries(entry.details.changes).map(([field, change]) => (
                  <li key={field}>{field.replaceAll('_', ' ')} changed from {valueText(change.before)} to {valueText(change.after)}</li>
                ))}
              </ul>}
            </div>
            <time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time>
          </li>
        ))}
      </ul>
      <PageControls label="Team activity pages" newer={newer} older={older} />
    </details>
  )
}

export function MyRequests({ api, revision, busy, run }: ActivityProps & { busy: boolean; run: Run }) {
  const [open, setOpen] = useState(false)
  const { data, error, newer, older } = useCursorPage<{ requests: RequestRow[]; next_before: number | null }>(
    api, '/me/join-requests', revision, open,
  )
  return (
    <details className="panel" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>My join requests</summary>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading your join requests…</p>}
      {data?.requests.length === 0 && <p>No join requests on this page.</p>}
      <ul className="item-list">
        {data?.requests.map((request) => (
          <li key={request.id}>
            <span><strong>{request.team_name}</strong> · {request.status}</span>
            {request.status === 'pending' && <button type="button" disabled={busy}
              aria-label={'Cancel request to ' + request.team_name}
              onClick={() => void run(async () => {
                await api('/join-requests/' + request.id, { method: 'DELETE' })
              }, 'Join request cancelled.')}>Cancel</button>}
          </li>
        ))}
      </ul>
      <PageControls label="My join request pages" newer={newer} older={older} />
    </details>
  )
}

export function ArchivedTeams({ api, revision }: ActivityProps) {
  const [open, setOpen] = useState(false)
  const { data, error, newer, older } = useCursorPage<{ teams: ArchivedTeam[]; next_before: number | null }>(
    api, '/me/archived-teams', revision, open,
  )
  return (
    <details className="panel" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>Archived teams</summary>
      {error && <p role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading archived teams…</p>}
      {data?.teams.length === 0 && <p>No archived teams on this page.</p>}
      {data?.teams.map((team) => (
        <AuditHistory key={team.id} api={api} revision={revision} teamId={team.id} title={team.name} />
      ))}
      <PageControls label="Archived team pages" newer={newer} older={older} />
    </details>
  )
}
