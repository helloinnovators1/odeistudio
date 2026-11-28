"use strict";

const PRODUCTION_ORIGIN = "https://zurios.vercel.app";
const DEVELOPMENT_ORIGINS = new Set([
  "http://127.0.0.1:3002",
  "http://localhost:3002",
]);

function isTrustedAppUrl(value) {
  let url;
  try {
    url = new URL(String(value));
  } catch {
    return false;
  }
  if (url.username || url.password) return false;
  if (url.origin === PRODUCTION_ORIGIN) {
    return url.pathname === "/odeistudio" || url.pathname.startsWith("/odeistudio/");
  }
  return DEVELOPMENT_ORIGINS.has(url.origin);
}

module.exports = { isTrustedAppUrl };
