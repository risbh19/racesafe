export type Team = {
  id: number
  hackathon_id: number
  leader_id: number
  name: string
  description: string
  min_size: number
  max_size: number
  member_count: number
  needed_skills: string[]
  looking: boolean
  locked: boolean
}

export type Person = {
  id: number
  display_name: string
  skills: string[]
  utc_offset_minutes: number
}

export type Profile = Person & {
  email: string
  hackathon_id: number
  looking: boolean
  team: Team | null
  requests: { id: number; team_id: number; team_name: string; status: string }[]
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export type Api = <T>(
  path: string, options?: { method?: string; body?: unknown; idempotent?: boolean },
) => Promise<T>

export function makeApi(token?: string): Api {
  return async function request<T>(
    path: string, options: { method?: string; body?: unknown; idempotent?: boolean } = {},
  ): Promise<T> {
    const headers = new Headers()
    if (token) headers.set('Authorization', 'Bearer ' + token)
    if (options.body !== undefined) headers.set('Content-Type', 'application/json')
    if (options.idempotent) {
      const key = Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
        byte.toString(16).padStart(2, '0')).join('')
      headers.set('Idempotency-Key', key)
    }
    const init: RequestInit = {
      method: options.method,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    }

    let response: Response
    try {
      response = await fetch('/api' + path, init)
    } catch (error) {
      if (!options.idempotent || !(error instanceof TypeError)) throw error
      response = await fetch('/api' + path, init)
    }
    const payload = await response.json().catch(() => null)
    if (!response.ok) {
      const detail = payload?.detail
      const message = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((entry) => entry.loc.at(-1) + ': ' + entry.msg).join('. ')
          : 'Request failed (' + response.status + ')'
      throw new ApiError(response.status, message)
    }
    return payload as T
  }
}

export function skillList(value: string): string[] {
  return value.split(',').map((skill) => skill.trim()).filter(Boolean)
}

export function utcLabel(offset: number): string {
  const minutes = Math.abs(offset)
  const hours = Math.floor(minutes / 60)
  return 'UTC' + (offset < 0 ? '−' : '+') + hours + ':' + String(minutes % 60).padStart(2, '0')
}
