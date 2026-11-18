import { useEffect, useRef, useState } from 'react'
import { analyzeFile, analyzeSample, listSamples } from './api.js'
import { Profile, RoleCard, SkillList } from './components.jsx'
import LiveJobs from './LiveJobs.jsx'

const LANES = [
  { key: 'recommended', label: 'Apply', tone: 'apply',
    blurb: 'You meet every must-have skill at the level these roles need.' },
  { key: 'stretch', label: 'Almost there', tone: 'almost',
    blurb: 'One gap away. Close it, then apply.' },
  { key: 'not_recommended', label: 'Skip for now', tone: 'skip',
    blurb: 'Not a fit yet. Each one says why, so nothing is a mystery.' },
]

const prettySample = (n) => n.replace('.txt', '').replace(/_/g, ' ')

export default function App() {
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [lane, setLane] = useState('recommended')
  const [samples, setSamples] = useState([])
  const [dragging, setDragging] = useState(false)
  const [fileName, setFileName] = useState('')
  const [pdfUrl, setPdfUrl] = useState('')
  const inputRef = useRef(null)

  useEffect(() => { listSamples().then(setSamples).catch(() => {}) }, [])
  // free the old PDF blob whenever a new resume replaces it
  useEffect(() => () => { if (pdfUrl) URL.revokeObjectURL(pdfUrl) }, [pdfUrl])

  async function run(promise, label, file) {
    const isPdf = file && /\.pdf$/i.test(file.name)
    setPdfUrl(isPdf ? URL.createObjectURL(file) : '')
    setLoading(true); setError(''); setFileName(label)
    try {
      const r = await promise
      setResult(r)
      setLane(r.recommended.length ? 'recommended' : r.stretch.length ? 'stretch' : 'not_recommended')
    } catch (e) {
      setError(e.message); setResult(null)
    } finally {
      setLoading(false)
    }
  }

  function onFile(file) {
    if (!file) return
    run(analyzeFile(file), file.name, file)
  }

  const current = LANES.find((l) => l.key === lane)

  return (
    <div className="page">
      <header className="top">
        <span className="brand">Job Hunt</span>
        <span className="top-note">Resume to job-title matcher</span>
      </header>

      <section className={`hero ${result ? 'hero-compact' : ''}`}>
        <h1>Find the jobs your resume is ready for.</h1>
        <p className="lede">
          Upload your resume. Job Hunt reads your skills, estimates how strong each one is,
          and matches you only to roles where you meet the must-haves.
        </p>

        <label
          className={`drop ${dragging ? 'drop-active' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); onFile(e.dataTransfer.files[0]) }}
        >
          <input ref={inputRef} type="file" accept=".pdf,.docx,.txt"
                 onChange={(e) => onFile(e.target.files[0])} />
          <span className="drop-title">
            {loading ? `Reading ${fileName}…` : 'Drop your resume here, or choose a file'}
          </span>
          <span className="drop-sub">PDF, DOCX or TXT, up to 5 MB</span>
        </label>

        {samples.length > 0 && (
          <div className="samples">
            <span>No resume handy? Try a sample:</span>
            {samples.map((s) => (
              <button key={s} className="chip" disabled={loading}
                      onClick={() => run(analyzeSample(s), prettySample(s))}>
                {prettySample(s)}
              </button>
            ))}
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      {result && (
        <main className="results">
          <aside className="side">
            <Profile profile={result.profile} source={fileName}
                     resumeText={result.resume_text} pdfUrl={pdfUrl} />
            <SkillList skills={result.skills} />
          </aside>

          <section className="lanes">
            <div className="lane-tabs" role="tablist">
              {LANES.map((l) => (
                <button key={l.key} role="tab" aria-selected={lane === l.key}
                        className={`lane-tab tone-${l.tone} ${lane === l.key ? 'on' : ''}`}
                        onClick={() => setLane(l.key)}>
                  <span className="lane-count">{result[l.key].length}</span>
                  <span>{l.label}</span>
                </button>
              ))}
            </div>
            <p className="lane-blurb">{current.blurb}</p>

            {result[lane].length === 0 ? (
              <div className="empty">
                {lane === 'recommended'
                  ? <>No role is a full match yet. Open <b>Almost there</b> to see what is one skill away.</>
                  : 'Nothing in this list.'}
              </div>
            ) : (
              <div className="role-list">
                {result[lane].map((m) => <RoleCard key={m.title} match={m} tone={current.tone} />)}
              </div>
            )}
          </section>
        </main>
      )}

      {result && <LiveJobs result={result} />}

      <footer className="foot">
        Mini project, Dept. of CSE (Data Science), Sir MVIT. Scores are guidance, not a guarantee.
      </footer>
    </div>
  )
}
