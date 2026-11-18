import { useEffect, useRef, useState } from 'react'
import { getJobSearch, startJobSearch } from './api.js'

const POLL_MS = 2000
const PAGE = 10 // jobs shown before "See more"
const VERDICTS = [
  { key: 'APPLY', label: 'Apply', tone: 'apply' },
  { key: 'ALMOST', label: 'Almost there', tone: 'almost' },
  { key: 'SKIP', label: 'Skip', tone: 'skip' },
]

function buildRequest(result, location) {
  return {
    titles: [...result.recommended, ...result.stretch].map((m) => m.title),
    skills: result.skills.map((s) => ({ name: s.name, level: s.level })),
    experience_years: result.profile.experience_years || 0,
    location: location.trim(),
  }
}

function JobCard({ job }) {
  const v = VERDICTS.find((x) => x.key === job.verdict) || VERDICTS[2]
  const facts = [job.location, job.salary, job.experience_text, job.posted].filter(Boolean)
  return (
    <article className={`role job tone-${v.tone}`}>
      <div className="job-head">
        <div className="role-title">
          <span>{job.title}</span>
          <span className="muted role-family">{job.company}</span>
        </div>
        <span className={`verdict verdict-${v.tone}`}>{v.label}</span>
      </div>
      <div className="role-body">
        {facts.length > 0 && <p className="job-facts">{facts.join(' · ')}</p>}
        {job.matched_skills.length > 0 && (
          <p className="tags"><b>You have:</b> {job.matched_skills.join(', ')}</p>
        )}
        {job.missing_skills.length > 0 && (
          <p className="tags"><b>Missing:</b> {job.missing_skills.join(', ')}</p>
        )}
        {job.reasons.filter((r) => !r.startsWith('Missing:')).map((r) => (
          <p key={r} className="tiny muted">{r}</p>
        ))}
        <div className="job-foot">
          <span className="tiny muted">{job.is_internship ? 'Internship' : ''}</span>
          <a className="open-link" href={job.url} target="_blank" rel="noopener noreferrer">
            Open posting<span className="sr-only"> (opens in a new tab)</span> ↗
          </a>
        </div>
      </div>
    </article>
  )
}

export default function LiveJobs({ result }) {
  const [location, setLocation] = useState('')
  const [search, setSearch] = useState(null)
  const [error, setError] = useState('')
  const [verdict, setVerdict] = useState('ALL')
  const [internOnly, setInternOnly] = useState(false)
  const [starting, setStarting] = useState(false)
  const [limit, setLimit] = useState(PAGE)
  // changing a filter or the resume starts the list from the top again
  useEffect(() => { setLimit(PAGE) }, [verdict, internOnly, result])
  const timer = useRef(null)
  const token = useRef(0) // bumped for every new search; responses for an older one are ignored

  const stop = () => { clearInterval(timer.current); timer.current = null }

  // a new resume means old results no longer apply
  useEffect(() => { token.current += 1; stop(); setSearch(null); setError(''); setStarting(false) }, [result])
  useEffect(() => () => { token.current += 1; stop() }, [])

  async function find() {
    if (starting) return
    const mine = ++token.current
    const current = () => mine === token.current
    stop(); setError(''); setVerdict('ALL'); setInternOnly(false); setLimit(PAGE)
    setStarting(true)
    setSearch({ state: 'running', sites: [], jobs: [] })
    try {
      // "Search again" skips the 6-hour cache
      const body = { ...buildRequest(result, location), refresh: Boolean(search) }
      const { search_id } = await startJobSearch(body)
      if (!current()) return
      let finished = false
      const poll = async () => {
        try {
          const s = await getJobSearch(search_id)
          if (!current()) return
          setSearch(s)
          if (s.state === 'done') { finished = true; stop() }
        } catch (e) {
          if (!current()) return
          finished = true; stop(); setError(e.message)
        }
      }
      await poll()   // cached searches finish on the first poll
      if (current() && !finished) timer.current = setInterval(poll, POLL_MS)
    } catch (e) {
      if (current()) { setError(e.message); setSearch(null) }
    } finally {
      if (current()) setStarting(false)
    }
  }

  const running = starting || search?.state === 'running'
  const jobs = search?.jobs || []
  const shown = jobs.filter((j) => (verdict === 'ALL' || j.verdict === verdict)
    && (!internOnly || j.is_internship))
  const count = (k) => jobs.filter((j) => j.verdict === k).length

  return (
    <section className="live" aria-labelledby="live-title">
      <div className="live-head">
        <div>
          <h2 id="live-title">Live jobs</h2>
          <p className="muted">
            Current job and internship postings that fit this resume. Takes about a minute.
          </p>
        </div>
        <form className="live-form" onSubmit={(e) => { e.preventDefault(); find() }}>
          <label className="sr-only" htmlFor="live-loc">City (optional)</label>
          <input id="live-loc" type="text" placeholder="City (optional)" title="Leave blank to search all of India"
                 value={location} onChange={(e) => setLocation(e.target.value)} disabled={running} />
          <button type="submit" className="find-btn" disabled={running}>
            {running ? 'Searching…' : search ? 'Search again' : 'Find jobs'}
          </button>
        </form>
      </div>

      {error && <p className="error" role="alert">{error}</p>}

      {search && (
        <>
          {search.cached && <p className="tiny muted">Showing results saved from a search in the last 6 hours.</p>}
          {running && (
            <p className="search-status tiny muted" role="status">
              <span className="spinner" aria-hidden="true" />
              Searching for jobs…{jobs.length > 0 && ` ${jobs.length} found so far`}
            </p>
          )}

          {jobs.length > 0 && (
            <div className="job-filters">
              <div className="lane-tabs" role="tablist" aria-label="Filter by verdict">
                {VERDICTS.map((v) => (
                  <button key={v.key} role="tab" aria-selected={verdict === v.key}
                          className={`lane-tab tone-${v.tone} ${verdict === v.key ? 'on' : ''}`}
                          onClick={() => setVerdict(verdict === v.key ? 'ALL' : v.key)}>
                    <span className="lane-count">{count(v.key)}</span><span>{v.label}</span>
                  </button>
                ))}
              </div>
              <div className="filter-row">
                <label className="check">
                  <input type="checkbox" checked={internOnly} onChange={(e) => setInternOnly(e.target.checked)} />
                  Internships only
                </label>
                <span className="tiny muted">
                  Showing {Math.min(limit, shown.length)} of {shown.length}
                  {shown.length < jobs.length && ` (${jobs.length} total)`}
                </span>
              </div>
            </div>
          )}

          {shown.length > 0 ? (
            <>
              <div className="role-list">
                {shown.slice(0, limit).map((j) => <JobCard key={`${j.source}-${j.source_id}`} job={j} />)}
              </div>
              {shown.length > limit && (
                <div className="see-more">
                  <button className="see-more-btn" onClick={() => setLimit(limit + PAGE)}>
                    See more jobs
                    <span className="muted"> ({shown.length - limit} more)</span>
                  </button>
                </div>
              )}
              {limit > PAGE && shown.length <= limit && shown.length > PAGE && (
                <p className="see-more tiny muted">You have seen all {shown.length} jobs.</p>
              )}
            </>
          ) : !running && (
            <div className="empty">
              {jobs.length
                ? 'No postings match these filters.'
                : 'No postings found. Try another city.'}
            </div>
          )}
        </>
      )}
    </section>
  )
}
