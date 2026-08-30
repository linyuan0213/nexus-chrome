/** 实例 display（":1" 字符串或数字）→ noVNC URL。 */

/** ":1" / 1 / null → 1 / 1 / null */
export function displayNumber(display: string | number | null | undefined): number | null {
  if (display === null || display === undefined || display === '') return null;
  const n = parseInt(String(display).replace(/^:/, ''), 10);
  return Number.isNaN(n) ? null : n;
}

export function vncUrl(display: string | number | null | undefined, password?: string): string {
  const n = displayNumber(display);
  if (n === null) return '';
  const params = new URLSearchParams({ autoconnect: 'true', resize: 'scale' });
  if (password) params.set('password', password);
  return `/chrome${n}/vnc.html?${params.toString()}`;
}

export function vncPageUrl(display: string | number | null | undefined): string {
  const n = displayNumber(display);
  return n === null ? '' : `/chrome${n}/`;
}
