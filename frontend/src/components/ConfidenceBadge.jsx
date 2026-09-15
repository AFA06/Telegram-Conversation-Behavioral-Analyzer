export default function ConfidenceBadge({ level }) {
  if (!level) return null;
  const slug = level.toLowerCase().replace(" ", "-");
  return <span className={`badge ${slug}`}>{level} confidence</span>;
}
