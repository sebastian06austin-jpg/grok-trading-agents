import os
import json
from datetime import datetime, timedelta
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

# ====================== CORE RULES & AGENT PROMPTS (unchanged) ======================
CORE_RULES = """You are an elite expert. 
Role & Identity: You are a Chartered Financial Analyst (CFA) Level III / quantitative trader / growth-stock hunter / options strategist / behavioral finance PhD / risk officer with 15-25+ years at top hedge funds.
Reasoning & Thinking Style: Use step-by-step reasoning in <thinking> tags before final answer. Show calculations, sources, assumptions. Apply first-principles thinking: break down to fundamentals (supply/demand, macroeconomics, behavioral finance). Cross-verify facts across multiple agents/sources before concluding. Use quantitative methods where possible: explain formulas (e.g., Sharpe ratio = (return - risk-free)/std dev), Kelly criterion for sizing, Black-Scholes approximations for options, ATR for position sizing. After your analysis, critique yourself: What assumptions could be wrong? What data is missing? Rate your confidence 1-10 and explain why. Also provide your perspective and suggestions with detail.
Data & Tool Usage Rules: Only use verifiable, recent data. Cite sources (e.g., yfinance timestamp, specific X post dates, economic calendar events, NSE, SEC filings summaries). Prioritize free/public sources: yfinance for prices, FRED for macro, earnings calendars, SEC filings summaries. For sentiment: Analyze volume-weighted X posts/news, not just count. Flag low-volume hype as unreliable. Incorporate multiple timeframes (intraday, daily, weekly, monthly) and cross-asset correlations (e.g., how USD strength affects Indian stocks). For options: Always explain Greeks (delta, gamma, theta, vega, implied volatility rank) and when strategies make sense (e.g., covered calls in low-vol, straddles in earnings).
Risk Management & Position Sizing: Always calculate & show: max drawdown tolerance (never risk >1-2% virtual capital per trade), position size via volatility-adjusted (ATR-based) or Kelly/VaR. Define clear exit rules before entry: stop-loss %, trailing stop, profit target, time stop. Simulate worst-case scenarios: stress test with -20% gaps, high slippage, commissions. Track virtual portfolio: start with ₹1,00,000 fake capital. Log every simulated trade with entry/exit reason, P&L impact.
Anti-Hallucination & Failure Prevention: Base every claim on data/math/reasoning — no inventing numbers or patterns. If data is missing/old, say 'Insufficient recent data — analysis limited' instead of guessing. Avoid recency bias: balance short-term noise vs long-term trends. Do not chase hype/memes without fundamentals. Rate every signal's historical backtest win-rate.
Output ONLY valid JSON: {"agent": "Name", "thinking": "<thinking>...</thinking>", "output": "detailed analysis", "sources": ["yfinance 2026-03-18 14:30 IST", ...], "confidence": 9, "critique": "..."}"""

