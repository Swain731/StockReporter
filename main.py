import requests
import pandas as pd
import numpy as np
import os
import sys
import google.generativeai as genai
from datetime import datetime
import json

# Fix Windows console emoji printing issue
sys.stdout.reconfigure(encoding='utf-8')

def get_twse_data():
    print("1/3 抓取上市股票每日收盤行情...")
    url_quotes = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    res_quotes = requests.get(url_quotes)
    df_quotes = pd.DataFrame(res_quotes.json())
    
    print("2/3 抓取上市公司產業別資料...")
    url_info = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
    res_info = requests.get(url_info)
    df_info = pd.DataFrame(res_info.json())
    
    # Clean and merge
    df_info = df_info[['公司代號', '產業別']].rename(columns={'公司代號': 'Code', '產業別': 'Industry'})
    df = pd.merge(df_quotes, df_info, on='Code', how='inner')
    
    # Parse numbers
    def parse_float(val):
        try:
            return float(str(val).replace(',', ''))
        except:
            return np.nan
            
    df['ClosingPrice'] = df['ClosingPrice'].apply(parse_float)
    df['Change'] = df['Change'].apply(parse_float)
    df['TradeValue'] = df['TradeValue'].apply(parse_float)
    
    # Calculate change %
    df['PrevClose'] = df['ClosingPrice'] - df['Change']
    df['ChangePct'] = np.where(df['PrevClose'] > 0, (df['Change'] / df['PrevClose']) * 100, 0)
    
    return df.dropna(subset=['ClosingPrice', 'ChangePct', 'Industry'])

def analyze_market(df):
    print("3/3 分析強勢族群...")
    df = df[df['Industry'] != '']
    
    # Group by industry
    industry_stats = df.groupby('Industry').agg(
        AvgChangePct=('ChangePct', 'mean'),
        TotalTradeValue=('TradeValue', 'sum'),
        StockCount=('Code', 'count')
    ).reset_index()
    
    # Filter minimum stock count and find top 3 strongest
    industry_stats = industry_stats[industry_stats['StockCount'] >= 3]
    strong_industries = industry_stats.sort_values(by='AvgChangePct', ascending=False).head(3)
    
    report_data = []
    for _, row in strong_industries.iterrows():
        ind = row['Industry']
        # Top 5 gainers in this industry
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

def generate_ai_report(report_data):
    # Set your Gemini API key here or via env variable
    api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyAUO6tmExk2fusBfdc0DZrtfIvbifCS6FQ")
    
    if not api_key:
        print("\n==== 🏆 本日台股強勢族群報告 (資料版) ====")
        for d in report_data:
            print(f"[{d['Industry']}] 平均漲幅: {d['AvgChangePct']:.2f}%")
            print("  指標股:")
            for s in d['TopStocks']:
                print(f"  - {s}")
            print("-" * 30)
        print("\n💡 提示: 設定 GEMINI_API_KEY 以便由 AI 自動生成預測與分析概要。")
        return

    print("🤖 正在呼叫 AI 進行預期與概要分析...")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
    你是專業的台灣股市分析師。以下是 {today_str} 台灣股市當天最強勢的族群資料：\n
    """
    for d in report_data:
        prompt += f"族群：{d['Industry']} (平均漲幅: {d['AvgChangePct']:.2f}%)\n"
        prompt += f"強勢股：{', '.join(d['TopStocks'])}\n\n"
        
    prompt += """
    請根據上述資料，直接撰寫一份簡潔專業的盤後報告：
    【今日強勢分析】：結合近期總經或產業趨勢，說明這些族群為何今日轉強。
    【明日預估】：預估明日這些資金是否延續，或者可能輪動到哪個特定族群，並說明理由。
    【重點持股建議】：對列表中的領頭羊給出簡短的操作與風險提醒。
    不要寫任何廢話，直接給重點。
    """
    
    try:
        response = model.generate_content(prompt)
        print("\n" + "="*50)
        print(f"📊 股市 AI 報告 ({today_str}) ".center(50))
        print("="*50)
        print(response.text)
    except Exception as e:
        print(f"AI 解析失敗: {e}")

if __name__ == "__main__":
    df = get_twse_data()
    report_data = analyze_market(df)
    generate_ai_report(report_data)
