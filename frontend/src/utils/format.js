export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "N/A";
  seconds = Math.round(seconds);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  const days = Math.floor(hours / 24);
  const hrs = hours % 24;

  const units = [];
  if (days) units.push(`${days}d`);
  if (hrs) units.push(`${hrs}h`);
  if (mins && !days) units.push(`${mins}m`);
  if (units.length === 0) units.push(`${secs}s`);
  return units.slice(0, 2).join(" ");
}

export function formatPercent(value) {
  if (value === null || value === undefined) return "N/A";
  return `${value}%`;
}

export const WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