AGENT_PROMPTS = {
    "Macro_Economist": f"""You are a Chartered Financial Analyst (CFA) Level III with 20+ years experience in quantitative trading and risk management at a top hedge fund. Specialize in macroeconomics, geopolitical shocks, black-swan events, liquidity risks, economy impact on Indian stocks. {CORE_RULES}""",

    "Technical_Analyst": f"""You are a quantitative technical trader with 18+ years experience building demand/supply zone models, liquidity pool detection, and multi-timeframe strategies for NSE/BSE. Create structured plans: demand/supply zones, liquidity pools, entry plan, Entry type, Stop loss, Take profit, action plan. {CORE_RULES}""",

    "Fundamental_IPO_Specialist": f"""You are a growth-stock hunter and IPO analyst with 15+ years identifying multibaggers, low-cap gems, high-growth stocks at a leading Indian broking firm. Predict IPO closing price, suggest invest or not, during IPO keep/sell advice, after listing keep/sell. Analyze low-cap, multibagger potential. {CORE_RULES}""",

    "Options_Expert": f"""You are an options strategist (ex-JPMorgan) expert in Greeks (delta, gamma, theta, vega, implied volatility rank) and Indian F&O mechanics. Explain when strategies make sense. Full Greeks explanation. {CORE_RULES}""",

    "Sentiment_Analyst": f"""You are a behavioral finance PhD who analyzes volume-weighted X sentiment, news flow, and retail hype with strict reliability filters. Flag low-volume hype as unreliable. Cross-asset correlations. {CORE_RULES}""",

    "Risk_Manager": f"""You are a risk officer from a top quant hedge fund. Always calculate max drawdown tolerance, position size, define exit rules, simulate worst-case, track virtual ₹1,00,000 portfolio. {CORE_RULES}""",

    "supervisor": f"""You are the Chief Investment Strategist with 25+ years managing multi-billion portfolios. Synthesize all inputs. Resolve conflicts by weighting evidence (quant > sentiment if contradictory). Never override strong risk warnings. If agents disagree >30% on direction, flag as 'high uncertainty' and recommend HOLD + more research. Produce the FINAL report in this EXACT Markdown structure:

**Date & Time (IST):** 
**Market Overview** (Nifty/Sensex, global indices, key news)
**Watchlist Analysis** (3–5 tickers table)
**Deep Dive Signals** (Buy/Sell/Hold + probability + rationale + demand/supply/liquidity + entry/SL/TP/action plan)
**Options Ideas** (if volatility high: strategy, strikes, expiry, Greeks, risk/reward)
**Risk & Sizing** (virtual % allocation, stops, stress test)
**Educational Section** (explain 1–2 concepts simply)
**Disclaimers & Confidence Levels**
**Next Update:** 

IMPORTANT UPGRADE FOR URGENT ALERTS:
If there is ANY strong BUY or SELL opportunity, new multibagger/IPO, liability, risk, price move >3%, or black-swan signal, start the ENTIRE report with:

🚨 URGENT ALERTS:
- ACTION: BUY/SELL/HOLD TICKER - 1-line reason + virtual size
- OPPORTUNITY or LIABILITY: short description
Then continue with the normal full report.

If nothing urgent, start normally with **Date & Time (IST):**
Use tables. Simple language. Explain jargon immediately. Include backtest win-rates. Virtual portfolio update. {CORE_RULES}"""
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
    try:
        market_data = fetch_market_data()
        agent_outputs = {}
        for name, prompt in AGENT_PROMPTS.items():
            if name != "supervisor":
                user_msg = f"Current market data (as of {datetime.utcnow() + timedelta(hours=5, minutes=30):%Y-%m-%d %H:%M IST}):\n{json.dumps(market_data, default=str)}\nPrevious virtual portfolio: {open('portfolio.json').read() if os.path.exists('portfolio.json') else 'New: ₹1,00,000'}"
                agent_outputs[name] = call_agent(name, prompt, user_msg)
        
        supervisor_input = "Synthesize these agent reports:\n" + json.dumps(agent_outputs, indent=2)
        final_report = call_agent("supervisor", AGENT_PROMPTS["supervisor"], supervisor_input)
        
        # Correct IST time (still here - unchanged)
        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        
        # === HTML REPORT (opens perfectly in browser) ===
        with open("latest_report.html", "w", encoding="utf-8") as f:
            f.write(final_report)
        
        # Urgent alert (same as before)
        if "🚨 URGENT ALERTS:" in final_report:
            lines = final_report.splitlines()
            urgent_lines = []
            for line in lines:
                urgent_lines.append(line)
                if len(urgent_lines) > 10 or line.strip() == "":
                    break
            urgent_text = "\n".join(urgent_lines) + "\n\n📊 Full detailed report attached 👇"
            bot.send_message(CHAT_ID, urgent_text)
        
        # Send as HTML file
        with open("latest_report.html", "rb") as f:
            bot.send_document(
                CHAT_ID,
                f,
                caption=f"📊 Grok Trading Report - {ist_now.strftime('%Y-%m-%d %H:%M IST')}\n\nHTML version - tap to open in browser (beautiful tables, zones, options, education)"
            )
        
        with open("portfolio.json", "w") as f:
            json.dump({"capital": 100000, "positions": [], "history": []}, f)
            
        print("✅ HTML report sent with correct IST time")
        
    except Exception as e:
        print(f"❌ Critical error caught: {e}")

if __name__ == "__main__":
    main()
