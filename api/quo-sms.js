export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const quoApiUrl = (process.env.QUO_API_URL || 'https://api.openphone.com/v1/messages').trim();
  const quoApiKey = (process.env.QUO_API_KEY || '').trim();
  const quoApiKeyHeader = (process.env.QUO_API_KEY_HEADER || 'Authorization').trim();
  const quoAuthScheme = (process.env.QUO_AUTH_SCHEME || 'raw').trim().toLowerCase();
  const quoFrom = (process.env.QUO_FROM || '').trim();

  if (!quoApiUrl || !quoApiKey) {
    return res.status(500).json({
      error: 'Missing Quo API configuration. Set QUO_API_URL and QUO_API_KEY.',
    });
  }

  const { to, text, articleTitle, articleUrl } = req.body || {};
  if (!to || !text) {
    return res.status(400).json({ error: 'Both "to" and "text" are required.' });
  }
  if (!quoFrom) {
    return res.status(500).json({
      error: 'Missing QUO_FROM. Set your Quo sender number or phone number ID in server env.',
    });
  }

  const headers = {
    'Content-Type': 'application/json',
  };

  if (quoApiKeyHeader.toLowerCase() === 'authorization') {
    headers.Authorization =
      quoAuthScheme === 'bearer' ? `Bearer ${quoApiKey}` : quoApiKey;
  } else {
    headers[quoApiKeyHeader] = quoApiKey;
  }

  const toList = Array.isArray(to) ? to : [to];
  const payload = {
    to: toList,
    from: quoFrom,
    content: text,
    metadata: {
      source: 'miny-ven',
      articleTitle: articleTitle || '',
      articleUrl: articleUrl || '',
    },
  };

  try {
    const quoResponse = await fetch(quoApiUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    const raw = await quoResponse.text();
    let data = {};
    try {
      data = raw ? JSON.parse(raw) : {};
    } catch {
      data = { raw };
    }

    if (!quoResponse.ok) {
      return res.status(quoResponse.status).json({
        error: 'Quo API returned an error.',
        details: data,
      });
    }

    return res.status(200).json({
      ok: true,
      provider: 'quo',
      response: data,
    });
  } catch (error) {
    return res.status(500).json({
      error: 'Failed to reach Quo API.',
      details: error instanceof Error ? error.message : String(error),
    });
  }
}
