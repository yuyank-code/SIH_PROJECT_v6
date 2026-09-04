import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useEffect } from "react";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import MapPage from "@/pages/MapPage";
import Zones from "@/pages/Zones";
import ZoneDetail from "@/pages/ZoneDetail";
import Sensors from "@/pages/Sensors";
import Reports from "@/pages/Reports";
import Alerts from "@/pages/Alerts";
import Response from "@/pages/Response";
import Shelters from "@/pages/Shelters";
import OpsBoard from "@/pages/OpsBoard";
import Recovery from "@/pages/Recovery";
import ModelCard from "@/pages/ModelCard";
import Analytics from "@/pages/Analytics";
import Public from "@/pages/Public";
import Safety from "@/pages/Safety";
import Report from "@/pages/Report";
import FieldOfficer from "@/pages/FieldOfficer";
import Recipients from "@/pages/Recipients";
import AuthGate from "@/components/AuthGate";
import { supabase } from "@/lib/supabaseClient";
import { registerWebPush } from "@/lib/push";

const OPS = ["ADMIN", "AUTHORITY", "FIELD_OFFICER"];
const FIELD = ["ADMIN", "AUTHORITY", "FIELD_OFFICER"];
const op = (element) => <AuthGate roles={OPS}>{element}</AuthGate>;
const field = (element) => <AuthGate roles={FIELD}>{element}</AuthGate>;

export default function App() {
    useEffect(() => {
        let active = true;
        const setup = async () => {
            const { data } = await supabase.auth.getSession();
            if (active && data.session) registerWebPush().catch(() => {});
        };
        setup();
        const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => { if (session) registerWebPush().catch(() => {}); });
        return () => { active = false; listener.subscription.unsubscribe(); };
    }, []);

    return <BrowserRouter><Routes>
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={op(<Dashboard />)} />
        <Route path="/map" element={op(<MapPage />)} />
        <Route path="/zones" element={op(<Zones />)} />
        <Route path="/zones/:id" element={op(<ZoneDetail />)} />
        <Route path="/sensors" element={op(<Sensors />)} />
        <Route path="/reports" element={op(<Reports />)} />
        <Route path="/alerts" element={op(<Alerts />)} />
        <Route path="/response" element={op(<Response />)} />
        <Route path="/shelters" element={op(<Shelters />)} />
        <Route path="/ops" element={op(<OpsBoard />)} />
        <Route path="/recovery" element={op(<Recovery />)} />
        <Route path="/model" element={op(<ModelCard />)} />
        <Route path="/analytics" element={op(<Analytics />)} />
        <Route path="/recipients" element={<AuthGate roles={["ADMIN", "AUTHORITY"]}><Recipients /></AuthGate>} />
        <Route path="/public" element={<Public />} />
        {/* Shelter directions are deliberately unauthenticated — a person deciding
            where to run must never meet a login wall. */}
        <Route path="/safety" element={<Safety />} />
        {/* Reporting needs an identity (storage path + distinct-reporter counting),
            but no ops role: an empty roles array admits any signed-in profile,
            CITIZEN included. Report.jsx renders its own sign-in prompt. */}
        <Route path="/report" element={<Report />} />
        <Route path="/field" element={field(<FieldOfficer />)} />
        <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes></BrowserRouter>;
}
