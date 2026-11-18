import { useState } from 'react'

const LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Expert']

/* Similar categories are shown together so the list stays short. */
const GROUPS = [
  { label: 'Languages', cats: ['Programming Language'] },
  { label: 'Data, AI & Databases', cats: ['Data', 'AI/ML', 'Database'] },
  { label: 'Web, Mobile & Design', cats: ['Web', 'Mobile', 'Design', 'Web3', 'Game Dev'] },
  { label: 'Cloud, DevOps & Systems', cats: ['DevOps & Cloud', 'Testing', 'Security & Networks', 'Embedded & IoT'] },
  { label: 'Core & Soft Skills', cats: ['CS Fundamentals', 'Business', 'Soft Skill'] },
]
const groupOf = (cat) => (GROUPS.find((g) => g.cats.includes(cat)) || { label: 'Other' }).label

/* Four-step track: filled = your level, ring = level the role needs */
export function LevelTrack({ have, need, label, mini }) {
  return (
    <span className={`track ${mini ? 'mini' : ''}`} role="img"
          aria-label={`${label}: you ${LEVELS[have - 1] || 'not found'}${need ? `, needs ${LEVELS[need - 1]}` : ''}`}>
      {[1, 2, 3, 4].map((i) => (
        <span key={i}
              className={`step ${i <= have ? 'have' : ''} ${need === i ? 'need' : ''} ${need && i <= need && i > have ? 'gap' : ''}`} />
      ))}
    </span>
  )
}

const Check = () => (
  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
    <path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
const Cross = () => (
  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
    <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
  </svg>
)

export function Profile({ profile, source, resumeText, pdfUrl }) {
  const [big, setBig] = useState(false)
  const yrs = profile.experience_years
  const months = Math.round(yrs * 12)
  const expLabel = !yrs ? 'Fresher'
    : yrs < 1 ? `${months} month${months === 1 ? '' : 's'} experience`
    : `${yrs} year${yrs === 1 ? '' : 's'} experience`
  return (
    <div className="panel profile">
      <h2>{profile.name || source}</h2>
      {profile.education && <p className="edu muted" title={profile.education}>{profile.education}</p>}
      <p className="meta">
        <span className="pill" title={profile.experience_source}>{expLabel}</span>
        <span className="pill" title={`Read from: ${profile.sections_found.join(', ')}`}>
          {profile.sections_found.length} sections read
        </span>
      </p>

      {(pdfUrl || resumeText) && (
        <div className="cv">
          <div className="cv-bar">
            <span className="cv-name" title={source}>{source}</span>
            {pdfUrl
              ? <a className="cv-btn" href={pdfUrl} target="_blank" rel="noreferrer">Open full</a>
              : <button className="cv-btn" onClick={() => setBig(!big)} aria-expanded={big}>
                  {big ? 'Shrink' : 'Expand'}
                </button>}
          </div>
          {pdfUrl
            ? <iframe className="cv-frame" src={`${pdfUrl}#toolbar=0&navpanes=0&view=FitH`} title="Resume preview" />
            : <pre className={`cv-text ${big ? 'big' : ''}`} tabIndex={0} aria-label="Resume text">{resumeText}</pre>}
        </div>
      )}
    </div>
  )
}

export function SkillList({ skills }) {
  const groups = new Map(GROUPS.map((g) => [g.label, []]))
  skills.forEach((s) => {
    const g = groupOf(s.category)
    if (!groups.has(g)) groups.set(g, [])
    groups.get(g).push(s)
  })
  const counts = [4, 3, 2, 1].map((lv) => ({ lv, n: skills.filter((s) => s.level === lv).length }))
  return (
    <div className="panel skills">
      <h3>Your skills <span className="muted">({skills.length})</span></h3>
      <p className="tiny muted">
        {counts.filter((c) => c.n).map((c) => `${c.n} ${LEVELS[c.lv - 1]}`).join(' · ')}
        <span className="hint"> · hover a skill to see why</span>
      </p>
      {[...groups].filter(([, list]) => list.length).map(([label, list]) => (
        <div key={label} className="skill-group">
          <h4>{label}</h4>
          <ul className="skill-chips">
            {[...list].sort((a, b) => b.level - a.level).map((s) => (
              <li key={s.name} className="skill-chip" title={`${s.level_name}: ${s.reasons.join('; ')}`}>
                <span>{s.name}</span>
                <LevelTrack have={s.level} label={s.name} mini />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

/* "Python / R" -> "Python" when met; drop "(or similar)" noise */
function reqLabel(r) {
  if (r.met && r.your_skill) return r.your_skill
  return r.requirement.replace(/\s*\(or similar\)/i, '')
}

export function RoleCard({ match, tone }) {
  const [open, setOpen] = useState(false)
  const b = match.breakdown
  const bonus = match.matched_good_to_have
  const showReasons = tone !== 'apply' && match.reasons.length > 0
  return (
    <article className={`role tone-${tone}`}>
      <div className="role-head">
        <span className="role-title">
          <span>{match.title}</span>
          <span className="muted role-family">{match.family}{match.min_years ? ` · ${match.min_years}+ yrs` : ''}</span>
        </span>
        <span className="score" title={`60% must-haves (${b.must_have}) + 25% bonus (${b.good_to_have}) + 15% text (${b.text_similarity})`}>
          <b>{Math.round(match.score)}</b><small>%</small>
        </span>
      </div>

      <div className="role-body">
        <ul className="reqs-chips" aria-label="Must-have skills">
          {match.requirements.map((r) => (
            <li key={r.requirement} className={`req ${r.met ? 'ok' : 'no'}`}
                title={`${r.requirement}: you ${r.your_level_name}, needs ${r.min_level_name}`}>
              {r.met ? <Check /> : <Cross />}
              <span>{reqLabel(r)}</span>
              {!r.met && <small>{r.your_level ? `need ${r.min_level_name}` : 'missing'}</small>}
            </li>
          ))}
        </ul>

        {bonus.length > 0 && (
          <p className="bonus tiny">
            <span className="muted">Bonus: </span>
            {bonus.slice(0, 3).join(', ')}
            {bonus.length > 3 && <span className="muted"> +{bonus.length - 3} more</span>}
          </p>
        )}

        <button className="more" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? 'Hide details' : tone === 'apply' ? 'Details' : 'Why & how to get there'}
        </button>

        {open && (
          <div className="details">
            <p className="muted">{match.description}</p>
            {showReasons && (
              <div className="why">
                <h5>{tone === 'skip' ? 'Why not now' : 'What is in the way'}</h5>
                <ul>{match.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
              </div>
            )}
            {match.upskill.length > 0 && (
              <div className="plan">
                <h5>How to get there</h5>
                <ul>{match.upskill.map((r) => <li key={r}>{r}</li>)}</ul>
              </div>
            )}
            {bonus.length > 3 && <p className="tiny"><span className="muted">All bonus skills: </span>{bonus.join(', ')}</p>}
            <p className="tiny muted">
              Score = 60% must-haves ({b.must_have}) + 25% bonus skills ({b.good_to_have}) + 15% text similarity ({b.text_similarity})
            </p>
          </div>
        )}
      </div>
    </article>
  )
}
