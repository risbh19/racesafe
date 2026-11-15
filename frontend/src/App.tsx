import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ApiError, makeApi, skillList, utcLabel, type Profile } from './api'
import { ArchivedTeams, MyRequests } from './components/Activity'
import { JoinDialog } from './components/JoinDialog'
import { Avatar, Brand } from './components/WorkspaceUI'
import { useEvents } from './hooks/useEvents'
import { AuthPage } from './pages/AuthPage'
import { BoardPage } from './pages/BoardPage'
import { TeamPage } from './pages/TeamPage'
import './App.css'

type View = 'board' | 'team' | 'requests' | 'profile' | 'archive'
const headings: Record<View, string> = {
  board: 'Discovery', team: 'Team workspace', requests: 'My requests', profile: 'My profile', archive: 'Archived teams',
}

export default function App() {
  const [token, setToken] = useState('')
  const [profile, setProfile] = useState<Profile | null>(null)
  const [teamId, setTeamId] = useState<number | null>(null)
  const [view, setView] = useState<View>('board')
  const [join, setJoin] = useState(false)
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null)
  const actionBusy = useRef(false)
  const content = useRef<HTMLElement>(null)
  const account = useRef<HTMLDetailsElement>(null)
  const api = useMemo(() => makeApi(token), [token])
  const refresh = () => setRevision((current) => current + 1)
  const connected = useEvents(token, profile?.hackathon_id, refresh)

  useEffect(() => {
    if (!token) return
    let active = true
    void api<Profile>('/me').then((data) => {
      if (active) setProfile(data)
    }).catch((error: unknown) => {
      if (!active) return
      if (error instanceof ApiError && error.status === 401) {
        setToken('')
        setProfile(null)
        setTeamId(null)
        setView('board')
        setJoin(false)
      } else {
        setNotice({ text: (error as Error).message, error: true })
      }
    })
    return () => { active = false }
  }, [api, token, revision])

  function signOut() {
    setToken('')
    setProfile(null)
    setTeamId(null)
    setView('board')
    setJoin(false)
    setNotice(null)
  }

  function navigate(next: View) {
    account.current?.removeAttribute('open')
    setView(next)
    window.requestAnimationFrame(() => content.current?.focus())
  }

  function openTeam(id: number) {
    setTeamId(id)
    navigate('team')
  }

  async function run(action: () => Promise<void>, success?: string) {
    if (actionBusy.current) return
    actionBusy.current = true
    setBusy(true)
    setNotice(null)
    try {
      await action()
      if (success) {
        setNotice({ text: success, error: false })
        refresh()
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        signOut()
      } else {
        setNotice({ text: (error as Error).message, error: true })
        if (error instanceof ApiError && error.status === 409) refresh()
      }
    } finally {
      actionBusy.current = false
      setBusy(false)
    }
  }

  function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    void run(async () => {
      await api('/me', {
        method: 'PATCH',
        body: {
          display_name: form.get('name'),
          skills: skillList(String(form.get('skills') ?? '')),
          utc_offset_minutes: Number(form.get('utc_offset_minutes')),
          looking: form.has('looking'),
        },
      })
    }, 'Profile saved.')
  }

  if (!token) return <AuthPage signedIn={setToken} />

  const ownTeamId = profile?.team?.id
  const onOwnTeam = view === 'team' && teamId === ownTeamId
  return (
    <div className="workspace">
      <a className="skip" href="#content">Skip to content</a>
      <aside className="sidebar" aria-label="RaceSafe workspace">
        <button className="brand-home" type="button" onClick={() => navigate('board')}><Brand /></button>
        <nav className="main-nav" aria-label="Workspace">
          <button type="button" aria-current={view === 'board' || (view === 'team' && !onOwnTeam) ? 'page' : undefined}
            onClick={() => navigate('board')}><span className="nav-icon board-icon" aria-hidden="true" />Board</button>
          {ownTeamId !== undefined && <button type="button" aria-current={onOwnTeam ? 'page' : undefined}
            onClick={() => openTeam(ownTeamId)}><span className="nav-icon team-icon" aria-hidden="true" />My team</button>}
          {profile && <button type="button" aria-current={view === 'requests' ? 'page' : undefined}
            onClick={() => navigate('requests')}><span className="nav-icon inbox-icon" aria-hidden="true" />My requests</button>}
        </nav>
        <details className="account-menu" ref={account} onKeyDown={(event) => {
          const menu = event.currentTarget
          if (event.key === 'Escape' && menu.open) {
            event.preventDefault()
            menu.open = false
            menu.querySelector('summary')?.focus()
          }
        }}>
          <summary aria-label="Account">
            <Avatar name={profile?.display_name || 'RaceSafe'} tone={profile?.id} />
            <span className="account-identity"><strong>{profile?.display_name || 'Account'}</strong>
              {profile && <small>{utcLabel(profile.utc_offset_minutes)}</small>}
            </span>
            <span className="account-chevron" aria-hidden="true">⌃</span>
          </summary>
          <div className="account-actions">
            {profile && <><button type="button" onClick={() => navigate('profile')}>My profile</button>
              <button type="button" onClick={() => navigate('archive')}>Archived teams</button></>}
            <button type="button" onClick={signOut}>Sign out</button>
          </div>
        </details>
      </aside>

      <div className="workspace-body">
        <header className="workspace-bar">
          <div className="workspace-bar-inner">
            <p className="workspace-location"><span>Hackathon</span><span aria-hidden="true">/</span><strong>{headings[view]}</strong></p>
            <span className={connected ? 'connection live' : 'connection'} role="status">
              {connected ? 'Live updates on' : 'Connecting…'}
            </span>
          </div>
        </header>

        <main id="content" ref={content} className="content" tabIndex={-1}>
          {notice && <p role={notice.error ? 'alert' : 'status'} className={notice.error ? 'error' : 'notice'}>{notice.text}</p>}
          {!profile && <section className="panel stack"><p>{notice ? 'Could not load your profile.' : 'Loading your profile…'}</p>
            {notice && <button type="button" onClick={refresh}>Retry</button>}</section>}
          {profile && view === 'board' && <BoardPage api={api} profile={profile} revision={revision} busy={busy} run={run}
            openTeam={openTeam} joinWithCode={() => setJoin(true)} />}
          {profile && view === 'team' && teamId !== null && <TeamPage key={teamId} api={api} profile={profile} teamId={teamId}
            revision={revision} busy={busy} run={run} back={() => navigate('board')} />}
          {profile && view === 'requests' && <MyRequests api={api} revision={revision} run={run} busy={busy} openTeam={openTeam} />}
          {profile && view === 'archive' && <ArchivedTeams api={api} revision={revision} />}
          {profile && view === 'profile' && <>
            <header className="page-heading">
              <h1>My profile</h1>
              <p>Update the skills and time zone other hackers see.</p>
            </header>
            <section className="panel profile-panel">
              <div className="person-heading profile-identity">
                <Avatar name={profile.display_name} tone={profile.id} />
                <div><strong>{profile.display_name}</strong><p>{profile.email}</p></div>
              </div>
              <form className="stack" onSubmit={saveProfile}>
                <label>Display name<input name="name" minLength={2} maxLength={60} defaultValue={profile.display_name} required /></label>
                <label>Skills<input name="skills" defaultValue={profile.skills.join(', ')} placeholder="Python, design, React" /></label>
                <label>UTC offset in minutes<input type="number" min={-720} max={840} name="utc_offset_minutes" defaultValue={profile.utc_offset_minutes} required /></label>
                {!profile.team && <label className="check"><input type="checkbox" name="looking" defaultChecked={profile.looking} />Show me on the people board</label>}
                <button className="primary" disabled={busy}>Save profile</button>
              </form>
            </section>
          </>}
        </main>
      </div>
      {join && <JoinDialog api={api} close={() => setJoin(false)} joined={(id) => {
        openTeam(id)
        setNotice({ text: 'You joined the team.', error: false })
        refresh()
      }} />}
    </div>
  )
}
