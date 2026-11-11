/**
 * 日期小工具：本地时区的今天（YYYY-MM-DD）与中文短显示。
 */

export function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** 2026-11-04 → 11月4日（同年省略年份） */
export function formatDateCn(iso: string): string {
  const parts = iso.split('-');
  if (parts.length !== 3) return iso;
  const month = Number(parts[1]);
  const day = Number(parts[2]);
  const thisYear = new Date().getFullYear();
  return parts[0] === String(thisYear) ? `${month}月${day}日` : `${parts[0]}年${month}月${day}日`;
}
