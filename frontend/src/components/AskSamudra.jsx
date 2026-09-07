import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';

const API_BASE = 'http://localhost:8000';

const EXAMPLES = [
  "Which float has the deepest thermocline?",
  "Average MLD in Arabian Sea this year",
  "Floats near Chennai",
  "Warmest surface temp recorded",
  "Compare Arabian Sea vs Bay of Bengal salinity",
  "Top 5 floats by profile count"
];

export default function AskSamudra() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (queryText) => {
    const text = queryText || input;
    if (!text.trim() || loading) return;

    const newMsg = { role: 'user', content: text };
    const updated = [...messages, newMsg];
    setMessages(updated);
    if (!queryText) setInput('');
    setLoading(true);

    try {
      const historyPayload = updated
        .slice(0, -1)
        .map(m => ({ role: m.role, content: m.content }));

      const res = await axios.post(`${API_BASE}/api/chat`, {
        message: text,
        history: historyPayload
      });

      const reply = res.data?.response || 'No response';
      setMessages([...updated, { role: 'assistant', content: reply }]);
    } catch (err) {
      console.error(err);
      setMessages([...updated, { role: 'assistant', content: 'Error communicating with AI backend service.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2>Ask Samudra</h2>
      <div className="st-caption" style={{ marginBottom: '1rem' }}>
        Ask anything about Argo floats, ocean conditions, or tuna catch data
      </div>

      <div style={{ fontWeight: 500, fontSize: '0.85rem', marginBottom: '0.5rem', color: '#858C89', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Try these:</div>
      <div className="try-buttons-grid">
        {EXAMPLES.map((q, idx) => (
          <button key={idx} className="st-button" onClick={() => handleSend(q)}>
            {q}
          </button>
        ))}
      </div>

      <div className="chat-message-list">
        {messages.map((msg, i) => (
          <div key={i} className={`chat-msg ${msg.role}`}>
            <div className="chat-msg-icon">
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>
            <div style={{ whiteSpace: 'pre-wrap', flex: 1, color: msg.role === 'user' ? '#F2F4F3' : '#F2F4F3' }}>{msg.content}</div>
          </div>
        ))}

        {loading && (
          <div className="chat-msg assistant">
            <div className="chat-msg-icon">🤖</div>
            <div style={{ color: '#858C89' }}>Querying database...</div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <div className="chat-input-container">
        <input
          type="text"
          className="st-chat-input"
          placeholder="Ask anything..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          disabled={loading}
        />
      </div>
    </div>
  );
}
