import http from 'k6/http'
import { check, sleep } from 'k6'

const base = __ENV.BASE_URL || 'http://127.0.0.1:8000'
const hackathonId = __ENV.HACKATHON_ID || '1'
const duration = __ENV.DURATION || '60s'
const paceSeconds = Number(__ENV.PACE_SECONDS ?? '1')

export const options = {
  scenarios: { board: { executor: 'constant-vus', vus: 100, duration } },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  thresholds: {
    'http_req_duration{endpoint:board}': ['p(95)<200'],
    'http_req_failed{endpoint:board}': ['rate==0'],
    checks: ['rate==1'],
  },
}

export function setup() {
  if (!__ENV.SEED_PASSWORD) throw new Error('Set SEED_PASSWORD to the same value used to seed the database.')
  const response = http.post(base + '/api/auth/login', JSON.stringify({
    email: 'seed-10000@benchmark.racesafe.test',
    password: __ENV.SEED_PASSWORD,
  }), { headers: { 'Content-Type': 'application/json' }, tags: { endpoint: 'login' } })
  if (response.status !== 200) throw new Error('Benchmark login failed: ' + response.status)
  return { token: response.json('access_token') }
}

export default function ({ token }) {
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
    base_url: base, vus: 100, duration, pace_seconds: paceSeconds,
    successful_board_requests: count, median_ms: latency.med, p95_ms: latency['p(95)'],
    p99_ms: latency['p(99)'], error_rate: errors.rate,
    board_requests_per_second: count / (data.state.testRunDurationMs / 1000),
  }
  return {
    stdout: JSON.stringify(summary, null, 2) + '\n',
    [__ENV.REPORT_PATH || 'loadtest/report.json']: JSON.stringify(summary, null, 2) + '\n',
  }
}
