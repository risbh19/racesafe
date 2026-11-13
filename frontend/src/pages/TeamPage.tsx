import { useEffect, useState, type FormEvent } from 'react'
import { skillList, utcLabel, type Api, type Person, type Profile, type Team } from '../api'
import type { Run } from './BoardPage'

type Detail = Team & { members: Omit<Person, 'utc_offset_minutes'>[] }
type Pending = { id: number; user_id: number; display_name: string; message: string }
type Event = { id: number; actor_id: number; actor_name: string | null; action: string; created_at: string }
type Suggestion = Person & {
  score: number; skill_score: number; timezone_score: number; matched_skills: string[]
}

export function TeamPage({ api, profile, teamId, revision, busy, run, back }: {
  api: Api; profile: Profile; teamId: number; revision: number; busy: boolean; run: Run; back: () => void
}) {
  const [team, setTeam] = useState<Detail | null>(null)
  const [pending, setPending] = useState<Pending[]>([])
  const [events, setEvents] = useState<Event[]>([])
  const [ranking, setRanking] = useState<{ explanation: string; suggestions: Suggestion[] } | null>(null)
  const [invite, setInvite] = useState<{ code: string; expires_at: string } | null>(null)
  const [error, setError] = useState('')
  const path = '/teams/' + teamId

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const current = await api<Detail>(path)
        if (!active) return
        setTeam(current)
        setError('')
        const [requests, audit] = await Promise.all([
          current.leader_id === profile.id
            ? api<{ requests: Pending[] }>(path + '/join-requests').catch(() => ({ requests: [] }))
            : { requests: [] },
          current.members.some((member) => member.id === profile.id)
            ? api<{ events: Event[] }>(path + '/audit').catch(() => ({ events: [] }))
            : { events: [] },
        ])
        if (active) {
          setPending(requests.requests)
          setEvents(audit.events)
        }
      } catch (reason) {
        if (active) {
          setTeam(null)
          setError((reason as Error).message)
        }
      }
    }
    void load()
    return () => { active = false }
  }, [api, path, profile.id, revision])

  if (!team) return (
    <section className="panel">
      <button type="button" onClick={back}>Back to board</button>
      <p role={error ? 'alert' : 'status'}>{error || 'Loading team…'}</p>
    </section>
  )

  const leader = team.leader_id === profile.id
  const member = team.members.some((person) => person.id === profile.id)
  const waiting = profile.requests.some((request) => request.team_id === teamId && request.status === 'pending')

  function action(url: string, method: string, success: string, idempotent = false) {
    void run(async () => { await api(url, { method, idempotent }) }, success)
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
            <span className="seat-count">{team.locked ? 'Finalized' : 'Forming'}</span>
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
          {!profile.team && !team.locked && team.member_count < team.max_size && !waiting && (
            <form className="stack inset" onSubmit={requestJoin}>
              <label>Message to the team leader<textarea name="message" maxLength={300} rows={2} /></label>
              <button className="primary" disabled={busy}>Request to join</button>
            </form>
          )}
          {waiting && <p className="muted">Your request is pending.</p>}
        </section>

        {leader && (
          <section className="panel stack">
            <h2>Manage team</h2>
            <p className="muted">{team.min_size} members are required to finalize.</p>
            <div className="row">
              <button type="button" disabled={busy || (!team.locked && team.member_count < team.min_size)} onClick={() =>
                action(path + '/lock', team.locked ? 'DELETE' : 'POST', team.locked ? 'Team reopened.' : 'Team finalized.')
              }>{team.locked ? 'Reopen team' : 'Finalize team'}</button>
              <button type="button" disabled={busy} onClick={() => void run(async () => {
                setInvite(await api(path + '/invite-code', { method: 'POST' }))
              }, 'Invite code generated.')}>{invite ? 'Rotate invite code' : 'Generate invite code'}</button>
            </div>
            {invite && <div className="invite"><code>{invite.code}</code><span>Expires {new Date(invite.expires_at).toLocaleString()}</span></div>}
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
          {pending.length === 0 && <p className="muted">No pending requests.</p>}
          <ul className="item-list">
            {pending.map((request) => (
              <li key={request.id}>
                <div><strong>{request.display_name}</strong>{request.message && <p>{request.message}</p>}</div>
                <div className="row">
                  <button className="primary" type="button" disabled={busy} aria-label={'Accept ' + request.display_name}
                    onClick={() => action('/join-requests/' + request.id + '/accept', 'POST', 'Request accepted.', true)}>Accept</button>
                  <button type="button" disabled={busy} aria-label={'Decline ' + request.display_name}
                    onClick={() => action('/join-requests/' + request.id + '/decline', 'POST', 'Request declined.')}>Decline</button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {leader && (
        <section className="panel">
          <h2>Teammate suggestions</h2>
          <button type="button" disabled={busy} onClick={() => void run(async () => {
            setRanking(await api(path + '/suggestions'))
          })}>{ranking ? 'Refresh suggestions' : 'Rank available teammates'}</button>
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

      {member && (
        <details className="panel">
          <summary>Team activity</summary>
          <ul className="item-list">
            {events.map((entry) => <li key={entry.id}><span>{entry.action} by {entry.actor_name ?? 'user ' + entry.actor_id}</span><time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time></li>)}
          </ul>
        </details>
      )}
    </>
  )
}
