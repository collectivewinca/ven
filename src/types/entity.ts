export interface Entity {
  id: string;
  name: string;
  category: EntityCategory;
  mentionScore: number;
  bio: string;
  website: string;
  socialLinks: string[];
  contactEmail: string;
  genreTags: string[];
  location: string;
  notes: string;
  enriched: boolean;
  enrichedAt: string;
}

export type EntityCategory =
  | 'artists'
  | 'bands'
  | 'venues'
  | 'festivals'
  | 'labels'
  | 'producers'
  | 'music_orgs';

export const CATEGORY_META: Record<EntityCategory, { label: string; icon: string; color: string }> = {
  artists: { label: 'Artists', icon: 'mic', color: 'from-pink-500 to-rose-500' },
  bands: { label: 'Bands', icon: 'music', color: 'from-violet-600 to-indigo-600' },
  venues: { label: 'Venues', icon: 'map-pin', color: 'from-emerald-500 to-teal-500' },
  festivals: { label: 'Festivals', icon: 'sparkles', color: 'from-amber-500 to-orange-500' },
  labels: { label: 'Labels', icon: 'disc', color: 'from-cyan-500 to-blue-500' },
  producers: { label: 'Producers', icon: 'sliders', color: 'from-red-500 to-orange-500' },
  music_orgs: { label: 'Organizations', icon: 'building', color: 'from-slate-500 to-gray-600' },
};
