import os
import sys
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
from datetime import datetime
import time
import pandas as pd
import numpy as np
import requests
import yfinance as yf

# Fix Windows console emoji printing issue
sys.stdout.reconfigure(encoding='utf-8')

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_twse_data():
    url_quotes = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    res_quotes = requests.get(url_quotes)
    df_quotes = pd.DataFrame(res_quotes.json())
    
    url_info = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    res_info = requests.get(url_info)
    df_info = pd.DataFrame(res_info.json())
    
    # Clean and merge
    if '公司代號' in df_info.columns:
        df_info = df_info[['公司代號', '產業別']].rename(columns={'公司代號': 'Code', '產業別': 'Industry'})
    else:
        df_info = df_info.rename(columns={'Code': 'Code', 'Sector': 'Industry'}) # fallback

    df = pd.merge(df_quotes, df_info, on='Code', how='inner')
    
    def parse_float(val):
        try:
            return float(str(val).replace(',', ''))
        except:
            return np.nan
            
    df['ClosingPrice'] = df['ClosingPrice'].apply(parse_float)
    df['Change'] = df['Change'].apply(parse_float)
    df['TradeValue'] = df['TradeValue'].apply(parse_float)
    
    df['PrevClose'] = df['ClosingPrice'] - df['Change']
    df['ChangePct'] = np.where(df['PrevClose'] > 0, (df['Change'] / df['PrevClose']) * 100, 0)
    
    return df.dropna(subset=['ClosingPrice', 'ChangePct', 'Industry'])

def analyze_market_data(df):
    df = df[df['Industry'] != '']
    industry_stats = df.groupby('Industry').agg(
        AvgChangePct=('ChangePct', 'mean'),
        TotalTradeValue=('TradeValue', 'sum'),
        StockCount=('Code', 'count')
    ).reset_index()
    
    industry_stats = industry_stats[industry_stats['StockCount'] >= 3]
    strong_industries = industry_stats.sort_values(by='AvgChangePct', ascending=False).head(3)
    
    report_data = []
    for _, row in strong_industries.iterrows():
        ind = row['Industry']
        ind_df = df[df['Industry'] == ind].sort_values(by='ChangePct', ascending=False).head(5)
        
        stocks_info = []
        for _, s_row in ind_df.iterrows():
            stocks_info.append(f"{s_row['Name']}({s_row['Code']}): {s_row['ClosingPrice']} (漲幅: {s_row['ChangePct']:.2f}%)")
            
        report_data.append({
            'Industry': ind,
            'AvgChangePct': row['AvgChangePct'],
            'TopStocks': stocks_info
        })
    return report_data

@app.get("/api/market-analysis")
async def get_market_analysis():
    # 1. Fetch and process TWSE Data
    df = get_twse_data()
    report_data = analyze_market_data(df)
    
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        return {
            "success": False,
            "error": "API Key 未設定，請在後端終端機設定 GEMINI_API_KEY 環境變數。",
            "data": report_data
        }

    # 2. Call Gemini
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        prompt = f"""
        你是專業的台灣股市分析師。以下是 {today_str} 台灣股市當天最強勢的族群資料：\n
        """
        for d in report_data:
            prompt += f"族群：{d['Industry']} (平均漲幅: {d['AvgChangePct']:.2f}%)\n"
            prompt += f"強勢股：{', '.join(d['TopStocks'])}\n\n"
            
        prompt += """
        請根據上述資料，直接撰寫一份簡潔專業的盤後報告：
        ## 今日強勢分析
        結合近期總經或產業趨勢，說明這些族群為何今日轉強。
        ## 明日預估
        預估明日這些資金是否延續，或者可能輪動到哪個特定族群，並說明理由。
        ## 重點持股建議
        對列表中的領頭羊給出簡短的操作與風險提醒。
        不要寫任何廢話，直接給重點。
        請使用 Markdown 格式。
        """
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                return {
                    "success": True,
                    "data": report_data,
                    "ai_report": response.text
                }
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    time.sleep(20)
                else:
                    raise e
    except Exception as e:
        return {
            "success": False,
            "error": f"AI 解析失敗: {str(e)}",
            "data": report_data
        }

