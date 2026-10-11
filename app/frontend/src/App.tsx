import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { LiveBadge } from "./components/LiveBadge";
import { AnalysisPage } from "./pages/AnalysisPage";
import { CapturesPage } from "./pages/CapturesPage";
import { ProtocolsPage } from "./pages/ProtocolsPage";

export function App() {
  const protocols = useQuery({ queryKey: ["protocols"], queryFn: api.protocols, refetchInterval: 10_000 });
  const broken = (protocols.data ?? []).filter((p) => p.errors.length);

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">Analyseur de frames</Link>
        <nav>
          <NavLink to="/" end>Captures</NavLink>
          <NavLink to="/protocols">Protocoles</NavLink>
        </nav>
        {broken.length ? (
          <Link to={`/protocols?p=${broken[0].name ?? ""}`} className="yaml-alert">
            {broken.length === 1 ? `${broken[0].file} contient une erreur` : `${broken.length} fichiers YAML en erreur`}
          </Link>
        ) : null}
        <span className="topbar-spacer" />
        <LiveBadge />
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CapturesPage />} />
          <Route path="/captures/:id" element={<AnalysisPage />} />
          <Route path="/protocols" element={<ProtocolsPage />} />
          <Route path="*" element={<p className="page-note">Page introuvable. <Link to="/">Retour aux captures</Link></p>} />
        </Routes>
      </main>
    </div>
  );
}
