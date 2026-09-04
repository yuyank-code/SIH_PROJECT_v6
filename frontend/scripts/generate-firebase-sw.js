const fs = require("fs");
const path = require("path");

const required = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.REACT_APP_FIREBASE_APP_ID,
};

const missing = Object.entries(required).filter(([, value]) => !value).map(([key]) => key);
const out = path.join(__dirname, "..", "public", "firebase-messaging-sw.js");

if (missing.length) {
  fs.writeFileSync(out, "// Firebase Messaging is disabled until all REACT_APP_FIREBASE_* values are configured.\n");
  console.warn(`Firebase messaging service worker disabled; missing: ${missing.join(", ")}`);
  process.exit(0);
}

const config = JSON.stringify(required, null, 2);
const content = `/* Generated at build time. Do not edit manually. */
importScripts("https://www.gstatic.com/firebasejs/10.13.2/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.13.2/firebase-messaging-compat.js");

firebase.initializeApp(${config});
const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  const title = payload.notification?.title || "NER-SLIDE Alert";
  const options = {
    body: payload.notification?.body || "New landslide risk alert",
    data: payload.data || {},
    icon: "/logo192.png",
  };
  self.registration.showNotification(title, options);
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    if (windows.length) return windows[0].focus();
    return clients.openWindow("/");
  }));
});
`;
fs.writeFileSync(out, content);
console.log("Generated public/firebase-messaging-sw.js");
