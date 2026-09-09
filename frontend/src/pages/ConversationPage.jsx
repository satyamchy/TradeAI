import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { processConversation } from '../api/stockApi';

const SUGGESTIONS = [
  "Analyze Reliance Industries for intraday trading",
  "Compare TCS and Infosys technical indicators",
  "What are the key support and resistance levels for HDFC Bank?",
  "Screen top momentum stocks for delivery today",
];

export default function ConversationPage() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: `👋 **Welcome to TradeAI Agentic Assistant!**\n\nI am powered by an asynchronous **LangGraph** engine connected directly to live NSE/BSE market quotes and mathematical technical indicators.\n\nAsk me anything about Indian stocks:\n- ⚡ **Intraday Pivots**: $S_1, S_2, R_1, R_2$, RSI, and MACD signals\n- 📈 **Trend Analysis**: 20-day & 50-day Moving Averages, Bollinger Bands\n- 🏢 **Fundamental Valuation**: P/E, Market Cap, Return metrics`,
      sources: [],
      structured_data: null,
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleSend = async (queryText) => {
    const q = (queryText || input).trim();
    if (!q || loading) return;

    const userMsg = { role: 'user', content: q };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await processConversation(q);
      const botMsg = {
        role: 'assistant',
        content: res.answer || "No response received.",
        sources: res.sources || [],
        structured_data: res.structured_data || null,
      };
      setMessages(prev => [...prev, botMsg]);
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `❌ **Error**: ${err?.response?.data?.detail || err.message || 'Failed to process conversation with AI agent.'}`,
          sources: [],
          structured_data: null,
        }
      ]);
    }
    setLoading(false);
  };

  return (
    <div className="max-w-5xl mx-auto p-4 flex flex-col h-[calc(100vh-105px)]">
      {/* Header */}
      <div className="card p-3 mb-3 flex flex-wrap items-center justify-between gap-2" style={{ background: '#1c1815' }}>
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center font-bold text-sm"
               style={{ background: 'linear-gradient(135deg,#ff6b00,#ffaa00)', color: '#12100e' }}>
            💬
          </div>
          <div>
            <h1 className="text-sm font-bold" style={{ color: '#f5ebe1' }}>Agentic Financial Decision Support</h1>
            <p className="text-[11px]" style={{ color: '#a89b8c' }}>Orchestrated via LangGraph with multi-horizon evaluation</p>
          </div>
        </div>
        <span className="text-[11px] px-2.5 py-1 rounded-full badge-orange font-semibold">
          POST /api/conversation
        </span>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map((msg, idx) => {
          const isUser = msg.role === 'user';
          return (
            <div key={idx} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-3xl rounded-xl p-4 shadow-sm border ${
                  isUser
                    ? 'border-orange-500/40 text-white'
                    : 'border-stone-800 text-stone-200'
                }`}
                style={{
                  background: isUser ? '#2d1f14' : '#1c1815',
                  borderColor: isUser ? '#ff6b00' : '#382e26',
                }}
              >
                {/* Message Header */}
                <div className="text-[11px] font-semibold mb-1 flex items-center gap-1.5" style={{ color: isUser ? '#ffaa00' : '#ff8533' }}>
                  <span>{isUser ? '👤 You' : '🤖 TradeAI Agent'}</span>
                </div>

                {/* Markdown Content */}
                <div className="text-sm leading-relaxed prose prose-invert max-w-none text-[#f5ebe1]">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>

                {/* Structured Financial Metric Card */}
                {msg.structured_data && (
                  <div className="mt-3 p-2.5 rounded-lg border text-xs grid grid-cols-2 sm:grid-cols-4 gap-2"
                       style={{ background: '#12100e', borderColor: '#382e26' }}>
                    <div>
                      <span className="text-[10px]" style={{ color: '#a89b8c' }}>Ticker</span>
                      <div className="font-bold text-sm" style={{ color: '#ffaa00' }}>{msg.structured_data.ticker}</div>
                    </div>
                    <div>
                      <span className="text-[10px]" style={{ color: '#a89b8c' }}>Current Price</span>
                      <div className="font-semibold text-sm" style={{ color: '#f5ebe1' }}>₹{msg.structured_data.current_price}</div>
                    </div>
                    <div>
                      <span className="text-[10px]" style={{ color: '#a89b8c' }}>RSI (14)</span>
                      <div className="font-semibold text-sm" style={{ color: '#10b981' }}>
                        {msg.structured_data.indicators?.rsi_14 ?? '—'}
                      </div>
                    </div>
                    <div>
                      <span className="text-[10px]" style={{ color: '#a89b8c' }}>P/E Ratio</span>
                      <div className="font-semibold text-sm" style={{ color: '#f5ebe1' }}>
                        {msg.structured_data.pe_ratio ?? '—'}
                      </div>
                    </div>
                  </div>
                )}

                {/* Sources & Badges */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-3 pt-2 border-t flex flex-wrap items-center gap-1.5 text-[11px]" style={{ borderColor: '#382e26' }}>
                    <span style={{ color: '#a89b8c' }}>Data Sources:</span>
                    {msg.sources.map((s, sIdx) => (
                      <span key={sIdx} className="px-2 py-0.5 rounded badge-beige font-mono text-[10px]">
                        {s.title}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start">
            <div className="card p-3 rounded-xl border flex items-center gap-2" style={{ background: '#1c1815', borderColor: '#382e26' }}>
              <span className="w-2.5 h-2.5 rounded-full bg-orange-500 pulse-dot" />
              <span className="text-xs" style={{ color: '#a89b8c' }}>Agent analyzing price action, indicators &amp; order book…</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggested Queries */}
      <div className="py-2 flex flex-wrap gap-1.5 overflow-x-auto">
        {SUGGESTIONS.map((s, idx) => (
          <button
            key={idx}
            onClick={() => handleSend(s)}
            className="text-xs px-2.5 py-1 rounded-lg border transition-all text-left truncate max-w-xs hover:border-orange-500/60"
            style={{ background: '#1c1815', borderColor: '#382e26', color: '#a89b8c' }}
          >
            💡 {s}
          </button>
        ))}
      </div>

      {/* Input Composer */}
      <form onSubmit={(e) => { e.preventDefault(); handleSend(); }} className="card p-2 flex items-center gap-2" style={{ background: '#1c1815' }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about NSE/BSE stocks (e.g., 'Analyze TCS for delivery')..."
          className="flex-1 rounded-lg px-3 py-2.5 text-sm outline-none transition-all"
          style={{ background: '#12100e', border: '1px solid #382e26', color: '#f5ebe1' }}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-5 py-2.5 rounded-lg text-sm font-bold text-white transition-all hover:opacity-90 disabled:opacity-40"
          style={{ background: 'linear-gradient(135deg, #ff6b00, #e65100)' }}
        >
          Send
        </button>
      </form>
    </div>
  );
}
