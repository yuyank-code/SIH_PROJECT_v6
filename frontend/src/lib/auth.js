import { useEffect, useState } from "react";
import { supabase } from "./supabaseClient";

export function useSupabaseSession() {
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        let mounted = true;
        supabase.auth.getSession().then(({ data }) => { if (mounted) { setSession(data.session); setLoading(false); } });
        const { data: listener } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
        return () => { mounted = false; listener.subscription.unsubscribe(); };
    }, []);
    return { session, user: session?.user || null, loading };
}
