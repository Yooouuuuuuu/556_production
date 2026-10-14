// Dates and times the way the person reads them (設定 → 全域 → 程式): four date orders and a 24 h / 12 h clock.
export type TimeFormat = 'ymd' | 'iso' | 'dmy' | 'mdy';
export const TIME_FORMATS: TimeFormat[] = ['ymd', 'iso', 'dmy', 'mdy'];

const pad = (n: number) => String(n).padStart(2, '0');

export function fmtDate(ts: number, f: TimeFormat): string {
  const d = new Date(ts * 1000);
  const y = d.getFullYear(), m = pad(d.getMonth() + 1), day = pad(d.getDate());
  switch (f) {
    case 'iso': return `${y}-${m}-${day}`;
    case 'dmy': return `${day}/${m}/${y}`;
    case 'mdy': return `${m}/${day}/${y}`;
    default: return `${y}/${m}/${day}`;
  }
}

export function fmtTime(ts: number, clock24: boolean): string {
  const d = new Date(ts * 1000);
  const mm = pad(d.getMinutes());
  let h = d.getHours();
  if (clock24) return `${pad(h)}:${mm}`;
  const ap = h < 12 ? 'AM' : 'PM';
  h = h % 12 || 12;
  return `${h}:${mm} ${ap}`;
}

export function fmtDateTime(ts: number, f: TimeFormat, clock24: boolean): string {
  return `${fmtDate(ts, f)} ${fmtTime(ts, clock24)}`;
}

// local calendar day of a timestamp, as an integer (days since the epoch in local time)
export function dayIndex(ts: number): number {
  const d = new Date(ts * 1000);
  return Math.floor(new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() / 86400000);
}

export function dayLabel(ts: number, now: number, f: TimeFormat, labels: { today: string; yesterday: string }): string {
  const diff = dayIndex(now) - dayIndex(ts);
  if (diff === 0) return labels.today;
  if (diff === 1) return labels.yesterday;
  return fmtDate(ts, f);
}

// whole calendar days from ts to now (0 = same day)
export function daysSince(ts: number, now: number): number {
  return dayIndex(now) - dayIndex(ts);
}
