// Small wrapper around the FastAPI backend.
async function handle(res) {
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`)
  return body
}

export async function analyzeFile(file) {
  const form = new FormData()
  form.append('file', file)
  return handle(await fetch('/api/analyze', { method: 'POST', body: form }))
}

export async function listSamples() {
  return handle(await fetch('/api/samples'))
}

export async function analyzeSample(name) {
  return handle(await fetch(`/api/samples/${encodeURIComponent(name)}`))
}

export async function startJobSearch(body) {
  return handle(await fetch('/api/jobs/search', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }))
}

export async function getJobSearch(id) {
  return handle(await fetch(`/api/jobs/search/${encodeURIComponent(id)}`))
}
