import { startTransition, useEffect, useOptimistic, useState, type FormEvent } from 'react'
import { skillList, utcLabel, type Api, type Person, type Profile, type Team } from '../api'
import { AuditHistory } from '../components/Activity'
import { Avatar, Dialog, Skills } from '../components/WorkspaceUI'
import type { Run } from './BoardPage'

type Detail = Team & {
  members: Omit<Person, 'utc_offset_minutes'>[]
  invite_version: number | null
  my_pending_request_id: number | null
}
type Pending = { id: number; user_id: number; display_name: string; message: string }
type Inbox = { requests: Pending[]; next_after: number | null }
const NO_REQUESTS: Pending[] = []
type Suggestion = Person & {
  score: number; skill_score: number; timezone_score: number; matched_skills: string[]
}
type Ranking = { explanation: string; suggestions: Suggestion[] }
type Invite = { code: string; expires_at: string; version: number }
type Section = 'overview' | 'inbox' | 'manage' | 'activity'
type Confirmation = { kind: 'leave' } | { kind: 'remove'; person: Detail['members'][number] }

export function TeamPage({ api, profile, teamId, revision, busy, run, back }: {
  api: Api; profile: Profile; teamId: number; revision: number; busy: boolean; run: Run; back: () => void
}) {
  const [team, setTeam] = useState<Detail | null>(null)
  const [inbox, setInbox] = useState<{ cursor: number | null; data: Inbox } | null>(null)
  const [inboxError, setInboxError] = useState('')
  const [inboxCursors, setInboxCursors] = useState<(number | null)[]>([null])
  const [ranking, setRanking] = useState<Ranking | null>(null)
  const [rankingAttempt, setRankingAttempt] = useState(0)
  const [rankingError, setRankingError] = useState('')
  const [invite, setInvite] = useState<Invite | null>(null)
  const [copyFeedback, setCopyFeedback] = useState<{ version: number; message: string } | null>(null)
  const [section, setSection] = useState<Section>('overview')
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null)
  const [error, setError] = useState('')
  const path = '/teams/' + teamId
  const leader = team?.leader_id === profile.id
  const inboxCursor = inboxCursors.at(-1) ?? null
  const currentInbox = inbox?.cursor === inboxCursor ? inbox.data : null
  const [visibleRequests, hideRequest] = useOptimistic(
    currentInbox?.requests ?? NO_REQUESTS,
    (requests, id: number) => requests.filter((request) => request.id !== id),
  )
  const shownInvite = invite && invite.version === team?.invite_version ? invite : null

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    void api<Detail>(path, { signal }).then((current) => {
      if (signal.aborted) return
      setTeam(current)
      setError('')
    }).catch((reason: Error) => {
      if (signal.aborted) return
      setTeam(null)
      setError(reason.message)
    })
    return () => controller.abort()
  }, [api, path, revision])

  useEffect(() => {
    if (!leader) return
    const controller = new AbortController()
    const { signal } = controller
    const params = new URLSearchParams({ limit: '20' })
    if (inboxCursor !== null) params.set('after', String(inboxCursor))
    void api<Inbox>(path + '/join-requests?' + params, { signal }).then((data) => {
      if (signal.aborted) return
      setInbox({ cursor: inboxCursor, data })
      setInboxError('')
    }).catch((reason: Error) => {
      if (!signal.aborted) setInboxError(reason.message)
    })
    return () => controller.abort()
  }, [api, inboxCursor, leader, path, revision])

  useEffect(() => {
    if (!leader || rankingAttempt === 0) return
    const controller = new AbortController()
    const { signal } = controller
    void api<Ranking>(path + '/suggestions', { signal }).then((data) => {
      if (signal.aborted) return
      setRanking(data)
      setRankingError('')
    }).catch((reason: Error) => {
      if (!signal.aborted) setRankingError(reason.message)
    })
    return () => controller.abort()
  }, [api, leader, path, rankingAttempt, revision])

  useEffect(() => {
    if (!invite) return
    const remaining = Date.parse(invite.expires_at) - Date.now()
    const timeout = window.setTimeout(() => setInvite(null), Math.max(0, remaining))
    return () => window.clearTimeout(timeout)
  }, [invite])

  if (!team) return (
    <section className="panel">
      <button type="button" onClick={back}>Back to board</button>
      <p role={error ? 'alert' : 'status'}>{error || 'Loading team…'}</p>
    </section>
  )

  const member = team.members.some((person) => person.id === profile.id)
  const pendingRequest = team.my_pending_request_id
  const canApply = !profile.team && !member && !team.locked && team.member_count < team.max_size
  const restrictedSection = ((section === 'inbox' || section === 'manage') && !leader)
    || (section === 'activity' && !member)
  const activeSection = restrictedSection ? 'overview' : section
  const status = team.locked ? 'Finalized' : team.is_draft ? 'Draft' : 'Formed'

  function action(url: string, method: string, success: string, idempotent = false) {
    void run(async () => { await api(url, { method, idempotent }) }, success)
  }

  function acceptRequest(id: number) {
    startTransition(async () => {
      hideRequest(id)
      await run(async () => {
        await api('/join-requests/' + id + '/accept', { method: 'POST', idempotent: true })
        setInbox((current) => current && {
          ...current, data: {
            ...current.data, requests: current.data.requests.filter((request) => request.id !== id),
          },
        })
      }, 'Request accepted.')
    })
  }

  function requestJoin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = new FormData(event.currentTarget).get('message')
    void run(async () => {
      await api(path + '/join-requests', { method: 'POST', body: { message }, idempotent: true })
    }, 'Join request sent.')
  }

  function edit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    void run(async () => {
      await api(path, {
        method: 'PATCH',
        body: {
          name: form.get('name'), description: form.get('description'),
          needed_skills: skillList(String(form.get('skills') ?? '')), looking: form.has('looking'),
        },
      })
    }, 'Team updated.')
  }

  async function copyInvite(current: Invite) {
    try {
      await navigator.clipboard.writeText(current.code)
      setCopyFeedback({ version: current.version, message: 'Invite code copied.' })
    } catch {
      setCopyFeedback({ version: current.version, message: 'Select and copy the code above.' })
    }
  }

  function confirmMembershipChange() {
    if (!confirmation) return
    setConfirmation(null)
    if (confirmation.kind === 'leave') {
      void run(async () => {
        await api(path + '/members/me', { method: 'DELETE' })
        back()
      }, 'You left the team.')
    } else {
      action(path + '/members/' + confirmation.person.id, 'DELETE', 'Member removed.')
    }
  }

  return (
    <>
      <button className="back-button" type="button" onClick={back}><span aria-hidden="true">←</span> Back to board</button>
      <header className="panel team-header">
        <div className="team-title">
          <Avatar name={team.name} tone={team.id} />
          <div className="team-intro">
            <div className="title-line">
              <h1>{team.name}</h1>
              <span className={'badge ' + (team.is_draft ? 'badge-draft' : 'badge-open')}>{status}</span>
            </div>
            {team.description && <p>{team.description}</p>}
            <Skills items={team.needed_skills} />
          </div>
        </div>
        <div className="capacity team-capacity">
          <div className="capacity-label">
            <strong>{team.member_count}/{team.max_size} seats</strong>
            <span>{team.locked || team.member_count === team.max_size ? 'Closed' : (team.max_size - team.member_count) + ' open'}</span>
          </div>
          <progress aria-label="Seats filled" value={team.member_count} max={team.max_size} />
          {team.is_draft && <p>Forms at {team.min_size} members</p>}
        </div>
      </header>

      {member && (
        <div className="view-tools team-tools">
          <div className="view-switch" role="group" aria-label="Team sections">
            <button type="button" aria-pressed={activeSection === 'overview'} onClick={() => setSection('overview')}>Overview</button>
            {leader && <>
              <button type="button" aria-label="Join requests" aria-pressed={activeSection === 'inbox'} onClick={() => setSection('inbox')}>
                Join requests{inboxCursor === null && visibleRequests.length > 0 &&
                  <span className="tab-count" aria-hidden="true">{visibleRequests.length}{currentInbox?.next_after != null ? '+' : ''}</span>}
              </button>
              <button type="button" aria-pressed={activeSection === 'manage'} onClick={() => setSection('manage')}>Manage</button>
            </>}
            <button type="button" aria-pressed={activeSection === 'activity'} onClick={() => setSection('activity')}>Activity</button>
          </div>
        </div>
      )}

      {activeSection === 'overview' && <div className={'team-columns' + (leader || !member ? '' : ' single-column')}>
        <section className="panel roster">
          <div className="section-heading"><h2>Members</h2><span>{team.members.length} of {team.max_size}</span></div>
          <ul className="item-list">
            {team.members.map((person) => (
              <li key={person.id}>
                <div className="person-heading">
                  <Avatar name={person.display_name} tone={person.id} />
                  <div>
                    <div className="title-line"><strong>{person.display_name}</strong>
                      {person.id === team.leader_id && <span className="badge badge-open">Leader</span>}</div>
                    <Skills items={person.skills} />
                  </div>
                </div>
                {leader && person.id !== profile.id && <button className="quiet" type="button" disabled={busy}
                  aria-label={'Remove ' + person.display_name} onClick={() => setConfirmation({ kind: 'remove', person })}>Remove</button>}
              </li>
            ))}
          </ul>
          {member && <div className="section-footer">
            <button className="quiet danger-text" type="button" disabled={busy} onClick={() => setConfirmation({ kind: 'leave' })}>Leave team</button>
          </div>}
        </section>

        {canApply && pendingRequest === null && <section className="panel stack">
          <div className="section-heading"><h2>Join this team</h2></div>
          <p className="muted">Send the leader a short note about how you can contribute.</p>
          <form className="stack" onSubmit={requestJoin}>
            <label>Message to the team leader<textarea name="message" maxLength={300} rows={3} placeholder="Tell them what you'd bring to the team" /></label>
            <button className="primary" disabled={busy}>Request to join</button>
          </form>
        </section>}

        {pendingRequest !== null && <section className="panel stack">
          <div className="section-heading"><h2>Join request</h2><span className="badge badge-draft">Pending</span></div>
          <p>Your request is pending.</p>
          <button type="button" disabled={busy} onClick={() => {
            action('/join-requests/' + pendingRequest, 'DELETE', 'Join request cancelled.')
          }}>Cancel join request</button>
        </section>}

        {!member && !canApply && pendingRequest === null && <section className="panel stack">
          <h2>{team.locked || team.member_count >= team.max_size ? 'Recruitment closed' : 'Already on a team'}</h2>
          <p className="muted">{team.locked || team.member_count >= team.max_size
            ? 'This team isn’t taking join requests right now.'
            : 'You can be a member of one team at this hackathon.'}</p>
        </section>}

        {leader && <section className="panel stack matches">
          <div className="section-heading"><h2>Teammate suggestions</h2></div>
          {rankingAttempt === 0 && <p className="muted">Find available teammates by missing skills and time zone.</p>}
          {(rankingAttempt === 0 || rankingError) && <button type="button" disabled={busy} onClick={() => {
            setRankingError('')
            setRankingAttempt(rankingAttempt + 1)
          }}>{rankingError ? 'Retry suggestions' : 'Rank available teammates'}</button>}
          {rankingAttempt > 0 && !ranking && !rankingError && <p role="status">Ranking available teammates…</p>}
          {rankingError && <p role="alert">{rankingError}</p>}
          {ranking && <>
            <ul className="item-list">
              {ranking.suggestions.map((person) => (
                <li key={person.id}>
                  <div className="person-heading">
                    <Avatar name={person.display_name} tone={person.id} />
                    <div><strong>{person.display_name}</strong><p>{utcLabel(person.utc_offset_minutes)}</p>
                      <Skills items={person.matched_skills} /></div>
                  </div>
                  <span className="badge badge-open" title="Match score">{person.score}/100</span>
                </li>
              ))}
            </ul>
            {ranking.suggestions.length === 0 && <p>No available participants.</p>}
            <details className="score-explanation"><summary>How matching works</summary><p>{ranking.explanation}</p></details>
          </>}
        </section>}
      </div>}

      {activeSection === 'inbox' && (
        <section className="panel stack">
          <div className="section-heading"><h2>Join requests</h2></div>
          {inboxError && <p role="alert" className="error">{inboxError}</p>}
          {!currentInbox && !inboxError && <p role="status">Loading requests…</p>}
          {currentInbox && visibleRequests.length === 0 && <p className="empty-state">No pending requests on this page.</p>}
          <ul className="item-list inbox-list">
            {visibleRequests.map((request) => (
              <li key={request.id}>
                <div className="person-heading"><Avatar name={request.display_name} tone={request.user_id} />
                  <div><strong>{request.display_name}</strong>{request.message && <p>{request.message}</p>}</div>
                </div>
                <div className="row">
                  <button type="button" disabled={busy} aria-label={'Decline ' + request.display_name}
                    onClick={() => action('/join-requests/' + request.id + '/decline', 'POST', 'Request declined.')}>Decline</button>
                  <button className="primary" type="button" disabled={busy} aria-label={'Accept ' + request.display_name}
                    onClick={() => acceptRequest(request.id)}>Accept</button>
                </div>
              </li>
            ))}
          </ul>
          {(inboxCursors.length > 1 || currentInbox?.next_after != null) && (
            <nav className="row" aria-label="Join request pages">
              <button type="button" disabled={busy || inboxCursors.length === 1} onClick={() => {
                setInboxError('')
                setInboxCursors(inboxCursors.slice(0, -1))
              }}>Previous requests</button>
              <button type="button" disabled={busy || currentInbox?.next_after == null} onClick={() => {
                if (currentInbox?.next_after == null) return
                setInboxError('')
                setInboxCursors([...inboxCursors, currentInbox.next_after])
              }}>Next requests</button>
            </nav>
          )}
        </section>
      )}

      {activeSection === 'manage' && <div className="team-columns manage-columns">
        <section className="panel stack invite-panel">
          <div className="section-heading"><h2>Invite code</h2></div>
          <p className="muted">Share a code that expires in 24 hours. Generating another code revokes the previous one.</p>
          {shownInvite && <>
            <div className="invite">
              <code>{shownInvite.code}</code>
              <button type="button" onClick={() => void copyInvite(shownInvite)}>Copy code</button>
              <span>Expires {new Date(shownInvite.expires_at).toLocaleString()}</span>
            </div>
            {copyFeedback?.version === shownInvite.version && <p role="status">{copyFeedback.message}</p>}
          </>}
          <button type="button" disabled={busy} onClick={() => void run(async () => {
            setInvite(await api<Invite>(path + '/invite-code', { method: 'POST' }))
          }, 'Invite code generated.')}>{shownInvite ? 'Rotate invite code' : 'Generate invite code'}</button>
        </section>
        <section className="panel stack details-panel">
          <div className="section-heading"><h2>Team details</h2></div>
          <form className="stack" onSubmit={edit}>
            <label>Team name<input name="name" minLength={3} maxLength={40} defaultValue={team.name} required /></label>
            <label>Description<textarea name="description" maxLength={500} rows={4} defaultValue={team.description} /></label>
            <label>Needed skills<input name="skills" defaultValue={team.needed_skills.join(', ')} /></label>
            <label className="check"><input type="checkbox" name="looking" defaultChecked={team.looking} />Show on open team board</label>
            <button className="primary" disabled={busy}>Save team</button>
          </form>
        </section>
        <section className="panel stack status-panel">
          <div className="section-heading"><h2>Team status</h2></div>
          <p className="muted">{team.is_draft ? 'Reach ' + team.min_size + ' members to finalize this team.'
            : team.locked ? 'Finalized teams are closed to new members.' : 'Finalize when your roster is ready to close recruitment.'}</p>
          <button type="button" disabled={busy || (!team.locked && team.is_draft)} onClick={() =>
            action(path + '/lock', team.locked ? 'DELETE' : 'POST', team.locked ? 'Team reopened.' : 'Team finalized.')
          }>{team.locked ? 'Reopen team' : 'Finalize team'}</button>
        </section>
      </div>}

      {activeSection === 'activity' && <AuditHistory api={api} revision={revision} teamId={teamId} />}

      {confirmation && <Dialog title={confirmation.kind === 'leave' ? 'Leave team' : 'Remove member'} onDismiss={() => setConfirmation(null)}>
        <div className="stack">
          <p>{confirmation.kind === 'leave' ? 'Leave ' + team.name + '?'
            : 'Remove ' + confirmation.person.display_name + ' from ' + team.name + '?'}</p>
          <div className="dialog-actions">
            <button type="button" onClick={() => setConfirmation(null)}>Cancel</button>
            <button type="button" className="danger" onClick={confirmMembershipChange}>{confirmation.kind === 'leave' ? 'Leave team' : 'Remove member'}</button>
          </div>
        </div>
      </Dialog>}
    </>
  )
}
