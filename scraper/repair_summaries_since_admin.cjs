#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.resolve(__dirname, '..');
const FIREBASE_MODULE_DIR = 'D:\\Modules\\firebase-cli';
const FIREBASE_ADMIN = require(path.join(FIREBASE_MODULE_DIR, 'node_modules', 'firebase-admin'));
const SERVICE_ACCOUNT = require(path.join(FIREBASE_MODULE_DIR, 'firebase-admin-key.json'));

const PROJECT_ID = process.env.FIREBASE_PROJECT_ID || process.env.VITE_FIREBASE_PROJECT_ID || 'miny-ven';
const CUTOFF = '2026-03-21T00:00:00';
const DEFAULT_LIMIT = 10;
const NVIDIA_CHAT_URL = process.env.NVIDIA_CHAT_URL || 'https://integrate.api.nvidia.com/v1/chat/completions';
const NVIDIA_CHAT_MODELS = (
  process.env.NVIDIA_CHAT_MODELS ||
  process.env.NVIDIA_CHAT_MODEL ||
  'stepfun-ai/step-3.5-flash,z-ai/glm5,moonshotai/kimi-k2.5,minimaxai/minimax-m2.5'
)
  .split(',')
  .map((model) => model.trim())
  .filter(Boolean);
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-3-flash-preview';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  for (const rawLine of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#') || !line.includes('=')) continue;
    const idx = line.indexOf('=');
    const key = line.slice(0, idx).trim();
    let value = line.slice(idx + 1).trim();
    value = value.replace(/^['"]|['"]$/g, '');
    if (!(key in process.env)) process.env[key] = value;
  }
}

loadEnvFile(path.join(ROOT_DIR, '.env'));
loadEnvFile(path.join(__dirname, '.env'));

const NVIDIA_API_KEY = process.env.NVIDIA_API_KEY || '';
function loadGeminiFallbackKey() {
  const refreshScript = path.join(__dirname, 'refresh_latest.py');
  if (!fs.existsSync(refreshScript)) return '';
  const match = fs.readFileSync(refreshScript, 'utf8').match(/GEMINI_API_KEY\s*=\s*["']([^"']+)["']/);
  return match ? match[1] : '';
}

const GEMINI_API_KEY = process.env.GEMINI_API_KEY || loadGeminiFallbackKey();

if (!FIREBASE_ADMIN.apps.length) {
  FIREBASE_ADMIN.initializeApp({
    credential: FIREBASE_ADMIN.credential.cert(SERVICE_ACCOUNT),
    projectId: PROJECT_ID,
  });
}

const db = FIREBASE_ADMIN.firestore();

function parseArgs(argv) {
  const args = { limit: DEFAULT_LIMIT, commit: false, dirtyOnly: true };
  for (const arg of argv.slice(2)) {
    if (arg.startsWith('--limit=')) args.limit = Number(arg.split('=')[1]) || DEFAULT_LIMIT;
    if (arg === '--commit') args.commit = true;
    if (arg === '--all') args.dirtyOnly = false;
  }
  return args;
}

