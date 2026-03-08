/**
 * useArtistEpk — fetches RapidConnect musician records and provides
 * lookup functions to resolve artist names → EPK URLs.
 *
 * Batch-fetches the musicians collection once, builds an in-memory
 * name→EPK index, then exposes:
 * - getEpkUrl(artistNames) for O(1) lookups by exact name
 * - findEpkInText(text) for scanning free text (title/summary) against the index
 */
import { useState, useEffect, useCallback, useRef } from 'react';

const RC_PROJECT_ID = 'subway-musician-564bd';
const RC_BASE = `https://firestore.googleapis.com/v1/projects/${RC_PROJECT_ID}/databases/(default)/documents/musicians`;

interface EpkEntry {
  name: string;
  identifier: string;
  shortenedLink?: string;
  epkUrl: string;
}

function getField(fields: Record<string, any>, key: string): string {
  const val = fields?.[key];
  if (!val) return '';
  return val.stringValue || val.integerValue || '';
}

function buildEpkUrl(identifier: string, shortenedLink?: string): string {
  if (shortenedLink) return shortenedLink;
  return `https://rapidconnect.minyvinyl.com/artists/${identifier}`;
}

export function useArtistEpk() {
  const indexRef = useRef<Map<string, EpkEntry>>(new Map());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function fetchMusicians() {
      try {
        const allDocs: any[] = [];
        let pageToken = '';

        while (true) {
          const params = new URLSearchParams();
          params.set('pageSize', '300');
          if (pageToken) params.set('pageToken', pageToken);
          ['name_lw', 'identifier', 'shortenedLink'].forEach(f =>
            params.append('mask.fieldPaths', f)
          );

          const resp = await fetch(`${RC_BASE}?${params}`);
          if (!resp.ok) break;
          const data = await resp.json();
          if (data.documents) allDocs.push(...data.documents);
          if (!data.nextPageToken) break;
          pageToken = data.nextPageToken;
        }

        if (cancelled) return;

        const nameIndex = new Map<string, EpkEntry>();
        for (const doc of allDocs) {
          const fields = doc.fields || {};
          const nameLw = getField(fields, 'name_lw');
          const identifier = getField(fields, 'identifier');
          if (!nameLw || !identifier) continue;

          const shortenedLink = getField(fields, 'shortenedLink') || undefined;
          const entry: EpkEntry = {
            name: nameLw,
            identifier,
            shortenedLink,
            epkUrl: buildEpkUrl(identifier, shortenedLink),
          };
          nameIndex.set(nameLw, entry);
        }

        indexRef.current = nameIndex;
        setReady(true);
      } catch (err) {
        console.warn('[useArtistEpk] Failed to fetch RC musicians:', err);
      }
    }

    fetchMusicians();
    return () => { cancelled = true; };
  }, []);

  const getEpkUrl = useCallback((artistNames: string[]): string | null => {
    if (!artistNames?.length) return null;
    const index = indexRef.current;
    for (const name of artistNames) {
      const entry = index.get(name.toLowerCase().trim());
      if (entry) return entry.epkUrl;
    }
    return null;
  }, []);

  /** Scan free text for any known artist name. Tries multi-word names first. */
  const findEpkInText = useCallback((text: string): string | null => {
    if (!text) return null;
    const index = indexRef.current;
    if (index.size === 0) return null;

    const textLw = text.toLowerCase();

    // Sort names longest-first so "Bad Bunny" matches before "Bad"
    const sortedNames = [...index.keys()].sort((a, b) => b.length - a.length);

    for (const name of sortedNames) {
      // Skip very short names (<=2 chars) to avoid false positives
      if (name.length <= 2) continue;
      // Word-boundary check: name must appear as a whole word/phrase
      const idx = textLw.indexOf(name);
      if (idx === -1) continue;
      const before = idx > 0 ? textLw[idx - 1] : ' ';
      const after = idx + name.length < textLw.length ? textLw[idx + name.length] : ' ';
      if (/\w/.test(before) || /\w/.test(after)) continue;
      return index.get(name)!.epkUrl;
    }
    return null;
  }, []);

  return { ready, getEpkUrl, findEpkInText };
}
