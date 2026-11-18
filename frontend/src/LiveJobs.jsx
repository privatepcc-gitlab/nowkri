import { useEffect, useRef, useState } from 'react'
import { getJobSearch, startJobSearch } from './api.js'

const POLL_MS = 2000
const VERDICTS = [
  { key: 'APPLY', label: 'Apply', tone: 'apply' },
  { key: 'ALMOST', label: 'Almost there', tone: 'almost' },
  { key: 'SKIP', label: 'Skip', tone: 'skip' },
]
const SITE_NAMES = { internshala: 'Internshala', shine: 'Shine', apna: 'Apna', naukri: 'Naukri' }
const siteName = (s) => SITE_NAMES[s] || s

function buildRequest(result, location) {
  return {
    titles: [...result.recommended, ...result.stretch].map((m) => m.title),
    skills: result.skills.map((s) => ({ name: s.name, level: s.level })),
    experience_years: result.profile.experience_years || 0,
    location: location.trim(),
  }
}

function SiteChip({ site }) {
  const busy = site.state === 'pending' || site.state === 'running'
  const bad = site.state === 'failed' || site.state === 'blocked'
  const text = busy ? 'searching…' : bad ? 'unavailable' : `${site.count} job${site.count === 1 ? '' : 's'}`
  return (
    <li className={`site-chip ${busy ? 'busy' : ''} ${bad ? 'bad' : ''}`} title={site.message || undefined}>
      {busy && <span className="spinner" aria-hidden="true" />}
      <b>{siteName(site.source)}</b> <span>{text}</span>
      {bad && site.message && <span className="site-msg">{site.message}</span>}
    </li>
  )
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
          <span className="tiny muted">
            {job.is_internship ? 'Internship on ' : 'On '}{siteName(job.source)}
            {job.also_on.length > 0 && `, also on ${job.also_on.map(siteName).join(', ')}`}
          </span>
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
  const [source, setSource] = useState('ALL')
  const [internOnly, setInternOnly] = useState(false)
  const [starting, setStarting] = useState(false)
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
    stop(); setError(''); setVerdict('ALL'); setSource('ALL'); setInternOnly(false)
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
    && (source === 'ALL' || j.source === source || j.also_on.includes(source))
    && (!internOnly || j.is_internship))
  const count = (k) => jobs.filter((j) => j.verdict === k).length
  const sources = [...new Set(jobs.flatMap((j) => [j.source, ...j.also_on]))]

  return (
    <section className="live" aria-labelledby="live-title">
      <div className="live-head">
        <div>
          <h2 id="live-title">Live jobs</h2>
          <p className="muted">
            Search Internshala, Shine and Apna for current postings that fit this resume. Takes about a minute.
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
          {search.sites.length > 0 && (
            <ul className="site-chips" aria-live="polite">
              {search.sites.map((s) => <SiteChip key={s.source} site={s} />)}
            </ul>
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
                <label>Site{' '}
                  <select value={source} onChange={(e) => setSource(e.target.value)}>
                    <option value="ALL">All sites</option>
                    {sources.map((s) => <option key={s} value={s}>{siteName(s)}</option>)}
                  </select>
                </label>
                <label className="check">
                  <input type="checkbox" checked={internOnly} onChange={(e) => setInternOnly(e.target.checked)} />
                  Internships only
                </label>
                <span className="tiny muted">{shown.length} of {jobs.length} shown</span>
              </div>
            </div>
          )}

          {shown.length > 0 ? (
            <div className="role-list">{shown.map((j) => <JobCard key={`${j.source}-${j.source_id}`} job={j} />)}</div>
          ) : !running && (
            <div className="empty">
              {jobs.length
                ? 'No postings match these filters.'
                : 'No postings found. Try another city, or check the site statuses above.'}
            </div>
          )}
        </>
      )}
    </section>
  )
}
