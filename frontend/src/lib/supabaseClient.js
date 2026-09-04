import { createClient } from '@supabase/supabase-js';

const url = process.env.REACT_APP_SUPABASE_URL;
// Support both the legacy frontend variable and Supabase's current publishable-key naming.
const anonKey = process.env.REACT_APP_SUPABASE_ANON_KEY || process.env.REACT_APP_SUPABASE_PUBLISHABLE_KEY;

if (!url || !anonKey) {
  // Keep local development explicit without exposing server credentials.
  console.error('Supabase frontend configuration is missing. Set REACT_APP_SUPABASE_URL and REACT_APP_SUPABASE_ANON_KEY (or REACT_APP_SUPABASE_PUBLISHABLE_KEY) in Render.');
}

export const supabase = createClient(url || 'https://invalid.local', anonKey || 'invalid-anon-key', {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
