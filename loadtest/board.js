import http from 'k6/http'
import exec from 'k6/execution'
import { check, sleep } from 'k6'

const base = __ENV.BASE_URL || 'http://127.0.0.1:8000'
const hackathonId = __ENV.HACKATHON_ID || '1'
const duration = __ENV.DURATION || '60s'
const paceSeconds = Number(__ENV.PACE_SECONDS ?? '1')
const vus = 100
const boardTokens = __ENV.BOARD_TOKEN_FILE ? JSON.parse(open(__ENV.BOARD_TOKEN_FILE)) : null

export const options = {
  scenarios: { board: { executor: 'constant-vus', vus, duration } },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  thresholds: {
    'http_req_duration{endpoint:board}': ['p(95)<200'],
    'http_req_failed{endpoint:board}': ['rate==0'],
    'http_reqs{endpoint:board}': ['count>=100'],
    checks: ['rate==1'],
  },
}

export function setup() {
  if (boardTokens !== null) {
    if (!Array.isArray(boardTokens) || boardTokens.length !== vus ||
        boardTokens.some((token) => typeof token !== 'string' || token.length === 0) ||
        new Set(boardTokens).size !== vus) {
      throw new Error('BOARD_TOKEN_FILE must contain 100 distinct bearer tokens.')
    }
    return null
  }
  if (!__ENV.SEED_PASSWORD) throw new Error('Set SEED_PASSWORD to the same value used to seed the database.')
  const response = http.post(base + '/api/auth/login', JSON.stringify({
    email: 'seed-10000@benchmark.racesafe.test',
    password: __ENV.SEED_PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'login' } })
  if (response.status !== 200) throw new Error('Benchmark login failed: ' + response.status)
  return { token: response.json('access_token') }
}

export default function (data) {
  const token = boardTokens === null ? data.token : boardTokens[exec.vu.idInTest - 1]
  const response = http.get(base + '/api/hackathons/' + hackathonId + '/board?limit=20', {
    headers: { Authorization: 'Bearer ' + token },
    tags: { endpoint: 'board' },
    responseType: 'text',
  })
  check(response, {
    'board is 200': (r) => r.status === 200,
    'board has 20 teams': (r) => r.status === 200 && r.json('teams').length === 20,
  })
  if (paceSeconds > 0) sleep(paceSeconds)
}

export function handleSummary(data) {
  const latency = data.metrics['http_req_duration{endpoint:board}']?.values || {}
  const errors = data.metrics['http_req_failed{endpoint:board}']?.values || {}
  const count = data.metrics.checks?.values?.passes / 2 || 0
  const summary = {
    base_url: base, vus, duration, pace_seconds: paceSeconds,
    authenticated_accounts: boardTokens === null ? 1 : vus,
    commit: __ENV.GITHUB_SHA || null,
    successful_board_requests: count, median_ms: latency.med, p95_ms: latency['p(95)'],
    p99_ms: latency['p(99)'], error_rate: errors.rate,
    board_requests_per_second: count / (data.state.testRunDurationMs / 1000),
  }
  return {
    stdout: JSON.stringify(summary, null, 2) + '\n',
    [__ENV.REPORT_PATH || 'loadtest/report.json']: JSON.stringify(summary, null, 2) + '\n',
  }
}
