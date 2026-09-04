import axios from "axios";
import { supabase } from "./supabaseClient";

const rawBase = process.env.REACT_APP_API_BASE_URL || process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
export const API = rawBase.replace(/\/$/, "").replace(/\/api\/$/, "") + "/api";
export const api = axios.create({ baseURL: API, timeout: 30000 });

api.interceptors.request.use(async (config) => {
    const { data } = await supabase.auth.getSession();
    const token = data?.session?.access_token;
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

const normalizeEmail = (email) => String(email || "").trim().toLowerCase();

export const auth = {
    signIn: (email, password) => supabase.auth.signInWithPassword({ email: normalizeEmail(email), password }),
    signUp: (email, password, fullName = "") => supabase.auth.signUp({
        email: normalizeEmail(email),
        password,
        options: {
            data: { full_name: fullName },
            emailRedirectTo: window.location.origin,
        },
    }),
    signOut: () => supabase.auth.signOut(),
    session: () => supabase.auth.getSession(),
    user: () => supabase.auth.getUser(),
    profile: () => api.get("/me"),
    onChange: (callback) => supabase.auth.onAuthStateChange(callback),
};

export async function uploadReportMedia(file, userId, reportId) {
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, "_");
    const path = `${userId}/${reportId}/${crypto.randomUUID()}-${safeName}`;
    const { error } = await supabase.storage.from("report-media").upload(path, file, { contentType: file.type, upsert: false });
    if (error) throw error;
    await api.post(`/reports/${reportId}/media`, { storage_path: path, media_type: "PHOTO", mime_type: file.type, size_bytes: file.size });
    return path;
}

export async function uploadReportDataUrl(dataUrl, userId, reportId, fileName = "evidence.jpg") {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    const file = new File([blob], fileName, { type: blob.type || "image/jpeg" });
    return uploadReportMedia(file, userId, reportId);
}

export async function registerPushToken(fcmToken, platform = "WEB") {
    const { data, error } = await supabase.rpc("register_device", { p_fcm_token: fcmToken, p_platform: platform });
    if (error) throw error;
    return data;
}

export const SEVERITY_COLORS = { CRITICAL: "#e11d48", HIGH: "#ea580c", MEDIUM: "#d97706", LOW: "#059669", UNKNOWN: "#6b7280" };
export const severityClass = (s) => ({ CRITICAL: "sev-critical", HIGH: "sev-high", MEDIUM: "sev-medium", LOW: "sev-low" }[s] || "sev-unknown");
export const roleFromStorage = () => localStorage.getItem("ner_role") || "CITIZEN";
export const setRole = (r) => localStorage.setItem("ner_role", r);

const QKEY = "ner_offline_reports";
export const enqueueOffline = (r) => {
    const list = JSON.parse(localStorage.getItem(QKEY) || "[]");
    list.push({ ...r, client_uuid: r.client_uuid || crypto.randomUUID(), queued_at: new Date().toISOString() });
    localStorage.setItem(QKEY, JSON.stringify(list));
};
export const getOfflineQueue = () => JSON.parse(localStorage.getItem(QKEY) || "[]");
export const clearOfflineItem = (id) => localStorage.setItem(QKEY, JSON.stringify(getOfflineQueue().filter((x) => x.client_uuid !== id)));
export const flushOffline = async () => {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return getOfflineQueue().length;
    for (const r of getOfflineQueue()) {
        try {
            const queued = { ...r };
            const photoData = queued.photo_data_url;
            delete queued.photo_data_url;
            const response = await api.post("/reports", queued);
            if (photoData && response.data?.id) await uploadReportDataUrl(photoData, user.id, response.data.id, queued.photo_file_name || "evidence.jpg");
            clearOfflineItem(r.client_uuid);
        } catch (e) { /* keep queued for the next connectivity event */ }
    }
    return getOfflineQueue().length;
};
