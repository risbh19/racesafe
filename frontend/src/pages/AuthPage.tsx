import { useState, type FormEvent } from 'react'
import { makeApi, skillList } from '../api'

export function AuthPage({ signedIn }: { signedIn: (token: string) => void }) {
  const [registering, setRegistering] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const form = new FormData(event.currentTarget)
    const account = { email: form.get('email'), password: form.get('password') }
    const body = registering
      ? {
          ...account,
          display_name: form.get('display_name'),
          skills: skillList(String(form.get('skills') ?? '')),
          utc_offset_minutes: -new Date().getTimezoneOffset(),
        }
      : account
    setBusy(true)
    setError('')
    try {
      const result = await makeApi()<{ access_token: string }>(
        registering ? '/auth/register' : '/auth/login', { method: 'POST', body },
      )
      signedIn(result.access_token)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="auth-layout">
      <div className="auth-intro">
        <span className="brand">RaceSafe</span>
        <h1>Find your hackathon team.</h1>
        <p>Browse teams with open seats, connect with people who bring different skills, or start your own team.</p>
      </div>
      <section className="panel auth-panel" aria-labelledby="auth-title">
        <h2 id="auth-title">{registering ? 'Create an account' : 'Sign in'}</h2>
        <form onSubmit={submit} className="stack">
          {registering && <label>Display name<input name="display_name" minLength={2} maxLength={60} autoComplete="name" required /></label>}
          <label>Email<input name="email" type="email" maxLength={254} autoComplete="email" required /></label>
          <label>Password<input name="password" type="password" minLength={registering ? 10 : 1} maxLength={128} autoComplete={registering ? 'new-password' : 'current-password'} required /></label>
          {registering && <label>Skills <span className="muted">(separate with commas)</span><input name="skills" placeholder="Python, React, design" /></label>}
          {error && <p className="error" role="alert">{error}</p>}
          <button className="primary" disabled={busy}>{busy ? 'Working…' : registering ? 'Create account' : 'Sign in'}</button>
        </form>
        <button className="quiet" type="button" onClick={() => { setRegistering(!registering); setError('') }}>
          {registering ? 'I already have an account' : 'Create a RaceSafe account'}
        </button>
      </section>
    </main>
  )
}