function cleanText(text) {
  if (!text) return '';
  return text
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/<[a-z!/][^>]*$/gi, ' ')
    .replace(/<[a-z!/][^>]*\s/gi, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&quot;/gi, '"')
    .replace(/&apos;/gi, "'")
    .replace(/&#8217;/g, "'")
    .replace(/&#8216;/g, "'")
    .replace(/&#8220;/g, '"')
    .replace(/&#8221;/g, '"')
    .replace(/&#8230;/g, '...')
    .replace(/&#(\d+);/g, (_, code) => {
      const value = Number(code);
      return Number.isFinite(value) ? String.fromCodePoint(value) : ' ';
    })
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => {
      const value = parseInt(code, 16);
      return Number.isFinite(value) ? String.fromCodePoint(value) : ' ';
    })
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/https?:\/\/\S+/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function isRefusalLike(text) {
  if (!text) return true;
  return /(?:let me|i need to|i(?:'|’)m going to|key facts|analyze the|write a 60-word|summary about this|bullet points)/i.test(text);
}

function isNoisyContent(text) {
  if (!text) return true;
  return /skip to main content|open navigation menu|newsletter search|cookie policy|advertisement/i.test(text);
}

function looksDirtySummary(text) {
  if (!text) return false;
  return /<!--|<[^>]+>|&#\d+;|&#x[0-9a-f]+;|&nbsp;|&amp;|pmc-paywall|pmc-not-a-paywall/i.test(text);
}

function buildFallbackSummary(title, content, existingSummary) {
  const cleanedExisting = cleanText(existingSummary);
  if (cleanedExisting && !isRefusalLike(cleanedExisting) && cleanedExisting.split(/\s+/).filter(Boolean).length >= 12) {
    return cleanedExisting;
  }

  const cleanedContent = cleanText(content);
  const sentenceBits = cleanedContent
    .split(/(?<=[.!?])\s+/)
    .map((part) => part.trim())
    .filter(Boolean);

  let draft = '';
  for (const bit of sentenceBits) {
    const candidate = draft ? `${draft} ${bit}` : bit;
    if (candidate.split(/\s+/).filter(Boolean).length > 60) break;
    draft = candidate;
    if (draft.split(/\s+/).filter(Boolean).length >= 40) break;
  }

  if (!draft) {
    draft = cleanedContent.split(/\s+/).filter(Boolean).slice(0, 60).join(' ');
  }

  return (draft || title).replace(/\s+/g, ' ').trim();
}

async function fetchArticleText(url) {
  if (!url) return '';
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; miny-ven-bot/1.0)' },
      signal: AbortSignal.timeout(20000),
    });
    if (!resp.ok) return '';
    const html = await resp.text();
    return cleanText(html).slice(0, 2500);
  } catch {
    return '';
  }
}

async function generateTextResponse(prompt, systemPrompt, temperature, maxTokens) {
  if (NVIDIA_API_KEY) {
    for (const model of NVIDIA_CHAT_MODELS) {
      for (let attempt = 0; attempt < 1; attempt += 1) {
        const resp = await fetch(NVIDIA_CHAT_URL, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${NVIDIA_API_KEY}`,
            'Content-Type': 'application/json',
          },
          signal: AbortSignal.timeout(30000),
          body: JSON.stringify({
            model,
            messages: [
              { role: 'system', content: systemPrompt },
              { role: 'user', content: prompt },
            ],
            temperature,
            max_tokens: maxTokens,
          }),
        });

        if (resp.ok) {
          const data = await resp.json();
          const text = data?.choices?.[0]?.message?.content?.trim() || '';
          if (text) return text;
        } else if (resp.status === 429) {
          await sleep(750);
          break;
        } else if (!GEMINI_API_KEY) {
          throw new Error(`NVIDIA ${model} error ${resp.status}`);
        } else {
          break;
        }
      }
    }

    if (!GEMINI_API_KEY) {
      throw new Error(`NVIDIA models exhausted: ${NVIDIA_CHAT_MODELS.join(', ')}`);
    }
  }

  if (!GEMINI_API_KEY) {
    throw new Error('No NVIDIA_API_KEY or GEMINI_API_KEY configured');
  }

  const resp = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`, {
    method: 'POST',
    headers: {
      'x-goog-api-key': GEMINI_API_KEY,
      'Content-Type': 'application/json',
    },
    signal: AbortSignal.timeout(30000),
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      systemInstruction: { parts: [{ text: systemPrompt }] },
      generationConfig: {
        maxOutputTokens: Math.min(maxTokens * 4, 4096),
        temperature,
      },
    }),
  });

  if (!resp.ok) throw new Error(`Gemini error ${resp.status}`);
  const data = await resp.json();
  return data?.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || '';
}

async function summarize(title, content, existingSummary) {
  const cleanedContent = cleanText(content);
  const prompt = `Write a 60-word music news summary. Count every word carefully - it must be between 55 and 65 words.

Title: ${title}

Article: ${cleanedContent.slice(0, 2000)}

Rules:
- MUST be 55-65 words
- Include the artist name, the news development, and why it matters
- Punchy music-journalist tone
- Do NOT start with "Summary:" or the title
- Do NOT mention the task, your process, "let me", "I need to", or bullet points
- Return only the summary`;

  let summary = '';
  try {
    summary = await generateTextResponse(
      prompt,
      'You are a professional music journalist writing 60-word news briefs. Return only the summary text with no analysis, no preamble, and no bullet points.',
      0.5,
      220
    );
  } catch {
    return buildFallbackSummary(title, cleanedContent, existingSummary);
  }

  if (isRefusalLike(summary)) {
    try {
      summary = await generateTextResponse(
        `${prompt}\n\nReturn exactly one finished paragraph and nothing else.`,
        'Return only the final summary paragraph. Never describe your reasoning, process, or key points.',
        0.3,
        400
      );
    } catch {
      return buildFallbackSummary(title, cleanedContent, existingSummary);
    }
  }

  const cleanedSummary = cleanText(summary);
  const words = cleanedSummary.split(/\s+/).filter(Boolean);
  if (!cleanedSummary || isRefusalLike(cleanedSummary) || words.length < 25) {
    const expanded = await generateTextResponse(
      `${prompt}\n\nThe previous draft was too short or unusable. Rewrite it as one clean 55-65 word paragraph.`,
      'Return only a finished 55-65 word summary paragraph. No analysis. No bullet points.',
      0.4,
      200
    ).catch(() => '');
    const expandedClean = cleanText(expanded);
    const expandedWords = expandedClean.split(/\s+/).filter(Boolean);
    if (expandedClean && !isRefusalLike(expandedClean) && expandedWords.length >= 25) {
      return expandedWords.length > 70 ? `${expandedWords.slice(0, 70).join(' ')}.` : expandedClean;
    }

    return buildFallbackSummary(title, cleanedContent, existingSummary);
  }
  if (words.length > 70) return `${words.slice(0, 70).join(' ')}.`;
  return cleanedSummary;
}

async function main() {
  const { limit, commit, dirtyOnly } = parseArgs(process.argv);
  const snapshot = await db
    .collection('articles')
    .where('published_at', '>=', CUTOFF)
    .orderBy('published_at', 'desc')
    .limit(dirtyOnly ? Math.max(limit * 8, 80) : limit)
    .get();

  const docs = dirtyOnly
    ? snapshot.docs.filter((doc) => looksDirtySummary((doc.data() || {}).summary || '')).slice(0, limit)
    : snapshot.docs.slice(0, limit);

  console.log(`Matched ${docs.length} article(s) on or after ${CUTOFF}`);
  console.log(`Mode: ${commit ? 'commit' : 'dry-run'}`);
  console.log(`Dirty-only: ${dirtyOnly ? 'yes' : 'no'}`);
  console.log('');

  const results = [];

  for (const [index, doc] of docs.entries()) {
    const data = doc.data() || {};
    const title = data.title || '';
    const publishedAt = data.published_at || '';
    const sourceUrl = data.source_url || '';
    const existingSummary = data.summary || '';
    const existingContent = data.full_content || '';

    console.log(`[${index + 1}/${docs.length}] ${publishedAt.slice(0, 10)} ${title.slice(0, 95)}`);

    try {
      const fetchedContent = await fetchArticleText(sourceUrl);
      const storedContent = cleanText(existingContent);
      const fallbackContent = storedContent || cleanText(existingSummary) || title;
      const bestContent = fetchedContent && !isNoisyContent(fetchedContent) ? fetchedContent : fallbackContent;
      const newSummary = await summarize(title, bestContent, existingSummary);

      results.push({
        id: doc.id,
        title,
        oldSummary: cleanText(existingSummary).slice(0, 180),
        newSummary: newSummary.slice(0, 180),
      });

      if (commit) {
        await doc.ref.update({
          summary: newSummary,
          full_content: bestContent.slice(0, 4000),
        });
        console.log('   updated');
      } else {
        console.log('   prepared');
      }
    } catch (error) {
      console.log(`   failed: ${error.message}`);
      results.push({
        id: doc.id,
        title,
        oldSummary: cleanText(existingSummary).slice(0, 180),
        newSummary: `ERROR: ${error.message}`,
      });
    }
  }

  console.log('');
  console.log('Preview');
  for (const item of results) {
    console.log(`- ${item.id}`);
    console.log(`  old: ${item.oldSummary}`);
    console.log(`  new: ${item.newSummary}`);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
