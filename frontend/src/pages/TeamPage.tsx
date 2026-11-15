import { startTransition, useEffect, useOptimistic, useState, type FormEvent } from 'react'
import { skillList, utcLabel, type Api, type Person, type Profile, type Team } from '../api'
import { AuditHistory } from '../components/Activity'
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

  return (
    <>
      <div className="row"><button className="back-button" type="button" onClick={back}><span aria-hidden="true">←</span> Back to board</button></div>
      <header className="board-hero team-hero">
        <div><h1>{team.name}</h1>{team.description && <p>{team.description}</p>}</div>
        <div className="capacity">
          <div className="capacity-label">
            <span>{team.member_count}/{team.max_size} seats</span>
            <span className="seat-count">{team.locked ? 'Finalized' : team.is_draft ? 'Draft' : 'Formed'}</span>
          </div>
          <progress aria-label="Seats filled" value={team.member_count} max={team.max_size} />
        </div>
      </header>

      <div className="two-columns">
        <section className="panel">
          <h2>Members</h2>
          <ul className="item-list">
            {team.members.map((person) => (
              <li key={person.id}>
                <div className="person-heading">
                  <span className="avatar" aria-hidden="true">{person.display_name.slice(0, 1).toUpperCase()}</span>
                  <div>
                    <strong>{person.display_name}</strong>
                    {person.id === team.leader_id && <span className="leader-label">Leader</span>}
                    {person.skills.length > 0 && <div className="tags">{person.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}
                  </div>
                </div>
                {leader && person.id !== profile.id && (
                  <button type="button" disabled={busy} aria-label={'Remove ' + person.display_name} onClick={() => {
                    if (window.confirm('Remove ' + person.display_name + ' from the team?')) {
                      action(path + '/members/' + person.id, 'DELETE', 'Member removed.')
                    }
                  }}>Remove</button>
                )}
              </li>
            ))}
          </ul>
          {member && <button type="button" disabled={busy} onClick={() => {
            if (window.confirm('Leave ' + team.name + '?')) {
              void run(async () => { await api(path + '/members/me', { method: 'DELETE' }); back() }, 'You left the team.')
            }
          }}>Leave team</button>}
          {!profile.team && !team.locked && team.member_count < team.max_size && pendingRequest === null && (
            <form className="stack inset" onSubmit={requestJoin}>
              <label>Message to the team leader<textarea name="message" maxLength={300} rows={2} /></label>
              <button className="primary" disabled={busy}>Request to join</button>
            </form>
          )}
          {pendingRequest !== null && <div className="row">
            <p className="muted">Your request is pending.</p>
            <button type="button" disabled={busy} onClick={() => {
              action('/join-requests/' + pendingRequest, 'DELETE', 'Join request cancelled.')
            }}>Cancel join request</button>
          </div>}
        </section>

        {leader && (
          <section className="panel stack">
            <h2>Manage team</h2>
            {team.is_draft && <p className="muted">This draft becomes a team at {team.min_size} members.</p>}
            <div className="row">
              <button type="button" disabled={busy || (!team.locked && team.member_count < team.min_size)} onClick={() =>
                action(path + '/lock', team.locked ? 'DELETE' : 'POST', team.locked ? 'Team reopened.' : 'Team finalized.')
              }>{team.locked ? 'Reopen team' : 'Finalize team'}</button>
              <button type="button" disabled={busy} onClick={() => void run(async () => {
                setInvite(await api<Invite>(path + '/invite-code', { method: 'POST' }))
              }, 'Invite code generated.')}>{shownInvite ? 'Rotate invite code' : 'Generate invite code'}</button>
            </div>
            {shownInvite && <div className="invite"><code>{shownInvite.code}</code><span>Expires {new Date(shownInvite.expires_at).toLocaleString()}</span></div>}
            <details>
              <summary>Edit team details</summary>
              <form className="stack inset" onSubmit={edit}>
                <label>Name<input name="name" minLength={3} maxLength={40} defaultValue={team.name} required /></label>
                <label>Description<textarea name="description" maxLength={500} defaultValue={team.description} /></label>
                <label>Needed skills<input name="skills" defaultValue={team.needed_skills.join(', ')} /></label>
                <label className="check"><input type="checkbox" name="looking" defaultChecked={team.looking} />Show on open team board</label>
                <button disabled={busy}>Save team</button>
              </form>
            </details>
          </section>
        )}
      </div>

      {leader && (
        <section className="panel">
          <h2>Join requests</h2>
          {inboxError && <p role="alert" className="error">{inboxError}</p>}
          {!currentInbox && !inboxError && <p role="status">Loading requests.</p>}
          {currentInbox && visibleRequests.length === 0 && <p className="muted">No pending requests on this page.</p>}
          <ul className="item-list">
            {visibleRequests.map((request) => (
              <li key={request.id}>
                <div><strong>{request.display_name}</strong>{request.message && <p>{request.message}</p>}</div>
                <div className="row">
                  <button className="primary" type="button" disabled={busy} aria-label={'Accept ' + request.display_name}
                    onClick={() => acceptRequest(request.id)}>Accept</button>
                  <button type="button" disabled={busy} aria-label={'Decline ' + request.display_name}
                    onClick={() => action('/join-requests/' + request.id + '/decline', 'POST', 'Request declined.')}>Decline</button>
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

      {leader && (
        <section className="panel">
          <h2>Teammate suggestions</h2>
          {(rankingAttempt === 0 || rankingError) && <button type="button" disabled={busy} onClick={() => {
            setRankingError('')
            setRankingAttempt(rankingAttempt + 1)
          }}>{rankingError ? 'Retry suggestions' : 'Rank available teammates'}</button>}
          {rankingAttempt > 0 && !ranking && !rankingError && <p role="status">Ranking available teammates…</p>}
          {rankingError && <p role="alert">{rankingError}</p>}
          {ranking && <><p className="muted">{ranking.explanation}</p>
            <ul className="item-list">
              {ranking.suggestions.map((person) => (
                <li key={person.id}>
                  <div><strong>{person.display_name}</strong><p>{utcLabel(person.utc_offset_minutes)} · {person.matched_skills.join(', ') || 'No matched skills'}</p></div>
                  <span className="seat-count">{person.score}/100</span>
                </li>
              ))}
            </ul>
            {ranking.suggestions.length === 0 && <p>No available participants.</p>}
          </>}
        </section>
      )}

      {member && <AuditHistory api={api} revision={revision} teamId={teamId} />}
    </>
  )
}
