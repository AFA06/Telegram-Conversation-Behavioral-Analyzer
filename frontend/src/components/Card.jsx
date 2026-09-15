export default function Card({ title, note, children }) {
  return (
    <div className="card">
      {title && <h2>{title}</h2>}
      {children}
      {note && <div className="card-note">{note}</div>}
    </div>
  );
}
