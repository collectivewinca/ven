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
import embeddedFallbackIndex from '../data/artistEpkIndex.json';

// RapidConnect migrated to PocketBase (sm_musicians on miny-database) in
// 2026-05; the old subway-musician-564bd Firestore is a stale April snapshot.
// Only quality-contract-passing records (content_status=published) are indexed.
const PB_BASE = 'https://miny-database.exe.xyz';
const PB_COLLECTION = 'sm_musicians';
const LOCAL_CACHE_KEY = 'miny-ven-artist-epk-index-v2';

interface EpkEntry {
  name: string;
  identifier: string;
  shortenedLink?: string;
  epkUrl: string;
}

interface SerializedEpkEntry {
  name?: string;
  name_lw?: string;
  identifier?: string;
  shortenedLink?: string;
  epkUrl?: string;
}

function normalizeName(value: string): string {
  return value
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ');
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

function setIndexEntries(index: Map<string, EpkEntry>, names: Array<string | undefined>, entry: EpkEntry) {
  names
    .map((value) => normalizeName(value || ''))
    .filter(Boolean)
    .forEach((value) => index.set(value, entry));
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function buildIndexFromSerialized(entries: SerializedEpkEntry[]): Map<string, EpkEntry> {
  const nameIndex = new Map<string, EpkEntry>();
  for (const item of entries) {
    const identifier = item.identifier || '';
    if (!identifier) continue;
    const shortenedLink = item.shortenedLink || undefined;
    const entry: EpkEntry = {
      name: item.name || item.name_lw || '',
      identifier,
      shortenedLink,
      epkUrl: item.epkUrl || buildEpkUrl(identifier, shortenedLink),
    };
    setIndexEntries(nameIndex, [item.name_lw, item.name], entry);
  }
  return nameIndex;
}

const embeddedIndex = buildIndexFromSerialized(embeddedFallbackIndex as SerializedEpkEntry[]);
const embeddedSortedNames = [...embeddedIndex.keys()].sort((a, b) => b.length - a.length);

function findMatchInIndex(index: Map<string, EpkEntry>, text: string, sortedNames?: string[]): string | null {
  if (!text || index.size === 0) return null;
  const textLw = normalizeName(text);
  const names = sortedNames || [...index.keys()].sort((a, b) => b.length - a.length);

  for (const name of names) {
    if (name.length <= 2) continue;
    const idx = textLw.indexOf(name);
    if (idx === -1) continue;
    const before = idx > 0 ? textLw[idx - 1] : ' ';
    const after = idx + name.length < textLw.length ? textLw[idx + name.length] : ' ';
    if (/[a-z0-9]/.test(before) || /[a-z0-9]/.test(after)) continue;
    const entry = index.get(name);
    if (!entry) continue;

    const tokenCount = normalizeName(entry.name).split(' ').filter(Boolean).length;
    if (tokenCount === 1) {
      const exactCasePattern = new RegExp(`(^|[^A-Za-z0-9])${escapeRegex(entry.name)}($|[^A-Za-z0-9])`);
      if (!exactCasePattern.test(text)) continue;
    }

    return entry.epkUrl;
  }

  return null;
}

export function useArtistEpk() {
  const indexRef = useRef<Map<string, EpkEntry>>(embeddedIndex);
  const [ready, setReady] = useState(indexRef.current.size > 0);

  useEffect(() => {
    let cancelled = false;

    async function hydrateCachedIndex() {
      try {
        const cached = localStorage.getItem(LOCAL_CACHE_KEY);
        if (!cached) return;
        const parsed = JSON.parse(cached) as SerializedEpkEntry[];
        const nameIndex = buildIndexFromSerialized(parsed);
        if (nameIndex.size === 0) return;
        indexRef.current = nameIndex;
        if (!cancelled) setReady(true);
      } catch (err) {
        console.warn('[useArtistEpk] Failed to read cached index:', err);
      }
    }

    async function refreshFromPocketBase() {
      try {
        const allRecords: any[] = [];
        let page = 1;

        while (true) {
          const params = new URLSearchParams();
          params.set('perPage', '500');
          params.set('page', String(page));
          params.set('filter', "content_status = 'published'");
          params.set('fields', 'id,identifier,name,name_lw,shortenedLink');

          const resp = await fetch(`${PB_BASE}/api/collections/${PB_COLLECTION}/records?${params}`);
          if (!resp.ok) break;
          const data = await resp.json();
          if (data.items) allRecords.push(...data.items);
          if (page >= Number(data.totalPages || 1) || !data.items?.length) break;
          page += 1;
        }

        if (cancelled) return;

        const nameIndex = new Map<string, EpkEntry>();
        for (const record of allRecords) {
          const nameLw = record.name_lw || '';
          const canonicalName = record.name || '';
          // The live site routes PB record ids (canonical, sitemap-consistent).
          const identifier = record.id || record.identifier || '';
          if (!identifier) continue;

          const shortenedLink = record.shortenedLink || undefined;
          const entry: EpkEntry = {
            name: canonicalName || nameLw,
            identifier,
            shortenedLink,
            epkUrl: buildEpkUrl(identifier, shortenedLink),
          };
          setIndexEntries(nameIndex, [nameLw, canonicalName], entry);
        }

        indexRef.current = nameIndex;
        localStorage.setItem(
          LOCAL_CACHE_KEY,
          JSON.stringify(
            [...nameIndex.values()].map((entry) => ({
              name: entry.name,
              identifier: entry.identifier,
              shortenedLink: entry.shortenedLink,
              epkUrl: entry.epkUrl,
            }))
          )
        );
        setReady(true);
      } catch (err) {
        console.warn('[useArtistEpk] Failed to fetch RC musicians:', err);
      }
    }

    hydrateCachedIndex().then(() => {
      refreshFromPocketBase();
    });
    return () => { cancelled = true; };
  }, []);

  const getEpkUrl = useCallback((artistNames: string[]): string | null => {
    if (!artistNames?.length) return null;
    const index = indexRef.current;
    for (const name of artistNames) {
      const key = normalizeName(name);
      const entry = index.get(key) || embeddedIndex.get(key);
      if (entry) return entry.epkUrl;
    }
    return null;
  }, []);

  /** Scan free text for any known artist name. Tries multi-word names first. */
  const findEpkInText = useCallback((text: string): string | null => {
    const index = indexRef.current;
    return findMatchInIndex(index, text) || findMatchInIndex(embeddedIndex, text, embeddedSortedNames);
  }, []);

  return { ready, getEpkUrl, findEpkInText };
}
