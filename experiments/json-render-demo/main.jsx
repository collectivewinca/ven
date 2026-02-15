import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import OpenAI from "openai";
import { defineCatalog } from "@json-render/core";
import { schema } from "@json-render/react";
import { defineRegistry, Renderer } from "@json-render/react";
import { z } from "zod";

// 1. Define Your Catalog - the guardrails
const catalog = defineCatalog(schema, {
  components: {
    Card: {
      props: z.object({ 
        title: z.string(),
        description: z.string().optional(),
      }),
      description: "A card container for content",
    },
    Metric: {
      props: {
        label: z.string(),
        value: z.string(),
        format: z.enum(["currency", "percent", "number"]).optional(),
      },
      description: "Display a metric value with label",
    },
    Button: {
      props: {
        label: z.string(),
        variant: z.enum(["primary", "secondary"]).optional(),
      },
      description: "Clickable button",
    },
    Row: {
      props: z.object({ gap: z.number().optional() }),
      description: "Horizontal row layout",
    },
  },
});

// 2. Define Your Components - what they actually render
const { registry } = defineRegistry(catalog, {
  components: {
    Card: ({ props, children }) => (
      <div style={{ 
        border: '1px solid #e0e0e0', 
        borderRadius: '8px', 
        padding: '16px',
        margin: '8px',
        background: 'white',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <h3 style={{ margin: '0 0 8px 0' }}>{props.title}</h3>
        {props.description && <p style={{ color: '#666', margin: '0 0 8px 0' }}>{props.description}</p>}
        {children}
      </div>
    ),
    Metric: ({ props }) => (
      <div style={{ 
        padding: '12px', 
        background: '#f5f5f5', 
        borderRadius: '6px',
        textAlign: 'center',
        flex: 1
      }}>
        <div style={{ fontSize: '12px', color: '#666', textTransform: 'uppercase' }}>{props.label}</div>
        <div style={{ fontSize: '24px', fontWeight: 'bold' }}>
          {props.format === 'currency' ? `$${props.value}` : 
           props.format === 'percent' ? `${props.value}%` : 
           props.value}
        </div>
      </div>
    ),
    Button: ({ props }) => (
      <button style={{
        padding: '10px 20px',
        background: props.variant === 'secondary' ? '#e0e0e0' : '#007AFF',
        color: props.variant === 'secondary' ? '#333' : 'white',
        border: 'none',
        borderRadius: '6px',
        cursor: 'pointer',
        fontWeight: '500'
      }}>
        {props.label}
      </button>
    ),
    Row: ({ props, children }) => (
      <div style={{ 
        display: 'flex', 
        gap: props.gap || 8,
        flexWrap: 'wrap'
      }}>
        {children}
      </div>
    ),
  },
});

// Default spec
const defaultSpec = {
  root: "card-1",
  elements: {
    "card-1": {
      type: "Card",
      props: { title: "Revenue Dashboard", description: "Key metrics for this month" },
      children: ["metrics-row"],
    },
    "metrics-row": {
      type: "Row",
      props: { gap: 16 },
      children: ["metric-1", "metric-2", "metric-3"],
    },
    "metric-1": {
      type: "Metric",
      props: { label: "Revenue", value: "124,500", format: "currency" },
    },
    "metric-2": {
      type: "Metric",
      props: { label: "Growth", value: "23", format: "percent" },
    },
    "metric-3": {
      type: "Metric",
      props: { label: "Users", value: "8,432", format: "number" },
    },
  },
};

function App() {
  const [provider, setProvider] = useState(localStorage.getItem('api_provider') || 'openrouter');
  const [apiKey, setApiKey] = useState(localStorage.getItem('api_key') || '');
  const [prompt, setPrompt] = useState('');
  const [spec, setSpec] = useState(defaultSpec);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const providers = {
    openrouter: {
      name: 'OpenRouter',
      baseURL: 'https://openrouter.ai/api/v1',
      model: 'deepseek/deepseek-chat',
    },
    deepseek: {
      name: 'DeepSeek',
      baseURL: 'https://api.deepseek.com',
      model: 'deepseek-chat',
    },
  };

  const handleSave = () => {
    localStorage.setItem('api_provider', provider);
    localStorage.setItem('api_key', apiKey);
    alert('Settings saved!');
  };

  const handleGenerate = async () => {
    if (!apiKey) {
      setError('Please enter your API key first');
      return;
    }
    if (!prompt.trim()) {
      setError('Please enter a prompt');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const config = providers[provider];
      
      const client = new OpenAI({
        apiKey,
        dangerouslyAllowBrowser: true,
        baseURL: config.baseURL,
      });

      const systemPrompt = `${catalog.prompt()}

You must respond with ONLY a valid JSON object in this exact format:
{
  "root": "element-id",
  "elements": {
    "element-id": {
      "type": "ComponentName",
      "props": { ... },
      "children": ["child-id-1", "child-id-2"]
    }
  }
}

Do NOT include any markdown formatting, code blocks, or explanation. Just raw JSON.`;

      const response = await client.chat.completions.create({
        model: config.model,
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: prompt },
        ],
        temperature: 0.1,
      });

      const content = response.choices[0].message.content;
      const parsedSpec = JSON.parse(content);
      setSpec(parsedSpec);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '24px', maxWidth: '800px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '24px' }}>json-render + {providers[provider].name}</h1>
      
      {/* Provider & API Key Settings */}
      <div style={{ marginBottom: '24px', padding: '16px', background: '#e8f4fd', borderRadius: '8px' }}>
        <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
          Provider:
        </label>
        <select 
          value={provider} 
          onChange={(e) => setProvider(e.target.value)}
          style={{ width: '100%', padding: '8px', marginBottom: '12px', borderRadius: '4px', border: '1px solid #ccc' }}
        >
          <option value="openrouter">OpenRouter (uses DeepSeek model)</option>
          <option value="deepseek">DeepSeek (direct)</option>
        </select>

        <label style={{ display: 'block', marginBottom: '8px', fontWeight: 'bold' }}>
          API Key:
        </label>
        <div style={{ display: 'flex', gap: '8px' }}>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={provider === 'openrouter' ? 'sk-or-...' : 'sk-...'}
            style={{ flex: 1, padding: '8px', borderRadius: '4px', border: '1px solid #ccc' }}
          />
          <button 
            onClick={handleSave}
            style={{ padding: '8px 16px', background: '#007AFF', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer' }}
          >
            Save
          </button>
        </div>
        <small style={{ color: '#666' }}>Stored in localStorage</small>
      </div>

      {/* Prompt Input */}
      <div style={{ marginBottom: '24px' }}>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Describe what UI you want... (e.g., 'Show me a sales dashboard with metrics')"
          style={{ 
            width: '100%', 
            padding: '12px', 
            borderRadius: '8px', 
            border: '1px solid #ccc',
            minHeight: '80px',
            fontFamily: 'inherit',
            resize: 'vertical'
          }}
        />
        <button
          onClick={handleGenerate}
          disabled={loading}
          style={{
            marginTop: '8px',
            padding: '12px 24px',
            background: loading ? '#ccc' : '#007AFF',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: loading ? 'not-allowed' : 'pointer',
            fontWeight: '500',
            fontSize: '16px'
          }}
        >
          {loading ? 'Generating...' : 'Generate UI'}
        </button>
      </div>

      {/* Error Display */}
      {error && (
        <div style={{ padding: '12px', background: '#f8d7da', color: '#721c24', borderRadius: '6px', marginBottom: '16px' }}>
          {error}
        </div>
      )}

      {/* Rendered UI */}
      <Renderer spec={spec} registry={registry} />

      {/* Debug Info */}
      <div style={{ marginTop: '32px', padding: '16px', background: '#f0f0f0', borderRadius: '8px' }}>
        <details>
          <summary style={{ cursor: 'pointer', fontWeight: 'bold' }}>View Generated JSON Spec</summary>
          <pre style={{ marginTop: '12px', padding: '12px', background: '#fff', borderRadius: '4px', overflow: 'auto', fontSize: '12px' }}>
            {JSON.stringify(spec, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  );
}

const root = createRoot(document.getElementById("root"));
root.render(<App />);
