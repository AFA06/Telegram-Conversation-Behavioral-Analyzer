import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/activity", label: "Activity" },
  { to: "/responses", label: "Response Times" },
  { to: "/conversations", label: "Conversations" },
  { to: "/calendar", label: "Calendar" },
  { to: "/trends", label: "Trends" },
  { to: "/explorer", label: "Data Explorer" },
  { to: "/settings", label: "Settings" },
];

export default function Sidebar() {
  return (
    <nav className="sidebar">
      <div className="sidebar-brand">
        Conversation Analyzer
        <small>Local-first · your data stays on this device</small>
      </div>
      {LINKS.map((l) => (
        <NavLink key={l.to} to={l.to} end={l.end} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
          {l.label}
        </NavLink>
      ))}
      <div className="sidebar-footer">
        Historical patterns only.
        <br />
        Not a claim about intent or availability.
      </div>
    </nav>
  );
}
