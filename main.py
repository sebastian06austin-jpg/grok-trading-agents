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

# ====================== FULL AGENT PROMPTS (only supervisor changed for urgent alerts) ======================
CORE_RULES = """... (same as before - no need to change) ..."""  # Keep everything exactly as it was

AGENT_PROMPTS = {
    # ... (Macro_Economist, Technical_Analyst, etc. — keep exactly the same as before) ...

    "supervisor": f"""You are the Chief Investment Strategist... (same as before)

IMPORTANT UPGRADE FOR URGENT ALERTS:
If there is ANY strong BUY or SELL opportunity, new multibagger/IPO, liability, risk, price move >3%, or black-swan signal, start the ENTIRE report with:

🚨 URGENT ALERTS:
- ACTION: BUY/SELL/HOLD TICKER - 1-line reason + virtual size
- OPPORTUNITY or LIABILITY: short description
Then continue with the normal full report.

If nothing urgent, start normally with **Date & Time (IST):**
"""
}

# (rest of the code same until main())

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
    
    # === URGENT ALERTS LOGIC (new) ===
    if "🚨 URGENT ALERTS:" in final_report:
        # Send short instant message first
        lines = final_report.splitlines()
        urgent_lines = []
        for line in lines:
            urgent_lines.append(line)
            if len(urgent_lines) > 8 or line.strip() == "":  # first 8 lines or until empty
                break
        urgent_text = "\n".join(urgent_lines) + "\n\n📊 Full detailed report below 👇"
        bot.send_message(CHAT_ID, urgent_text)
    
    # Send full report
    bot.send_message(CHAT_ID, final_report)
    
    # portfolio save (same)
    with open("portfolio.json", "w") as f:
        json.dump({"capital": 100000, "positions": [], "history": []}, f)

if __name__ == "__main__":
    main()
