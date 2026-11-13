import { useEffect, useState, type FormEvent } from 'react'
import { skillList, utcLabel, type Api, type Person, type Profile, type Team } from '../api'

type Board = { teams: Team[]; next_before: number | null }
type People = { people: Person[]; next_after: number | null }

export type Run = (action: () => Promise<void>, success?: string) => Promise<void>

export function BoardPage({ api, profile, revision, busy, run, openTeam }: {
  api: Api; profile: Profile; revision: number; busy: boolean; run: Run; openTeam: (id: number) => void
}) {
  const [tab, setTab] = useState<'teams' | 'people'>('teams')
  const [filter, setFilter] = useState('')
  const [board, setBoard] = useState<Board | null>(null)
  const [people, setPeople] = useState<People | null>(null)
  const [error, setError] = useState('')
  const base = '/hackathons/' + profile.hackathon_id
  const query = new URLSearchParams({ limit: '20', ...(filter ? { skill: filter } : {}) }).toString()

  useEffect(() => {
    let active = true
    async function load() {
      try {
        if (tab === 'teams') {
          const result = await api<Board>(base + '/board?' + query)
          if (active) setBoard(result)
        } else {
          const result = await api<People>(base + '/people?' + query)
          if (active) setPeople(result)
        }
        if (active) setError('')
      } catch (reason) {
        if (active) setError((reason as Error).message)
      }
    }
    void load()
    return () => { active = false }
  }, [api, base, query, revision, tab])

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = String(new FormData(event.currentTarget).get('skill') ?? '').trim()
    if (next !== filter) {
      setBoard(null)
      setPeople(null)
      setFilter(next)
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    void run(async () => {
      const result = await api<{ team_id: number }>(base + '/teams', {
        method: 'POST', idempotent: true,
        body: {
          name: form.get('name'), description: form.get('description'),
          needed_skills: skillList(String(form.get('skills') ?? '')),
        },
      })
      openTeam(result.team_id)
    }, 'Team created.')
  }

  function more() {
    void run(async () => {
      if (tab === 'teams' && board?.next_before) {
        const next = await api<Board>(base + '/board?' + query + '&before=' + board.next_before)
        setBoard({ teams: [...board.teams, ...next.teams], next_before: next.next_before })
      }
      if (tab === 'people' && people?.next_after) {
        const next = await api<People>(base + '/people?' + query + '&after=' + people.next_after)
        setPeople({ people: [...people.people, ...next.people], next_after: next.next_after })
      }
    })
  }

  return (
    <>
      <section className="board-hero">
        <h1>Team board</h1>
        <p>Find an open seat or meet participants looking for a team.</p>
        {!profile.team && (
          <details className="create-team">
            <summary>Create a team</summary>
            <form className="stack inset" onSubmit={create}>
              <label>Team name<input name="name" minLength={3} maxLength={40} required /></label>
              <label>Description<textarea name="description" maxLength={500} rows={3} /></label>
              <label>Skills you need <span className="muted">(separate with commas)</span><input name="skills" /></label>
              <button className="primary" disabled={busy}>Create team</button>
            </form>
          </details>
        )}
      </section>

      <div className="board-tools">
        <div className="segmented" role="group" aria-label="Board view">
          <button type="button" aria-pressed={tab === 'teams'} onClick={() => setTab('teams')}>Open teams</button>
          <button type="button" aria-pressed={tab === 'people'} onClick={() => setTab('people')}>People</button>
        </div>
        <form className="row filter" onSubmit={search}>
          <label htmlFor="skill-filter">Filter by skill</label>
          <input id="skill-filter" name="skill" maxLength={30} placeholder="e.g. Python" />
          <button>Apply</button>
        </form>
      </div>
      {error && <p role="alert" className="error">{error}</p>}
      {tab === 'teams' && (
        <section aria-label="Open teams" className="cards">
          {board?.teams.map((team) => (
            <article key={team.id} className="panel team-card">
              <div className="team-card-info">
                <h2>{team.name}</h2>
                {team.description && <p className="muted">{team.description}</p>}
                {team.needed_skills.length > 0 && <div className="tags">{team.needed_skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}
              </div>
              <div className="capacity">
                <div className="capacity-label">
                  <span>{team.member_count}/{team.max_size} filled</span>
                  <span className="seat-count">{team.max_size - team.member_count} open</span>
                </div>
                <progress aria-label="Seats filled" value={team.member_count} max={team.max_size} />
              </div>
              <button className="card-action" type="button" onClick={() => openTeam(team.id)} aria-label={'View ' + team.name}>
                View team <span aria-hidden="true">→</span>
              </button>
            </article>
          ))}
          {!board && !error && <p className="panel empty-state" role="status">Loading teams…</p>}
          {board?.teams.length === 0 && (
            <p className="panel empty-state" role="status">{filter ? 'No open teams match this skill.' : 'No teams have open seats yet.'}</p>
          )}
        </section>
      )}
      {tab === 'people' && (
        <section aria-label="Available teammates" className="cards">
          {people?.people.map((person) => (
            <article key={person.id} className="panel">
              <div className="person-heading">
                <span className="avatar" aria-hidden="true">{person.display_name.slice(0, 1).toUpperCase()}</span>
                <div><h2>{person.display_name}</h2><p>{utcLabel(person.utc_offset_minutes)}</p></div>
              </div>
              {person.skills.length > 0 && <div className="tags">{person.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}
            </article>
          ))}
          {!people && !error && <p className="panel empty-state" role="status">Loading people…</p>}
          {people?.people.length === 0 && (
            <p className="panel empty-state" role="status">{filter ? 'No participants match this skill.' : 'No participants are looking for a team yet.'}</p>
          )}
        </section>
      )}
      {((tab === 'teams' && board?.next_before) || (tab === 'people' && people?.next_after)) &&
        <button className="load-more" type="button" disabled={busy} onClick={more}>Load more</button>}
    </>
  )
}
