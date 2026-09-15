export default function RoleToggle({ value, onChange, options = ["me", "other", "both"], labels }) {
  const labelFor = (opt) => (labels && labels[opt]) || opt[0].toUpperCase() + opt.slice(1);
  return (
    <div className="role-toggle">
      {options.map((opt) => (
        <button key={opt} className={value === opt ? "active" : ""} onClick={() => onChange(opt)}>
          {labelFor(opt)}
        </button>
      ))}
    </div>
  );
}
