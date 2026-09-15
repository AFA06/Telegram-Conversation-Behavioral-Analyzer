import { Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Overview from "./pages/Overview";
import Activity from "./pages/Activity";
import ResponseTimes from "./pages/ResponseTimes";
import Conversations from "./pages/Conversations";
import Calendar from "./pages/Calendar";
import Trends from "./pages/Trends";
import DataExplorer from "./pages/DataExplorer";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/responses" element={<ResponseTimes />} />
          <Route path="/conversations" element={<Conversations />} />
          <Route path="/calendar" element={<Calendar />} />
          <Route path="/trends" element={<Trends />} />
          <Route path="/explorer" element={<DataExplorer />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
