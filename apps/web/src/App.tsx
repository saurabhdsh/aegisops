import { Navigate, Route, Routes } from "react-router-dom";
import { token } from "./lib/api";
import { Shell } from "./components/Shell";
import { Approvals } from "./pages/Approvals";
import { Audit } from "./pages/Audit";
import { Capacity } from "./pages/Capacity";
import { IncidentRecord } from "./pages/IncidentRecord";
import { Incidents } from "./pages/Incidents";
import { Login } from "./pages/Login";
import { Rca } from "./pages/Rca";
import { Runbooks } from "./pages/Runbooks";
import { Settings } from "./pages/Settings";
import { Topology } from "./pages/Topology";
import { Workflow } from "./pages/Workflow";

function Private() {
  if (!token()) return <Navigate to="/login" replace />;
  return <Shell />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Private />}>
        <Route path="/" element={<Navigate to="/incidents" replace />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/rca" element={<Rca />} />
        <Route path="/incidents/:incidentId" element={<IncidentRecord />} />
        <Route path="/workflows/:workflowId" element={<Workflow />} />
        <Route path="/approvals" element={<Approvals />} />
        <Route path="/capacity" element={<Capacity />} />
        <Route path="/topology" element={<Topology />} />
        <Route path="/runbooks" element={<Runbooks />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
