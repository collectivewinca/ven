export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const apiKey = (process.env.ELEVENLABS_API_KEY || '').trim();
  const configuredVoiceId = (process.env.ELEVENLABS_VOICE_ID || '').trim();
  const voiceName = (process.env.ELEVENLABS_VOICE_NAME || 'Alet V2').trim();
  const modelId = (process.env.ELEVENLABS_MODEL_ID || 'eleven_multilingual_v2').trim();

  if (!apiKey) {
    return res.status(500).json({
      error: 'Missing ElevenLabs API key. Set ELEVENLABS_API_KEY in server env.',
    });
  }

  const text = String(req.body?.text || '').trim();
  if (!text) {
    return res.status(400).json({ error: 'Missing text payload.' });
  }

  const clippedText = text.slice(0, 2500);

  try {
    let voiceId = configuredVoiceId;
    if (!voiceId) {
      const voicesResponse = await fetch('https://api.elevenlabs.io/v1/voices', {
        headers: { 'xi-api-key': apiKey },
      });

      if (!voicesResponse.ok) {
        const raw = await voicesResponse.text().catch(() => '');
        return res.status(voicesResponse.status).json({
          error: 'Failed to list ElevenLabs voices.',
          details: raw || `HTTP ${voicesResponse.status}`,
        });
      }

      const voicesData = await voicesResponse.json();
      const matchedVoice = (voicesData?.voices || []).find(
        (voice) => String(voice?.name || '').toLowerCase() === voiceName.toLowerCase()
      );
      if (!matchedVoice?.voice_id) {
        return res.status(400).json({
          error: `ElevenLabs voice "${voiceName}" was not found. Set ELEVENLABS_VOICE_ID to use a specific voice.`,
        });
      }
      voiceId = matchedVoice.voice_id;
    }

    const ttsResponse = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${encodeURIComponent(voiceId)}/stream?output_format=mp3_44100_128`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'xi-api-key': apiKey,
        },
        body: JSON.stringify({
          text: clippedText,
          model_id: modelId,
          voice_settings: {
            stability: 0.45,
            similarity_boost: 0.75,
            style: 0.25,
            use_speaker_boost: true,
          },
        }),
      }
    );

    if (!ttsResponse.ok) {
      const raw = await ttsResponse.text().catch(() => '');
      return res.status(ttsResponse.status).json({
        error: 'ElevenLabs API returned an error.',
        details: raw || `HTTP ${ttsResponse.status}`,
      });
    }

    const audioArrayBuffer = await ttsResponse.arrayBuffer();
    const audioBuffer = Buffer.from(audioArrayBuffer);
    res.setHeader('Content-Type', 'audio/mpeg');
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).send(audioBuffer);
  } catch (error) {
    return res.status(500).json({
      error: 'Failed to reach ElevenLabs API.',
      details: error instanceof Error ? error.message : String(error),
    });
  }
}
