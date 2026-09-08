import { useEffect, useState, useRef } from 'react';
import { createConversation, listConversations } from '../api/conversationApi.js';
import Sidebar from '../components/sidebar/Sidebar.jsx';
import ChatArea from '../components/chat/ChatArea.jsx';
import Composer from '../components/chat/Composer.jsx';
import MarketTickerHeader from '../components/stock/MarketTickerHeader.jsx';

const GUEST_CONVERSATION = {
  id: 'guest-conversation',
  title: 'Stock Market Analyzer Workspace',
  selected_model: 'groq/llama3',
  interaction_mode: 'chat',
};

function ChatPage() {
  const [conversations, setConversations] = useState([]);
  const [activeConversation, setActiveConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const composerRef = useRef(null);

  useEffect(() => {
    async function load() {
      setConversations([GUEST_CONVERSATION]);
      setActiveConversation(GUEST_CONVERSATION);
      setMessages([
        {
          id: 'welcome-message',
          role: 'assistant',
          content: `👋 **Welcome to OneAI Stock Market Analyzer!**\n\nI am your AI Decision Support Analyst for Indian Equities (NSE/BSE). I analyze live price action, technical indicators, and fundamentals across three distinct horizons:\n\n- ⚡ **Intraday Trading**: RSI, MACD, Volume Surges & Pivot Point Levels ($S_1, S_2, R_1, R_2$).\n- 📈 **Short-Term Holding**: Moving Averages ($SMA_{20}, SMA_{50}$) & Breakout Patterns.\n- 🏢 **Long-Term Investment**: Valuation ratios, P/E, Market Cap, & Return metrics.\n\n*Try asking:*  \n- *"Analyze TCS for intraday trading"*  \n- *"Show me overall market condition"*  \n- *"Find 5 stocks with strong momentum"*`,
        },
      ]);
    }
    load();
  }, []);

  function handleQuickQuery(query) {
    if (window.triggerSendQuery) {
      window.triggerSendQuery(query);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-[#0b0f19] text-slate-100 font-sans antialiased overflow-hidden">
      {/* Top Live Ticker Bar */}
      <MarketTickerHeader />

      {/* Main Workspace Layout */}
      <div className="flex flex-1 min-h-0">
        {/* Left Sidebar */}
        <div className="w-72 flex-shrink-0">
          <Sidebar 
            conversations={conversations} 
            activeConversation={activeConversation} 
            onSelect={setActiveConversation} 
            onQuickQuery={handleQuickQuery}
          />
        </div>

        {/* Center Main Chat Area */}
        <section className="flex flex-1 flex-col min-w-0 border-l border-slate-800 bg-[#0d1322]">
          <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/60 px-6 py-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-slate-200">Stock Analysis & Decision Support Chat</span>
              <span className="rounded-full bg-emerald-500/20 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                Live Data Connected
              </span>
            </div>
            <span className="text-xs text-slate-400">Powered by yfinance & Pure Math Engine</span>
          </div>

          <ChatArea messages={messages} />

          {activeConversation && (
            <Composer 
              conversation={activeConversation} 
              messages={messages} 
              setMessages={setMessages} 
            />
          )}
        </section>
      </div>
    </div>
  );
}

export default ChatPage;
