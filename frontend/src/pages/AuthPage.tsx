import { useEffect, useState, type FormEvent } from 'react'
import { makeApi, skillList } from '../api'

function readVerificationToken() {
  return new URLSearchParams(window.location.hash.slice(1)).get('verify-email') ?? ''
}

export function AuthPage({ signedIn }: { signedIn: (token: string) => void }) {
  const [verificationToken, setVerificationToken] = useState(readVerificationToken)
  const [verificationSent, setVerificationSent] = useState(false)
  const [registering, setRegistering] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    function clearVerificationLink() {
      if (readVerificationToken()) {
        window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
      }
    }

    function openVerificationLink() {
      const token = readVerificationToken()
      if (!token) return
      setVerificationToken(token)
      setVerificationSent(false)
      setError('')
      clearVerificationLink()
    }

    clearVerificationLink()
    window.addEventListener('hashchange', openVerificationLink)
    return () => window.removeEventListener('hashchange', openVerificationLink)
  }, [])

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
      if (verificationToken) {
        const result = await makeApi()<{ access_token: string }>('/auth/verify-email', {
          method: 'POST', body: { token: verificationToken, password: account.password },
        })
        signedIn(result.access_token)
      } else {
        const result = await makeApi()<{ access_token: string } | { verification_required: true }>(
          registering ? '/auth/register' : '/auth/login', { method: 'POST', body },
        )
        if ('verification_required' in result) setVerificationSent(true)
        else signedIn(result.access_token)
      }
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setBusy(false)
    }
  }

  function returnToSignup() {
    setVerificationToken('')
    setVerificationSent(false)
    setRegistering(true)
    setError('')
  }

  const verifying = Boolean(verificationToken)
  const title = verificationSent ? 'Check your inbox' : verifying ? 'Verify your email' : registering ? 'Create an account' : 'Sign in'

  return (
    <main className="auth-layout">
      <div className="auth-intro">
        <span className="brand">RaceSafe</span>
        <h1>Find your hackathon team.</h1>
        <p>Browse teams with open seats, connect with people who bring different skills, or start your own team.</p>
      </div>
      <section className="panel auth-panel" aria-labelledby="auth-title">
        <h2 id="auth-title">{title}</h2>
        {verificationSent ? (
          <>
            <p role="status">If this email can be registered, you’ll receive a verification link. Open it within 30 minutes and enter your signup password.</p>
            <button className="quiet" type="button" onClick={returnToSignup}>Request another link</button>
            <button className="quiet" type="button" onClick={() => { setVerificationSent(false); setRegistering(false) }}>Back to sign in</button>
          </>
        ) : (
          <>
            {verifying && <p>Enter the password you chose when signing up to verify your email.</p>}
            <form key={verifying ? 'verify' : registering ? 'register' : 'login'} onSubmit={submit} className="stack">
              {!verifying && registering && <label>Display name<input name="display_name" minLength={2} maxLength={60} autoComplete="name" required /></label>}
              {!verifying && <label>Email<input name="email" type="email" maxLength={254} autoComplete="email" required /></label>}
              <label>Password<input name="password" type="password" minLength={verifying || registering ? 10 : 1} maxLength={128} autoComplete={registering && !verifying ? 'new-password' : 'current-password'} required /></label>
              {!verifying && registering && <label>Skills <span className="muted">(separate with commas)</span><input name="skills" placeholder="Python, React, design" /></label>}
              {error && <p className="error" role="alert">{error}</p>}
              <button className="primary" disabled={busy}>{busy ? 'Working…' : verifying ? 'Verify and sign in' : registering ? 'Create account' : 'Sign in'}</button>
            </form>
            {verifying ? (
              <button className="quiet" type="button" disabled={busy} onClick={returnToSignup}>Request another link</button>
            ) : (
              <button className="quiet" type="button" disabled={busy} onClick={() => { setRegistering(!registering); setError('') }}>
                {registering ? 'I already have an account' : 'Create a RaceSafe account'}
              </button>
            )}
          </>
        )}
      </section>
    </main>
  )
}
