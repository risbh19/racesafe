import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ApiError, makeApi, skillList, utcLabel, type Profile } from './api'
import { JoinDialog } from './components/JoinDialog'
import { useEvents } from './hooks/useEvents'
import { AuthPage } from './pages/AuthPage'
import { BoardPage } from './pages/BoardPage'
import { TeamPage } from './pages/TeamPage'
import './App.css'

export default function App() {
  const [token, setToken] = useState('')
  const [profile, setProfile] = useState<Profile | null>(null)
  const [teamId, setTeamId] = useState<number | null>(null)
  const [join, setJoin] = useState(false)
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null)
  const actionBusy = useRef(false)
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
    setJoin(false)
    setNotice(null)
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

  return (
    <div className="workspace">
      <a className="skip" href="#content">Skip to content</a>
      <header className="topbar">
        <div className="shell topbar-content">
          <button type="button" className="brand" onClick={() => setTeamId(null)}>
            <span className="brand-mark" aria-hidden="true">R</span>RaceSafe
          </button>
          <nav className="row nav" aria-label="Main">
            <button type="button" aria-pressed={teamId === null} onClick={() => setTeamId(null)}>Board</button>
            {profile?.team && <button type="button" aria-pressed={teamId === profile.team.id} onClick={() => setTeamId(profile.team!.id)}>My team</button>}
            {profile && !profile.team && <button type="button" onClick={() => setJoin(true)}>Join with code</button>}
            <button type="button" className="sign-out" onClick={signOut}>Sign out</button>
          </nav>
        </div>
      </header>

      <main id="content" className="shell content" tabIndex={-1}>
        {notice && <p role={notice.error ? 'alert' : 'status'} className={notice.error ? 'error' : 'notice'}>{notice.text}</p>}
        {!profile && <div className="panel"><p>{notice ? 'Could not load your profile.' : 'Loading your profile…'}</p>
          {notice && <button type="button" onClick={refresh}>Retry</button>}</div>}
        {profile && (
          <>
            <div className="meta-bar">
              <div className="person-heading">
                <span className="avatar" aria-hidden="true">{profile.display_name.slice(0, 1).toUpperCase()}</span>
                <div><strong>{profile.display_name}</strong><p>{utcLabel(profile.utc_offset_minutes)}</p></div>
              </div>
              <span className={connected ? 'connection live' : 'connection'} role="status">
                {connected ? 'Live updates on' : 'Connecting…'}
              </span>
            </div>
            {teamId === null
              ? <BoardPage api={api} profile={profile} revision={revision} busy={busy} run={run} openTeam={setTeamId} />
              : <TeamPage key={teamId} api={api} profile={profile} teamId={teamId} revision={revision} busy={busy} run={run} back={() => setTeamId(null)} />}

            {profile.requests.length > 0 && <details className="panel">
              <summary>My join requests</summary>
              <ul className="item-list">
                {profile.requests.map((request) => (
                  <li key={request.id}>
                    <span><strong>{request.team_name}</strong> · {request.status}</span>
                    {request.status === 'pending' && <button type="button" disabled={busy} onClick={() => void run(async () => {
                      await api('/join-requests/' + request.id, { method: 'DELETE' })
                    }, 'Join request cancelled.')}>Cancel</button>}
                  </li>
                ))}
              </ul>
            </details>}

            <details className="panel">
              <summary>My profile</summary>
              <form className="stack inset" onSubmit={saveProfile}>
                <label>Display name<input name="name" minLength={2} maxLength={60} defaultValue={profile.display_name} required /></label>
                <label>Skills<input name="skills" defaultValue={profile.skills.join(', ')} /></label>
                <label>UTC offset in minutes<input type="number" min={-720} max={840} name="utc_offset_minutes" defaultValue={profile.utc_offset_minutes} required /></label>
                {!profile.team && <label className="check"><input type="checkbox" name="looking" defaultChecked={profile.looking} />Show me on the people board</label>}
                <button disabled={busy}>Save profile</button>
              </form>
            </details>
          </>
        )}
      </main>
      {join && <JoinDialog api={api} close={() => setJoin(false)} joined={(id) => {
        setTeamId(id)
        setNotice({ text: 'You joined the team.', error: false })
        refresh()
      }} />}
    </div>
  )
}
