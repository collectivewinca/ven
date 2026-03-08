# miny-ven Project Report (2026-03-08)

## Summary

This session focused on two related goals:

1. Remove stale "60s read" UI text from the featured article area.
2. Improve client refresh behavior so old users are more likely to receive the latest deployed app after updates.

The project already had an initial Article-to-EPK bridge in place before the final edits in this session. The work here validated that implementation, removed outdated fallback copy, and hardened the service worker strategy.

## Key Findings

### 1. Vercel and Production Status

- The active local Vercel-linked working copy is:
  - `/Users/aletviegas/Documents/claude26/miny-ven`
- The Vercel project is `miny-ven`.
- The custom production domain is:
  - `https://ven.minyvinyl.com`
- The site responded successfully during verification and rendered normally in a browser session.

### 2. EPK Architecture

Two Firebase projects are relevant:

- `miny-ven`
  - Stores article/news content in Firestore.
- `subway-musician-564bd`
  - Stores RapidConnect musician records in the `musicians` collection.

The intended article CTA path is:

- article data from `miny-ven`
- artist/EPK data from RapidConnect `musicians`
- destination URL:
  - prefer `shortenedLink` when present
  - otherwise use `https://rapidconnect.minyvinyl.com/artists/{identifier}`

### 3. Existing EPK Integration Confirmed

The repo already contained an earlier implementation of the Article-to-EPK bridge:

- `src/hooks/useArtistEpk.ts`
  - fetches RapidConnect musician records from `subway-musician-564bd`
  - builds an in-memory lookup index
  - resolves names to EPK URLs
- `src/App.tsx`
  - renders `Discover Artist` when a match exists
  - uses direct artist-name matching first
  - falls back to text scanning across title/summary

This means the major EPK integration work had already started before the final cleanup in this session.

## Changes Made

### 1. Removed stale read-time fallback

File changed:

- `src/App.tsx`

Change:

- Removed the featured article footer fallback that showed:
  - `60s read`
- The footer now only shows `Discover Artist` when a valid EPK match exists.
- If there is no RapidConnect match, that slot remains empty instead of showing irrelevant reading-time text.

Reason:

- `60s read` no longer reflects the current product direction.
- That UI space is now reserved for artist discovery and EPK navigation.

Git commit:

- `c99e647` — `chore: remove stale read time fallback`

### 2. Hardened service worker update behavior

File changed:

- `public/sw.js`

Change:

- bumped cache version from `miny-ven-v2` to `miny-ven-v3`
- removed precaching of `/index.html`
- added `self.skipWaiting()` during install
- added `activate` cleanup of old caches
- added `self.clients.claim()` during activate
- changed navigation requests to network-first with cache fallback

Reason:

- Old users could remain stuck on stale cached HTML.
- The prior service worker behavior was not suitable as a durable update strategy.
- The new behavior reduces stale-client risk and makes deployments propagate more reliably.

Git commit:

- `39aa7ea` — `fix: make service worker refresh clients`

## Verification

### Local verification

- `npm run build` succeeded after the `App.tsx` change.
- `npm run build` succeeded after the service worker change.

### Deployment verification

- Both changes were pushed to `origin/main`.
- Production verification URL:
  - `https://ven.minyvinyl.com`

## Current State

### Completed

- Production site checked and reachable.
- EPK bridge implementation confirmed in code.
- `60s read` fallback removed from featured article footer.
- Service worker improved so updates should reach users more reliably.
- Changes pushed to GitHub.

### Still true / not yet changed

- `readTime` still exists in the article data model and Firestore mapping.
- EPK matching is still heuristic:
  - article `artistNames` lookup first
  - title/summary text scan fallback second
- The UI does not yet provide a richer multi-artist selection flow.
- There is no explicit in-app "new version available" prompt yet.

## Open Questions

These questions remain relevant for future work:

1. For articles that mention multiple artists, should `Discover Artist`:
   - link to the first matched artist
   - open an artist chooser
   - or become `Discover Artists`

2. If no RapidConnect musician match exists, should the UI:
   - show nothing
   - show disabled text
   - or link to a generic landing page

3. Should the current text-scan fallback remain, or should all article-to-artist links require explicit structured matches only

4. Should `miny-ven` eventually add an in-app refresh prompt when a new service worker becomes active

## Recommended Next Steps

1. Verify on production that article cards with known artists display `Discover Artist` correctly.
2. Test an already-open browser tab to confirm the new service worker behavior is acceptable.
3. Add an optional "new version available" toast/banner for the strongest long-term refresh behavior.
4. Improve artist matching quality for articles with multiple or ambiguous artist names.