@app.get("/api/stock-analysis/{symbol}")
async def get_stock_analysis(symbol: str):
    # Fetch data using yfinance
    # Auto append .TW for Taiwan stocks if not specified.
    yf_symbol = symbol if symbol.endswith(".TW") or symbol.endswith(".TWO") else f"{symbol}.TW"
    
    ticker = yf.Ticker(yf_symbol)
    
    # 1. Fetch History (Technical)
    hist = ticker.history(period="1mo")
    if hist.empty:
        # Fallback to .TWO if .TW fails
        if not symbol.endswith(".TW") and not symbol.endswith(".TWO"):
            yf_symbol = f"{symbol}.TWO"
            ticker = yf.Ticker(yf_symbol)
            hist = ticker.history(period="1mo")
            
        if hist.empty:
            return {"success": False, "error": f"找不到股號 {symbol} 的相關交易資料。"}

    try:
        info = ticker.info
    except Exception:
        info = {}

    recent_close = hist['Close'].iloc[-1] if not hist.empty else 0
    recent_vol = hist['Volume'].iloc[-1] if not hist.empty else 0
    
    # Calculate simple technical indicators (MA5, MA20)
    hist['MA5'] = hist['Close'].rolling(window=5).mean()
    hist['MA20'] = hist['Close'].rolling(window=20).mean()
    ma5 = hist['MA5'].iloc[-1] if len(hist) >= 5 else 0
    ma20 = hist['MA20'].iloc[-1] if len(hist) >= 20 else 0
    
    # Prepare basic fundamentals
    pe = info.get('trailingPE', 'N/A')
    pb = info.get('priceToBook', 'N/A')
    dividend = info.get('dividendYield', 'N/A')
    company_name = info.get('shortName', symbol)
    sector = info.get('sector', 'N/A')
    
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        return {
            "success": False,
            "error": "API Key 未設定，請在後端終端機設定 GEMINI_API_KEY 環境變數。"
        }
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"""
        你是一位專業的台股分析師。請根據以下 {company_name} ({symbol}) 的最新市場數據，撰寫一份全面的個股分析報告。
        
        【技術面數據】
        最新收盤價: {recent_close:.2f}
        5日均線: {ma5:.2f}
        20日均線: {ma20:.2f}
        最新成交量: {recent_vol}
        
        【基本面數據】
        產業: {sector}
        本益比 (P/E): {pe}
        股價淨值比 (P/B): {pb}
        殖利率: {dividend if isinstance(dividend, str) else f"{dividend*100:.2f}%"}
        
        請撰寫一份專業的個股分析報告，必須包含以下三個段落：
        1. ## 技術面分析 (根據均線與收盤價位置)
        2. ## 基本面與籌碼面推測 (根據本益比/產業特性與價量變化，推測目前法人的參與熱度與籌碼安定度)
        3. ## 操作建議與風險提示
        
        請使用 Markdown 格式，不要寫多餘的寒暄或免責聲明。
        """
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                return {
                    "success": True,
                    "symbol": symbol,
                    "company_name": company_name,
                    "recent_close": recent_close,
                    "ai_report": response.text
                }
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    time.sleep(20)
                else:
                    raise e
    except Exception as e:
         return {
            "success": False,
            "error": f"AI 個股解析失敗: {str(e)}"
        }

@app.get("/api/recommendations")
async def get_recommendations():
    # Fetch today's data and get the top 50 performing stocks with decent trade value
    df = get_twse_data()
    # Filter for stocks with positive change and sort by TradeValue and ChangePct combined or just ChangePct
    top_stocks = df[df['ChangePct'] > 2].sort_values(by=['TradeValue', 'ChangePct'], ascending=[False, False]).head(80)
    
    candidates = []
    for _, row in top_stocks.iterrows():
        candidates.append(f"{row['Name']}({row['Code']}) - 產業: {row['Industry']}, 收盤: {row['ClosingPrice']}, 漲幅: {row['ChangePct']:.2f}%, 成交金額: {row['TradeValue']}")
        
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or api_key == "YOUR_API_KEY_HERE":
         return {
            "success": False,
            "error": "API Key 未設定，請在後端終端機設定 GEMINI_API_KEY 環境變數。"
        }
        
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        prompt = f"""
        你是一位極具經驗的台股分析師。以下是今日市場上表現強勢且成交量較大的前 80 檔候選股票：
        
        {chr(10).join(candidates)}
        
        請你從上述候選名單中，根據你的市場經驗與基本分析，精挑細選出 5 到 10 檔「明日推薦個股」。
        請直接輸出 Markdown 格式的綜合報告，並使用「表格」呈現，表格欄位必須包含：
        1. 股號 / 股名
        2. 產業類型
        3. 推薦原因 (請綜合推測與評估技術面、籌碼面或基本面等利多)
        4. 明日強勢預估分數 (1-100分，愈高代表明日愈可能續強或噴出)
        
        在表格之後，請加上一段簡短的「操作風險提示」。
        不要有任何多餘的引言廢話，直接給我精美的 Markdown 表格與提示。
        """
        for attempt in range(3):
            try:
                response = model.generate_content(prompt)
                return {
                    "success": True,
                    "ai_report": response.text
                }
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    time.sleep(20)
                else:
                    raise e
    except Exception as e:
        return {
            "success": False,
            "error": f"AI 推薦解析失敗: {str(e)}"
        }

# Mount frontend folder for static serving
frontend_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    print(f"Warning: Frontend directory not found at {frontend_path}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
