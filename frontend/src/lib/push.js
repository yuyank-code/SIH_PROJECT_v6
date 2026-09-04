import { registerPushToken } from "./api";

const FIREBASE_SCRIPTS = [
  "https://www.gstatic.com/firebasejs/10.13.2/firebase-app-compat.js",
  "https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-compat.js",
];

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`firebase_script_load_failed:${src}`));
    document.head.appendChild(script);
  });
}

export async function registerWebPush() {
  if (!("Notification" in window) || !("serviceWorker" in navigator)) return { enabled: false, reason: "unsupported" };
  const vapidKey = process.env.REACT_APP_FIREBASE_VAPID_KEY;
  const config = {
    apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
    authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
    projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
    storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
    messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
    appId: process.env.REACT_APP_FIREBASE_APP_ID,
  };
  if (!vapidKey || Object.values(config).some((v) => !v)) return { enabled: false, reason: "firebase_not_configured" };
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return { enabled: false, reason: "permission_denied" };
  for (const src of FIREBASE_SCRIPTS) await loadScript(src);
  if (!window.firebase) throw new Error("firebase_sdk_unavailable");
  const app = window.firebase.apps?.length ? window.firebase.app() : window.firebase.initializeApp(config);
  const messaging = window.firebase.messaging(app);
  const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");
  const token = await messaging.getToken({ vapidKey, serviceWorkerRegistration: registration });
  if (!token) return { enabled: false, reason: "token_unavailable" };
  await registerPushToken(token, "WEB");
  return { enabled: true, token };
}
