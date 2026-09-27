"use strict";

// Offline support for the home-screen app. index.html carries all peak and
// route data inline, so caching it plus its few static assets is enough for
// the whole table, search and route panels to work with no signal.
//
// Bump CACHE_VERSION when any PRECACHE file changes. When you bump a ?v= in
// index.html, bump the matching entry here in the same commit, or the
// precache entry never matches the request and that asset stays uncached.
const CACHE_VERSION = "v1";
const CACHE_NAME = `co14ers-${CACHE_VERSION}`;

const PRECACHE = [
  "./",
  "./manifest.json",
  "./favicon.svg?v=3",
  "./vendor/supabase.min.js",
  "./fonts/ibm-plex-mono-400-latin.woff2",
  "./fonts/ibm-plex-mono-500-latin.woff2",
];

// How long a navigation waits on the network before it shows the cached page.
// Long enough for a normal load, short enough that one bar of signal at a
// trailhead doesn't leave a blank screen. The network request keeps running
// after the cutoff and refreshes the cache for the next launch.
const NAV_TIMEOUT_MS = 3000;

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CACHE_NAME).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("co14ers-") && k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

const ROOT = new URL("./", self.registration.scope).href;

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  // Supabase, 14ers.com, Google Maps: never intercepted.
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // The app page. ?q= and #slug are client-side state, so every variant is
  // stored under the one root entry. reset.html is not handled: it only works
  // online (it completes an emailed reset link), so offline it should fail
  // the normal way rather than show a stale copy.
  if (req.mode === "navigate") {
    const path = url.origin + url.pathname;
    if (path !== ROOT && path !== ROOT + "index.html") return;
    e.respondWith(navigate(e));
    return;
  }

  // Static assets: cache-first. They are versioned by ?v= and CACHE_VERSION.
  e.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((r) => {
        if (r && r.ok) {
          const copy = r.clone();
          caches.open(CACHE_NAME).then((c) => c.put(req, copy));
        }
        return r;
      });
    })
  );
});

function navigate(e) {
  // no-cache: revalidate with the server (cheap ETag check) instead of taking
  // GitHub Pages' 10-minute HTTP cache, so a data deploy shows on next launch.
  const network = fetch(ROOT, { cache: "no-cache" }).then((r) => {
    if (r && r.ok) {
      const copy = r.clone();
      e.waitUntil(caches.open(CACHE_NAME).then((c) => c.put(ROOT, copy)));
    }
    return r;
  });
  e.waitUntil(network.catch(() => {}));

  const cached = caches.match(ROOT);
  const timeout = new Promise((resolve) => setTimeout(resolve, NAV_TIMEOUT_MS));

  return Promise.race([
    network,
    timeout.then(() => cached).then((c) => c || network),
  ]).catch(() => cached.then((c) => c || Response.error()));
}
