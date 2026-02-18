# miny-ven — Cost Estimate & Recent Updates

## Architecture Overview

- **Frontend**: React + Vite + Tailwind CSS (SPA deployed on Vercel)
- **Backend**: Python scraper (GitHub Actions cron), Firestore REST API
- **Image Gen**: Gemini 2.5 Flash (free tier)
- **Storage**: Firestore documents with data URI images (no Firebase Storage — billing not enabled)
- **Domain**: `ven.minyvinyl.com`

## Monthly Cost Estimate (100 Daily Active Users)

| Service | Cost | Notes |
|---|---|---|
| Gemini 2.5 Flash | **$0** | Free tier (500 req/day, we use ~10/day) |
| Firestore reads | **~$0.36** | ~2.1M reads/mo after optimization (1.5M free) |
| Firestore storage | **~$0.70** | ~7.5GB at steady state (1GB free) |
| Firestore writes | **~$0** | ~600 writes/mo (negligible) |
| Vercel hosting | **$0** | Hobby plan, static SPA |
| GitHub Actions | **$0** | ~25 hrs/mo of 2,000 free minutes |
| **Total** | **~$1/mo** | |

### Cost Drivers

- **Firestore reads** are the main variable cost. Each page visit = 1 bulk metadata fetch (300 docs) + ~15 lazy image fetches (one per visible card).
- **Firestore storage** grows with article count. Each article with a Gemini image adds ~94KB (data URI). At ~300 new articles/month, storage grows ~28MB/month.
- **Gemini API** is free at current volume. Paid tier kicks in above 500 images/day ($0.10/1K input tokens + image output pricing).

### Before vs After Optimization

| Metric | Before | After |
|---|---|---|
| Firestore reads/mo | ~27M ($15.30) | ~2.1M ($0.36) |
| Initial page payload | ~25MB (all docs + images) | ~600KB (metadata only) |
| Image loading | All at once | Lazy per visible card |
| Service worker | Cache-first (stale data) | Network-first for API |
| Total monthly cost | ~$16 | ~$1 |

### Future Cost Reduction

If Firebase billing is enabled ($0 minimum on Blaze plan):
- Firebase Storage: ~$0.60/mo (images as URLs instead of data URIs)
- Firestore storage drops from $0.70 to ~$0.07 (docs shrink from 94KB to 2KB)
- Total would drop to ~$0.50/mo

## Recent Updates (2026-02-18)

### Image Generation: OpenAI → Gemini

Replaced OpenAI DALL-E with Gemini 2.5 Flash for AI image generation.

**Why**: DALL-E URLs expire after ~1 hour; Gemini is free tier with no expiry.

**How it works**:
1. Scraper generates image via Gemini REST API (`gemini-2.5-flash-image` model)
2. Response contains base64 PNG in `inlineData` field
3. Image compressed to 800px WebP (quality 70-80)
4. Stored as `data:image/webp;base64,...` directly in Firestore `image_url` field
5. Frontend renders data URIs natively in `<img>` tags

**Commits**:
- `a314be4` Replace OpenAI DALL-E image gen with Gemini 2.5 Flash
- `d08894d` Fix Gemini REST API: use camelCase keys
- `5b84508` Fix Firebase Storage bucket name
- `a3a7e40` Add data URI fallback when Firebase Storage unavailable
- `d2e532f` Bump data URI quality to 800px/q70

### Image Backfill Workflow

Added manual GitHub Actions workflow to generate images for existing articles.

- Workflow: `.github/workflows/backfill-images.yml`
- Trigger: `workflow_dispatch` with `limit` input (default 10)
- Sorts by most recent `fetched_at` first
- Respects `BACKFILL_LIMIT` env var

**Commit**: `aebeb07` Add backfill workflow with BACKFILL_LIMIT support

### Frontend Pagination Fix

Fixed frontend only loading 100 of 273+ articles (Firestore REST default).

- Added `pageSize=300` and pagination loop
- All articles now load (274 total)

**Commit**: `895fa4e` Fix article fetch: paginate all docs and network-first SW

### Firestore Read Optimization

Reduced Firestore reads and payload size by 97%.

**Field masks**: Bulk fetch excludes `image_url` (~92KB avg) and `full_content` using Firestore `mask.fieldPaths`. Initial payload: ~600KB instead of ~25MB.

**Lazy image loading**: New `LazyArticleImage` component fetches `image_url` per card on demand. In-memory cache prevents duplicate fetches. Skips fetch for articles with `image_source: "none"`.

**Network-first service worker**: API calls now bypass cache, preventing stale data. Static assets still use cache-first.

**Commit**: `4b05ccf` Optimize Firestore reads: field masks + lazy image loading

## GitHub Secrets Required

| Secret | Purpose |
|---|---|
| `FIREBASE_API_KEY` | Firestore REST API access |
| `FIREBASE_SERVICE_ACCOUNT_B64` | Firebase Admin SDK (Storage uploads) |
| `GEMINI_API_KEY` | Gemini image generation |
| `DEEPSEEK_API_KEY` | Article summarization |
| `PERPLEXITY_API_KEY` | CTA headline generation |
| `OPENROUTER_API_KEY` | Fallback LLM routing |
| `EXA_API_KEY` | Article discovery |

## Deployment

Vercel GitHub integration is disabled. Deploy manually:

```bash
cd miny-ven
npm run build
vercel deploy dist/ --prod --scope collective-win --yes
```
