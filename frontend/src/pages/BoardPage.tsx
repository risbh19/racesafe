import { useEffect, useState, type FormEvent } from 'react'
import { skillList, utcLabel, type Api, type Person, type Profile, type Team } from '../api'
import { loadBoardWindow, PAGE_SIZE } from '../boardPagination'
import { Avatar, Dialog, Skills } from '../components/WorkspaceUI'

type Board = { teams: Team[]; next_before: number | null }
type People = { people: Person[]; next_after: number | null }

type Tab = 'teams' | 'people'
type Snapshot = { scope: string; count: number; next: number | null } & (
  { tab: 'teams'; items: Team[] } | { tab: 'people'; items: Person[] }
)

export type Run = (action: () => Promise<void>, success?: string) => Promise<void>

export function BoardPage({ api, profile, revision, busy, run, openTeam, joinWithCode }: {
  api: Api; profile: Profile; revision: number; busy: boolean; run: Run
  openTeam: (id: number) => void; joinWithCode: () => void
}) {
  const [tab, setTab] = useState<Tab>('teams')
  const [filter, setFilter] = useState('')
  const [searchText, setSearchText] = useState('')
  const [pageRequest, setPageRequest] = useState({ count: PAGE_SIZE })
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [failure, setFailure] = useState<{ scope: string; message: string } | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState('')
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

  function applyFilter(value: string) {
    const next = value.trim()
    if (next !== filter) {
      setSnapshot(null)
      setFailure(null)
      setFilter(next)
      setPageRequest({ count: PAGE_SIZE })
    }
  }

  function dismissCreate() {
    if (!busy) {
      setCreating(false)
      setCreateError('')
    }
  }

  function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setCreateError('')
    const form = new FormData(event.currentTarget)
    void run(async () => {
      try {
        const result = await api<{ team_id: number; is_draft?: boolean }>(base + '/teams', {
          method: 'POST', idempotent: true,
          body: {
            name: form.get('name'), description: form.get('description'),
            needed_skills: skillList(String(form.get('skills') ?? '')),
          },
        })
        setCreating(false)
        openTeam(result.team_id)
      } catch (reason) {
        setCreateError((reason as Error).message)
        throw reason
      }
    }, 'Team workspace created.')
  }

  return (
    <>
      <header className="board-banner">
        <div className="board-banner-copy">
          <h1>Find your team</h1>
          <p>Explore open teams or meet people looking for teammates.</p>
        </div>
        {!profile.team && (
          <div className="banner-actions">
            <button type="button" className="banner-secondary" onClick={joinWithCode}>Join with code</button>
            <button type="button" className="banner-primary" onClick={() => setCreating(true)}><span aria-hidden="true">+</span> Create a team</button>
          </div>
        )}
      </header>

      <div className="board-tools view-tools">
        <div className="view-switch" role="group" aria-label="Board view">
          <button type="button" aria-pressed={tab === 'teams'} onClick={() => selectTab('teams')}>Open teams</button>
          <button type="button" aria-pressed={tab === 'people'} onClick={() => selectTab('people')}>People</button>
        </div>
        <form className="filter" onSubmit={(event) => { event.preventDefault(); applyFilter(searchText) }}>
          <div className="search-field">
            <label className="sr-only" htmlFor="skill-filter">Filter by skill</label>
            <span className="search-icon" aria-hidden="true" />
            <input id="skill-filter" name="skill" value={searchText} maxLength={30} placeholder="Filter by skill"
              onChange={(event) => setSearchText(event.currentTarget.value)} />
          </div>
          <button type="submit">Apply</button>
        </form>
      </div>
      {filter && <div className="filter-summary"><span>Showing results for <strong>{filter}</strong></span>
        <button className="quiet" type="button" onClick={() => { setSearchText(''); applyFilter('') }}>Clear filter</button></div>}
      {error && <p role="alert" className="error">{error}</p>}
      {tab === 'teams' && (
        <section aria-label="Open teams" className="cards">
          {board?.map((team) => (
            <article key={team.id} className="panel team-card">
              <div className="card-top">
                <Avatar name={team.name} tone={team.id} />
                <span className={'badge ' + (team.is_draft ? 'badge-draft' : 'badge-open')}>{team.is_draft ? 'Draft' : 'Recruiting'}</span>
              </div>
              <div className="team-card-info">
                <h2>{team.name}</h2>
                {team.description && <p>{team.description}</p>}
                <Skills items={team.needed_skills} limit={3} />
              </div>
              <div className="capacity">
                <div className="capacity-label">
                  <span><strong>{team.member_count}/{team.max_size}</strong> members</span>
                  <span>{team.max_size - team.member_count} open</span>
                </div>
                <progress aria-label="Seats filled" value={team.member_count} max={team.max_size} />
              </div>
              <button className="card-action" type="button" onClick={() => openTeam(team.id)} aria-label={'View ' + team.name}>
                View team <span aria-hidden="true">↗</span>
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
            <article key={person.id} className="panel person-card">
              <div className="person-heading">
                <Avatar name={person.display_name} tone={person.id} />
                <div><h2>{person.display_name}</h2><p>{utcLabel(person.utc_offset_minutes)}</p></div>
              </div>
              <Skills items={person.skills} />
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
      {creating && <Dialog title="Create a team" onDismiss={dismissCreate}>
        <form className="stack" onSubmit={create}>
          <label>Team name<input name="name" minLength={3} maxLength={40} required placeholder="e.g. Pixel Pantry" /></label>
          <label>Description<textarea name="description" maxLength={500} rows={3} placeholder="What are you planning to build?" /></label>
          <label>Skills you need <input name="skills" placeholder="Python, design, React" /></label>
          <p className="field-hint">Separate skills with commas.</p>
          {createError && <p className="error" role="alert">{createError}</p>}
          <div className="dialog-actions">
            <button type="button" disabled={busy} onClick={dismissCreate}>Cancel</button>
            <button className="primary" disabled={busy}>{busy ? 'Creating…' : 'Create team'}</button>
          </div>
        </form>
      </Dialog>}
    </>
  )
}
