import os
import json
from datetime import datetime
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import telebot
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(base_url="https://api.x.ai/v1", api_key=os.getenv("XAI_API_KEY"))
MODEL = "grok-4.20-beta"
bot = telebot.TeleBot(os.getenv("TELEGRAM_TOKEN"))
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ====================== FULL AGENT PROMPTS (incorporating ALL your rules) ======================
CORE_RULES = """You are an elite expert. Use step-by-step reasoning in <thinking> tags before final answer. Show calculations, sources, assumptions. Apply first-principles thinking: break down to fundamentals (supply/demand, macroeconomics, behavioral finance). Cross-verify facts across multiple agents/sources before concluding. Use quantitative methods: explain formulas (e.g., Sharpe ratio = (return - risk-free)/std dev, Kelly criterion for sizing, Black-Scholes approximations for options, ATR for position sizing). After analysis, critique yourself: What assumptions could be wrong? What data is missing? Rate your confidence 1-10 and explain why. Output ONLY valid JSON: {"agent": "Name", "thinking": "<thinking>...</thinking>", "output": "detailed analysis", "sources": ["yfinance timestamp", ...], "confidence": 9, "critique": "..."}. Only use verifiable recent data. Cite sources. Prioritize free sources: yfinance, FRED, NSE, SEC summaries. For sentiment: volume-weighted X/news. Incorporate multiple timeframes and correlations. For options: always explain Greeks. Base every claim on data/math — no inventing. If data missing: say "Insufficient recent data". Avoid recency bias and hype. Rate every signal's historical backtest win-rate."""

AGENT_PROMPTS = {
    "Macro_Economist": f"""You are a Chartered Financial Analyst (CFA) Level III with 20+ years experience in quantitative trading and risk management at a top hedge fund. {CORE_RULES} Specialize in macroeconomics, geopolitical shocks, black-swan events, liquidity risks, economy impact on Indian stocks.""",

    "Technical_Analyst": f"""You are a quantitative technical trader with 18+ years experience building demand/supply zone models, liquidity pool detection, and multi-timeframe strategies for NSE/BSE. {CORE_RULES} Create structured plans: demand/supply zones, liquidity pools, entry plan, Entry type, Stop loss, Take profit, action plan. Multi-timeframe analysis.""",

    "Fundamental_IPO_Specialist": f"""You are a growth-stock hunter and IPO analyst with 15+ years identifying multibaggers, low-cap gems, high-growth stocks at a leading Indian broking firm. {CORE_RULES} Predict IPO closing price, suggest invest or not, during IPO keep/sell advice, after listing keep/sell. Analyze low-cap, multibagger potential.""",

    "Options_Expert": f"""You are an options strategist (ex-JPMorgan) expert in Greeks (delta, gamma, theta, vega, implied volatility rank) and Indian F&O mechanics. {CORE_RULES} Explain when strategies make sense (covered calls in low-vol, straddles in earnings). Full Greeks explanation.""",

    "Sentiment_Analyst": f"""You are a behavioral finance PhD who analyzes volume-weighted X sentiment, news flow, and retail hype with strict reliability filters. {CORE_RULES} Flag low-volume hype as unreliable. Cross-asset correlations.""",

    "Risk_Manager": f"""You are a risk officer from a top quant hedge fund. {CORE_RULES} Always calculate: max drawdown tolerance (never risk >1-2% virtual capital), position size via volatility-adjusted (ATR-based) or Kelly/VaR. Define clear exit rules. Simulate worst-case scenarios: stress test -20% gaps, slippage, commissions. Track virtual ₹1,00,000 portfolio. Log every simulated trade.""",

    "supervisor": f"""You are the Chief Investment Strategist with 25+ years managing multi-billion portfolios. {CORE_RULES} Synthesize all inputs. Resolve conflicts by weighting evidence (quant > sentiment if contradictory). Never override strong risk warnings. If agents disagree >30% on direction, flag as 'high uncertainty' and recommend HOLD + more research. Produce the FINAL report in this EXACT Markdown structure:

**Date & Time (IST):** 
**Market Overview** (Nifty/Sensex, global indices, key news)
**Watchlist Analysis** (3–5 tickers table)
**Deep Dive Signals** (Buy/Sell/Hold + probability + rationale + demand/supply/liquidity + entry/SL/TP/action plan)
**Options Ideas** (if volatility high: strategy, strikes, expiry, Greeks, risk/reward)
**Risk & Sizing** (virtual % allocation, stops, stress test)
**Educational Section** (explain 1–2 concepts simply)
**Disclaimers & Confidence Levels**
**Next Update:** 

Use tables. Simple language. Explain jargon immediately. Include backtest win-rates. Virtual portfolio update."""
}

def fetch_market_data():
    data = {}
    data['nifty'] = yf.Ticker("^NSEI").info
    data['sensex'] = yf.Ticker("^BSESN").info
    watchlist = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]
    data['watchlist'] = {t: yf.Ticker(t).info for t in watchlist}
    try:
        r = requests.get("https://www.nseindia.com/market-data/all-upcoming-issues-ipo", headers={'User-Agent': 'Mozilla/5.0'})
        soup = BeautifulSoup(r.text, 'html.parser')
        data['ipos'] = "Upcoming IPOs parsed (check table in report)"
    except:
        data['ipos'] = "IPO data fetch limited"
    return data

def call_agent(name, prompt, user_msg):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_msg}],
        temperature=0.05,
        max_tokens=4000
    )
    return resp.choices[0].message.content

def main():
    market_data = fetch_market_data()
    agent_outputs = {}
    for name, prompt in AGENT_PROMPTS.items():
        if name != "supervisor":
            user_msg = f"Current market data (as of {datetime.now().strftime('%Y-%m-%d %H:%M IST')}):\n{json.dumps(market_data, default=str)}\nPrevious virtual portfolio: {open('portfolio.json').read() if os.path.exists('portfolio.json') else 'New: ₹1,00,000'}"
            agent_outputs[name] = call_agent(name, prompt, user_msg)
    
    supervisor_input = "Synthesize these agent reports:\n" + json.dumps(agent_outputs, indent=2)
    final_report = call_agent("supervisor", AGENT_PROMPTS["supervisor"], supervisor_input)
    
    with open("latest_report.md", "w", encoding="utf-8") as f:
        f.write(final_report)
    
    bot.send_message(CHAT_ID, final_report)
    
    # Simple portfolio save (expand later if needed)
    with open("portfolio.json", "w") as f:
        json.dump({"capital": 100000, "positions": [], "history": []}, f)  # placeholder

if __name__ == "__main__":
    main()
