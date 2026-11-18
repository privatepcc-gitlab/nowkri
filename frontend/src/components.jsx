import { useState } from 'react'

const LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Expert']

/* Four-step track: filled = your level, ring = level the role needs */
export function LevelTrack({ have, need, label }) {
  return (
    <span className="track" role="img"
          aria-label={`${label}: you ${LEVELS[have - 1] || 'not found'}${need ? `, needs ${LEVELS[need - 1]}` : ''}`}>
      {[1, 2, 3, 4].map((i) => (
        <span key={i}
              className={`step ${i <= have ? 'have' : ''} ${need === i ? 'need' : ''} ${need && i <= need && i > have ? 'gap' : ''}`} />
      ))}
    </span>
  )
}

export function Profile({ profile, source }) {
  const yrs = profile.experience_years
  const months = Math.round(yrs * 12)
  const expLabel = !yrs ? 'Fresher'
    : yrs < 1 ? `${months} month${months === 1 ? '' : 's'}`
    : `${yrs} year${yrs === 1 ? '' : 's'}`
  const sections = profile.sections_found.join(', ')
  return (
    <div className="panel profile">
      <h2>{profile.name || source}</h2>
      {profile.education && <p className="muted">{profile.education}</p>}
      <dl>
        <div>
          <dt>Experience</dt>
          <dd>{expLabel}</dd>
        </div>
        <div>
          <dt>Read from</dt>
          <dd>{sections.charAt(0).toUpperCase() + sections.slice(1)}</dd>
        </div>
      </dl>
      <p className="tiny muted">{profile.experience_source}</p>
    </div>
  )
}

export function SkillList({ skills }) {
  const groups = {}
  skills.forEach((s) => { (groups[s.category] ||= []).push(s) })
  return (
    <div className="panel">
      <h3>Your skills ({skills.length})</h3>
      <p className="tiny muted">Level comes from where a skill shows up: listed only, used in projects, used at work.</p>
      {Object.entries(groups).map(([cat, list]) => (
        <div key={cat} className="skill-group">
          <h4>{cat}</h4>
          <ul>
            {list.map((s) => (
              <li key={s.name} title={s.reasons.join('; ')}>
                <span className="skill-name">{s.name}</span>
                <LevelTrack have={s.level} label={s.name} />
                <span className="skill-level">{s.level_name}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

export function RoleCard({ match, tone }) {
  const [open, setOpen] = useState(tone !== 'skip')
  const b = match.breakdown
  return (
    <article className={`role tone-${tone}`}>
      <button className="role-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="role-title">
          <span>{match.title}</span>
          <span className="muted role-family">{match.family}{match.min_years ? `, ${match.min_years}+ yrs` : ''}</span>
        </span>
        <span className="score"><b>{Math.round(match.score)}</b><small>% match</small></span>
      </button>

      {open && (
        <div className="role-body">
          <p className="muted">{match.description}</p>

          <table className="reqs">
            <caption>Must-have skills</caption>
            <tbody>
              {match.requirements.map((r) => (
                <tr key={r.requirement} className={r.met ? 'met' : 'unmet'}>
                  <td>
                    {r.requirement}
                    {r.your_skill && r.requirement.includes('/') && <span className="muted"> (you: {r.your_skill})</span>}
                  </td>
                  <td><LevelTrack have={r.your_level} need={r.min_level} label={r.requirement} /></td>
                  <td className="req-state">
                    {r.met ? 'Met' : r.your_level ? `${r.your_level_name}, need ${r.min_level_name}` : `Missing, need ${r.min_level_name}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {match.matched_good_to_have.length > 0 && (
            <p className="tags"><span className="muted">Bonus skills you have: </span>
              {match.matched_good_to_have.join(', ')}</p>
          )}

          {tone !== 'apply' && match.reasons.length > 0 && (
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

          <p className="breakdown tiny muted">
            Score = 60% must-haves ({b.must_have}) + 25% bonus skills ({b.good_to_have}) + 15% text similarity ({b.text_similarity})
          </p>
        </div>
      )}
    </article>
  )
}
