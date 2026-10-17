export interface ShellRow {
  shell_km: number
  DEB: number
  PAY: number
  'R/B': number
  UNK: number
}

export interface ShellFile {
  source: string
  shells: ShellRow[]
}

export const SUGGEST_MIN_KM = 350
export const SUGGEST_MAX_KM = 1200

export function shellTotal(row: ShellRow) {
  return (row.PAY ?? 0) + (row.DEB ?? 0) + (row['R/B'] ?? 0) + (row.UNK ?? 0)
}

export function shellBounds(altitudeKm: number) {
  const min = Math.floor(altitudeKm / 50) * 50
  return { min, max: min + 50 }
}

export function shellForAltitude(shells: ShellRow[], altitudeKm: number) {
  const { min } = shellBounds(altitudeKm)
  return shells.find((row) => row.shell_km === min) ?? null
}

export function busiestShell(shells: ShellRow[]) {
  return shells.reduce<ShellRow | null>((best, row) => {
    if (!best || shellTotal(row) > shellTotal(best)) return row
    return best
  }, null)
}

export function quieterShell(shells: ShellRow[], current: ShellRow | null) {
  const band = shells.filter((row) => row.shell_km >= SUGGEST_MIN_KM && row.shell_km <= SUGGEST_MAX_KM)
  const best = band.reduce<ShellRow | null>((quiet, row) => {
    if (!quiet || shellTotal(row) < shellTotal(quiet)) return row
    return quiet
  }, null)
  if (!best || (current && current.shell_km === best.shell_km)) return null
  return best
}

export function majorityLabel(row: ShellRow) {
  const kinds = [
    ['payloads', row.PAY ?? 0],
    ['debris', row.DEB ?? 0],
    ['rocket bodies', row['R/B'] ?? 0],
    ['unidentified', row.UNK ?? 0],
  ] as const
  let label: string = kinds[0][0]
  let count = -1
  for (const [name, value] of kinds) {
    if (value > count) {
      label = name
      count = value
    }
  }
  const total = shellTotal(row)
  if (total === 0) return 'Empty in the catalog'
  if (count / total >= 0.5) return `Mostly ${label}`
  return 'Mixed'
}

export function shellRange(row: ShellRow) {
  return `${row.shell_km.toLocaleString('en-US')}–${(row.shell_km + 50).toLocaleString('en-US')} km`
}
