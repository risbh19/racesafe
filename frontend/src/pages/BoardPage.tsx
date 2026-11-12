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
      <header className="section-head">
        <div><h1>Team board</h1><p className="muted">Find an open seat or meet participants looking for a team.</p></div>
      </header>

      {!profile.team && (
        <details className="panel">
          <summary>Create a team</summary>
          <form className="stack inset" onSubmit={create}>
            <label>Team name<input name="name" minLength={3} maxLength={40} required /></label>
            <label>Description<textarea name="description" maxLength={500} rows={3} /></label>
            <label>Skills you need <span className="muted">(separate with commas)</span><input name="skills" /></label>
            <button className="primary" disabled={busy}>Create team</button>
          </form>
        </details>
      )}

      <div className="board-tools">
        <div className="row" aria-label="Board view">
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
              <span className="seat-count">{team.max_size - team.member_count} open / {team.max_size} seats</span>
              <h2>{team.name}</h2>
              {team.description && <p>{team.description}</p>}
              <div className="tags">{team.needed_skills.map((skill) => <span key={skill}>{skill}</span>)}</div>
              <button type="button" onClick={() => openTeam(team.id)} aria-label={'View ' + team.name}>View team</button>
            </article>
          ))}
          {!board && !error && <p role="status">Loading teams…</p>}
          {board?.teams.length === 0 && <p className="muted">No open teams match this filter.</p>}
        </section>
      )}
      {tab === 'people' && (
        <section aria-label="Available teammates" className="cards">
          {people?.people.map((person) => (
            <article key={person.id} className="panel">
              <h2>{person.display_name}</h2>
              <p className="muted">{utcLabel(person.utc_offset_minutes)}</p>
              <div className="tags">{person.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>
            </article>
          ))}
          {!people && !error && <p role="status">Loading people…</p>}
          {people?.people.length === 0 && <p className="muted">No participants match this filter.</p>}
        </section>
      )}
      {((tab === 'teams' && board?.next_before) || (tab === 'people' && people?.next_after)) &&
        <button type="button" disabled={busy} onClick={more}>Load more</button>}
    </>
  )
}
