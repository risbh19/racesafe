import { useEffect, useState, type FormEvent } from 'react'
import { skillList, utcLabel, type Api, type Person, type Profile, type Team } from '../api'
import { loadBoardWindow, PAGE_SIZE } from '../boardPagination'

type Board = { teams: Team[]; next_before: number | null }
type People = { people: Person[]; next_after: number | null }

type Tab = 'teams' | 'people'
type Snapshot = { scope: string; count: number; next: number | null } & (
  { tab: 'teams'; items: Team[] } | { tab: 'people'; items: Person[] }
)

export type Run = (action: () => Promise<void>, success?: string) => Promise<void>

export function BoardPage({ api, profile, revision, busy, run, openTeam }: {
  api: Api; profile: Profile; revision: number; busy: boolean; run: Run; openTeam: (id: number) => void
}) {
  const [tab, setTab] = useState<Tab>('teams')
  const [filter, setFilter] = useState('')
  const [pageRequest, setPageRequest] = useState({ count: PAGE_SIZE })
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [failure, setFailure] = useState<{ scope: string; message: string } | null>(null)
  const base = '/hackathons/' + profile.hackathon_id
  const scope = JSON.stringify([base, tab, filter])
  const current = snapshot?.scope === scope ? snapshot : null
  const board = current?.tab === 'teams' ? current.items : null
  const people = current?.tab === 'people' ? current.items : null
  const error = failure?.scope === scope ? failure.message : ''

  useEffect(() => {
    const controller = new AbortController()
    const { signal } = controller
    const { count } = pageRequest

    function query(limit: number, cursor: number | null, cursorName: string) {
      const params = new URLSearchParams({ limit: String(limit) })
      if (filter) params.set('skill', filter)
      if (cursor !== null) params.set(cursorName, String(cursor))
      return '?' + params
    }

    async function load() {
      try {
        if (tab === 'teams') {
          const result = await loadBoardWindow(count, async (limit, cursor) => {
            const page = await api<Board>(base + '/board' + query(limit, cursor, 'before'), { signal })
            return { items: page.teams, next: page.next_before }
          })
          if (!signal.aborted) setSnapshot({ scope, count, tab, ...result })
        } else {
          const result = await loadBoardWindow(count, async (limit, cursor) => {
            const page = await api<People>(base + '/people' + query(limit, cursor, 'after'), { signal })
            return { items: page.people, next: page.next_after }
          })
          if (!signal.aborted) setSnapshot({ scope, count, tab, ...result })
        }
        if (!signal.aborted) setFailure(null)
      } catch (reason) {
        if (!signal.aborted) setFailure({ scope, message: (reason as Error).message })
      }
    }
    void load()
    return () => controller.abort()
  }, [api, base, filter, pageRequest, revision, scope, tab])

  function selectTab(next: Tab) {
    if (next === tab) return
    setSnapshot(null)
    setFailure(null)
    setTab(next)
    setPageRequest({ count: PAGE_SIZE })
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = String(new FormData(event.currentTarget).get('skill') ?? '').trim()
    if (next !== filter) {
      setSnapshot(null)
      setFailure(null)
      setFilter(next)
      setPageRequest({ count: PAGE_SIZE })
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
          <button type="button" aria-pressed={tab === 'teams'} onClick={() => selectTab('teams')}>Open teams</button>
          <button type="button" aria-pressed={tab === 'people'} onClick={() => selectTab('people')}>People</button>
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
          {board?.map((team) => (
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
          {board?.length === 0 && (
            <p className="panel empty-state" role="status">{filter ? 'No open teams match this skill.' : 'No teams have open seats yet.'}</p>
          )}
        </section>
      )}
      {tab === 'people' && (
        <section aria-label="Available teammates" className="cards">
          {people?.map((person) => (
            <article key={person.id} className="panel">
              <div className="person-heading">
                <span className="avatar" aria-hidden="true">{person.display_name.slice(0, 1).toUpperCase()}</span>
                <div><h2>{person.display_name}</h2><p>{utcLabel(person.utc_offset_minutes)}</p></div>
              </div>
              {person.skills.length > 0 && <div className="tags">{person.skills.map((skill) => <span key={skill}>{skill}</span>)}</div>}
            </article>
          ))}
          {!people && !error && <p className="panel empty-state" role="status">Loading people…</p>}
          {people?.length === 0 && (
            <p className="panel empty-state" role="status">{filter ? 'No participants match this skill.' : 'No participants are looking for a team yet.'}</p>
          )}
        </section>
      )}
      {current?.next != null &&
        <button className="load-more" type="button"
          disabled={busy || (!error && current.count < pageRequest.count)}
          onClick={() => setPageRequest({ count: current.count + PAGE_SIZE })}>Load more</button>}
    </>
  )
}
