import type { ObjectFact, OrbitCounts } from './orbit.ts'

const TYPE_COLOR: Record<keyof OrbitCounts, string> = {
  satellite: '#C9D6E3',
  debris: '#F2A541',
  'rocket body': '#8C7AE6',
  unknown: '#8B97A6',
}

const CONSTELLATION: Record<string, string> = {
  starlink: 'Starlink',
  oneweb: 'OneWeb',
  kuiper: 'Kuiper',
  qianfan: 'Qianfan',
  guowang: 'Guowang',
  iridium: 'Iridium',
  globalstar: 'Globalstar',
  flock: 'Flock',
  lemur: 'Lemur',
}

const BREAKUP: Record<string, string> = {
  'fengyun-1c-debris': 'Fengyun-1C debris',
  'cosmos-2251-debris': 'Cosmos 2251 debris',
  'iridium-33-debris': 'Iridium 33 debris',
  'cosmos-1408-debris': 'Cosmos 1408 debris',
}

const GROUP: Record<string, string> = {
  stations: 'Station',
  cubesat: 'Cubesat',
  science: 'Science',
  military: 'Military',
  weather: 'Weather',
  education: 'Education',
  gnss: 'GNSS',
  planet: 'Planet',
  geo: 'GEO',
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function formatDay(day: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(day)
  if (!match) return day
  const month = MONTHS[Number(match[2]) - 1]
  if (!month) return day
  return `${Number(match[3])} ${month} ${match[1]}`
}

function formatKm(value: number) {
  return `${Math.round(value).toLocaleString('en-US')} km`
}

function identity(fact: ObjectFact) {
  if (fact.constellation) return CONSTELLATION[fact.constellation] ?? fact.constellation
  const breakup = BREAKUP[fact.sourceGroup]
  if (breakup) return breakup
  for (const group of fact.groups) {
    const label = GROUP[group]
    if (label) return label
  }
  return null
}

export default function ObjectCard({ fact, liveKm }: { fact: ObjectFact; liveKm: number | null }) {
  const who = identity(fact)
  const catalog =
    fact.perigee != null && fact.apogee != null ? `${formatKm(fact.perigee)} to ${formatKm(fact.apogee)}` : null
  const rows: { label: string; value: string }[] = []
  if (liveKm != null && Number.isFinite(liveKm)) rows.push({ label: 'Height now', value: formatKm(liveKm) })
  if (catalog) rows.push({ label: 'Catalog', value: catalog })
  if (fact.inclination != null) rows.push({ label: 'Inclination', value: `${fact.inclination.toFixed(1)}°` })
  if (fact.owner) rows.push({ label: 'Owner', value: fact.owner })
  if (fact.launch) rows.push({ label: 'Launched', value: formatDay(fact.launch) })
  if (fact.radar != null) rows.push({ label: 'Radar size', value: `${fact.radar.toFixed(fact.radar < 0.1 ? 3 : 2)} m²` })
  if (who) rows.push({ label: 'Group', value: who })

  return (
    <aside className="inspect">
      <p className="inspect-type" style={{ color: TYPE_COLOR[fact.type] }}>
        {fact.type === 'unknown' ? 'unidentified' : fact.type}
      </p>
      <h2>{fact.name}</h2>
      <p className="inspect-id">
        NORAD <span className="num">{fact.norad.toLocaleString('en-US')}</span>
      </p>
      <dl>
        {rows.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd className={row.label === 'Owner' || row.label === 'Group' ? undefined : 'num'}>{row.value}</dd>
          </div>
        ))}
      </dl>
      <p className="source">CelesTrak GP · SATCAT</p>
    </aside>
  )
}
