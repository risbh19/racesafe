import { useState } from 'react'
import type { Api } from '../api'
import { useCursorPage } from '../hooks/useCursorPage'
import type { Run } from '../pages/BoardPage'
import { Avatar } from './WorkspaceUI'

type RequestRow = { id: number; team_id: number; team_name: string; status: string }
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
const eventLabels: Record<string, string> = {
  'team.created': 'Team started', 'team.formed': 'Team formed', 'team.returned_to_draft': 'Team returned to draft',
  'team.updated': 'Team details updated', 'team.finalized': 'Team finalized', 'team.reopened': 'Team reopened',
  'team.deleted': 'Team deleted', 'invite.rotated': 'Invite code issued', 'leader.changed': 'Leadership transferred',
  'member.joined': 'Member joined', 'member.left': 'Member left', 'member.removed': 'Member removed',
  'request.created': 'Request sent', 'request.accepted': 'Request accepted',
  'request.declined': 'Request declined', 'request.cancelled': 'Request cancelled',
}

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

export function AuditHistory({ api, revision, teamId, archivedTeam }: ActivityProps & {
  teamId: number; archivedTeam?: ArchivedTeam
}) {
  const [open, setOpen] = useState(false)
  const { data, error, newer, older } = useCursorPage<{ events: AuditRow[]; next_before: number | null }>(
    api, '/teams/' + teamId + '/audit', revision, !archivedTeam || open,
  )

  const history = <>
      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading team activity…</p>}
      {data?.events.length === 0 && <p>No team activity yet.</p>}
      <ul className="item-list audit-list">
        {data?.events.map((entry) => (
          <li key={entry.id}>
            <div>
              <strong>{eventLabels[entry.action] || entry.action} by {entry.actor_name ?? 'user ' + entry.actor_id}</strong>
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
  </>
  return archivedTeam ? (
    <details className="panel archived-team" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary><span>{archivedTeam.name}</span>
        <time dateTime={archivedTeam.deleted_at}>{new Date(archivedTeam.deleted_at).toLocaleDateString()}</time></summary>
      {history}
    </details>
  ) : <section className="panel stack"><div className="section-heading"><h2>Team activity</h2></div>{history}</section>
}

export function MyRequests({ api, revision, busy, run, openTeam }: ActivityProps & {
  busy: boolean; run: Run; openTeam: (id: number) => void
}) {
  const { data, error, newer, older } = useCursorPage<{ requests: RequestRow[]; next_before: number | null }>(
    api, '/me/join-requests', revision, true,
  )
  return (
    <>
      <header className="page-heading"><h1>My requests</h1><p>Track the join requests you’ve sent.</p></header>
      <section className="panel stack" aria-label="Sent join requests">
      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading your join requests…</p>}
      {data?.requests.length === 0 && <p className="empty-state">No join requests on this page.</p>}
      <ul className="item-list">
        {data?.requests.map((request) => (
          <li key={request.id}>
            <div className="person-heading">
              <Avatar name={request.team_name} tone={request.team_id} />
              <button className="text-link" type="button" onClick={() => openTeam(request.team_id)}>{request.team_name}</button>
            </div>
            <div className="row">
            <span className={'badge request-state state-' + request.status}>{request.status}</span>
            {request.status === 'pending' && <button type="button" disabled={busy}
              aria-label={'Cancel request to ' + request.team_name}
              onClick={() => void run(async () => {
                await api('/join-requests/' + request.id, { method: 'DELETE' })
              }, 'Join request cancelled.')}>Cancel</button>}
            </div>
          </li>
        ))}
      </ul>
      <PageControls label="My join request pages" newer={newer} older={older} />
      </section>
    </>
  )
}

export function ArchivedTeams({ api, revision }: ActivityProps) {
  const { data, error, newer, older } = useCursorPage<{ teams: ArchivedTeam[]; next_before: number | null }>(
    api, '/me/archived-teams', revision, true,
  )
  return (
    <>
      <header className="page-heading"><h1>Archived teams</h1><p>Review activity from teams you closed by leaving as the last member.</p></header>
      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p className="panel" role="status">Loading archived teams…</p>}
      {data?.teams.length === 0 && <p className="panel empty-state">No archived teams on this page.</p>}
      {data?.teams.map((team) => (
        <AuditHistory key={team.id} api={api} revision={revision} teamId={team.id} archivedTeam={team} />
      ))}
      <PageControls label="Archived team pages" newer={newer} older={older} />
    </>
  )
}
