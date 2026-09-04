import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { auth } from "@/lib/api";

export default function AuthGate({ roles = [], children }) {
  const [state, setState] = useState({ loading: true, profile: null });
  useEffect(() => {
    let mounted = true;
    auth.profile().then(({ data }) => {
      if (mounted) setState({ loading: false, profile: data?.profile || null });
    }).catch(() => mounted && setState({ loading: false, profile: null }));
    return () => { mounted = false; };
  }, []);
  if (state.loading) return <div className="min-h-screen flex items-center justify-center font-mono text-xs text-[var(--text-2)]">AUTHENTICATING…</div>;
  if (!state.profile) return <Navigate to="/login" replace />;
  if (roles.length && !roles.includes(state.profile.role)) return <Navigate to={state.profile.role === "CITIZEN" ? "/public" : "/dashboard"} replace />;
  return children;
}
