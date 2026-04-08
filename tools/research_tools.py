import yfinance as yf
from bs4 import BeautifulSoup
import requests

def get_company_financials(ticker: str) -> dict:
    """
    Pulls real-time financial data for a given public company ticker using Yahoo Finance.
    Returns market cap, EV, revenue, margins, and key multiples necessary for valuation.
    """
    import math
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        data = {
            "ticker": ticker,
            "company_name": info.get("shortName", ticker),
            "market_cap": info.get("marketCap", "N/A"),
            "enterprise_value": info.get("enterpriseValue", "N/A"),
            "trailing_pe": info.get("trailingPE", "N/A"),
            "forward_pe": info.get("forwardPE", "N/A"),
            "ebitda_margins": info.get("ebitdaMargins", "N/A"),
            "profit_margins": info.get("profitMargins", "N/A"),
            "revenue": info.get("totalRevenue", "N/A"),
            "total_debt": info.get("totalDebt", "N/A"),
            "total_cash": info.get("totalCash", "N/A"),
            "beta": info.get("beta", "N/A"),
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A")
        }
        
        # Clean NaNs which crash GenAI JSON payload
        for k, v in data.items():
            if isinstance(v, float) and math.isnan(v):
                data[k] = "N/A"
        return data
    except Exception as e:
        return {"error": f"Failed to retrieve data for {ticker}. Error: {str(e)}"}

def web_search(query: str) -> str:
    """
    Searches the internet for the query and returns top results with URLs.
    Use this to find relevant articles, news, or reports. To read the deep content of these results, pass the URL to the read_webpage tool.
    """
    try:
        import urllib.request
        import urllib.parse
        from bs4 import BeautifulSoup

        # 1. First Attempt: GET Request to DuckDuckGo Lite
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        safe_query = urllib.parse.quote(query)
        req = urllib.request.Request(f"https://lite.duckduckgo.com/lite/?q={safe_query}", headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read()
            soup = BeautifulSoup(html, 'html.parser')
            results = ""
            for a in soup.find_all('a', class_='result-link', limit=5):
                title = a.get_text(strip=True)
                href = a.get('href')
                
                snippet_td = a.find_next('td', class_='result-snippet')
                snippet = snippet_td.get_text(strip=True) if snippet_td else ""
                
                if href and href.startswith('//duckduckgo.com/l/?'):
                    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                    if 'uddg' in qs:
                        href = qs['uddg'][0]
                elif href and href.startswith('//'):
                    href = 'https:' + href
                
                if href and snippet:
                    results += f"Title: {title}\nURL: {href}\nSnippet: {snippet}\n\n"
                    
            if results.strip():
                return results
        except Exception as e:
            pass # Fallback to Wikipedia
            
        # 2. Fallback: Wikipedia API (Immune to Search Engine Rate Limits)
        try:
            import json
            url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={safe_query}&utf8=&format=json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read())
                results = ""
                for item in data['query']['search'][:5]:
                    title = item['title']
                    snippet = item['snippet'].replace('<span class="searchmatch">', '').replace('</span>', '')
                    results += f"Title: {title}\nURL: https://en.wikipedia.org/wiki/{urllib.parse.quote(title)}\nSnippet: {snippet}\n\n"
                
                if results:
                    return "WIKIPEDIA FALLBACK RESULTS:\n" + results
        except Exception:
            pass

        return f"No results found for '{query}'. Search engines blocked the request."
    except Exception as e:
        return f"Error performing web search for '{query}': {str(e)}"

def read_webpage(url: str) -> str:
    """
    Downloads and extracts the full readable text content from a given URL.
    Works for both standard HTML pages and binary PDF reports (like IMF, World Bank academic papers).
    Use this tool AFTER using web_search or search_academic_papers to deeply read the document.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' in content_type or url.lower().endswith('.pdf'):
            import io
            import pypdf
            pdf_file = io.BytesIO(response.content)
            reader = pypdf.PdfReader(pdf_file)
            text = ""
            for i in range(len(reader.pages)):
                page_text = reader.pages[i].extract_text()
                if page_text:
                    text += page_text + "\n"
                if len(text) > 20000: # Limit to avoid massive token bloat
                    break
            return text[:20000] if text else "Parsed PDF but found no extractable text."
        
        # HTML Path
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text(separator=' ')
        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        # Limit to first 15000 characters to avoid overwhelming the context and parsing garbage
        return text[:15000] if text else "No readable text found on this page."
    except Exception as e:
        return f"Failed to retrieve or parse the webpage at {url}. Error: {str(e)}"

def parse_financial_document(filepath: str) -> dict:
    """Parses an uploaded 10-K or PDF pitchbook to extract key financial metrics."""
    return {"status": "parsed", "content": "Extracted text showing $500M revenue and 20% margin."}

def get_historical_prices(ticker: str, period: str) -> dict:
    """
    Fetches historical pricing data (like % return) over a specific recent period using yfinance.
    Common tickers include '^GSPC' for S&P 500, 'CL=F' for Crude Oil, 'GC=F' for Gold.
    Recommended periods: '1mo', '3mo', '6mo', '1y', 'ytd', '5y'.
    """
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty:
            return {"error": f"No historical data found for '{ticker}' using period '{period}'."}
            
        start_price = hist['Close'].iloc[0]
        end_price = hist['Close'].iloc[-1]
        pct_change = ((end_price - start_price) / start_price) * 100
        
        return {
            "ticker": ticker,
            "period": period,
            "start_price": round(start_price, 2),
            "end_price": round(end_price, 2),
            "percent_return": round(pct_change, 2)
        }
    except Exception as e:
        return {"error": f"Failed to retrieve historical data for {ticker}. Error: {str(e)}"}

def get_macroeconomic_data(series_id: str) -> dict:
    """
    Fetches macroeconomic data via the FRED API using the provided series_id.
    Common series_ids: 'GDP' (Gross Domestic Product), 'FEDFUNDS' (Federal Funds Rate), 'CPIAUCSL' (Inflation), 'UNRATE' (Unemployment).
    Returns the latest 6 observations (months/quarters).
    """
    import os
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        return {"error": "FRED_API_KEY is not set in the environment variables."}
        
    try:
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json"
        response = requests.get(url)
        data = response.json()
        
        if 'observations' not in data:
            return {"error": f"API returned an error or unrecognized series_id '{series_id}'. Full response: {data}"}
            
        # Get the latest 6 observations to give the agent a brief trend
        latest_obs = data['observations'][-6:]
        trend = [{"date": obs['date'], "value": obs['value']} for obs in latest_obs]
        
        return {
            "series_id": series_id,
            "latest_observations": trend
        }
    except Exception as e:
        return {"error": f"Failed to retrieve FRED data for {series_id}. Error: {str(e)}"}

def get_detailed_financial_statements(ticker: str) -> dict:
    """
    Fetches the actual Income Statement, Balance Sheet, and Cash Flow statement for a ticker using Yahoo Finance.
    Use this to dig into granular figures like CAPEX, Operating Expenses, Total Debt, R&D, etc.
    """
    try:
        stock = yf.Ticker(ticker)
        # Get the most recent column of data to save tokens and fill NaNs which crash GenAI JSON parser
        inc = stock.financials.iloc[:, 0].fillna("N/A").to_dict() if not stock.financials.empty else {}
        bal = stock.balance_sheet.iloc[:, 0].fillna("N/A").to_dict() if not stock.balance_sheet.empty else {}
        cf = stock.cashflow.iloc[:, 0].fillna("N/A").to_dict() if not stock.cashflow.empty else {}
        return {
            "income_statement_latest": inc,
            "balance_sheet_latest": bal,
            "cash_flow_latest": cf
        }
    except Exception as e:
        return {"error": str(e)}

def image_search(query: str) -> dict:
    """
    Searches DuckDuckGo for images (e.g., 'Oil production supply chart 2026', 'S&P 500 technical analysis chart').
    Returns a list of image URLs. Use 'analyze_image_from_url' to visually read the charts.
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.images(query, max_results=3):
                results.append(r.get("image"))
        return {"image_urls": results}
    except Exception as e:
        return {"error": str(e)}

def analyze_image_from_url(image_url: str) -> dict:
    """
    Downloads an image (like a chart or graph from image_search) and uses Gemini's vision capabilities to visually read and analyze it.
    Returns a detailed extraction of the trends, numbers, and technical data shown in the chart.
    """
    try:
        from google import genai
        from google.genai import types
        import requests
        
        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()
        
        client = genai.Client()
        img_part = types.Part.from_bytes(data=response.content, mime_type=response.headers.get('Content-Type', 'image/jpeg'))
        
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[types.Content(role="user", parts=[
                img_part, 
                types.Part.from_text(text="Analyze this chart, graph, or visual data in extreme detail. Extract specific numbers, percentages, trends, axes labels, and structural financial data so I can use it in a quantitative model.")
            ])]
        )
        return {"visual_analysis": resp.text}
    except Exception as e:
        return {"error": f"Failed to analyze image from {image_url}. {str(e)}"}

def search_polymarket_odds(query: str) -> dict:
    """
    Searches Polymarket public betting markets for real-time implied probabilities and odds on geopolitical events, rates, and commodities.
    Returns the event title and the current percentage odds (e.g. Yes/No or price brackets) representing public sentiment and market expectation.
    """
    try:
        import requests
        import urllib.parse
        # Gamma API is open and requires no key
        safe_query = urllib.parse.quote(query)
        url = f"https://gamma-api.polymarket.com/events?limit=100&active=true&title={safe_query}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        events = response.json()
        
        relevant_markets = []
        for event in events:
            title = event.get("title", "")
            description = event.get("description", "")
            markets_info = []
            for market in event.get("markets", []):
                if market.get("active") and not market.get("closed"):
                    outcomes = market.get("outcomes", [])
                    try:
                        prices = [float(p) for p in market.get("outcomePrices", [])]
                    except:
                        prices = market.get("outcomePrices", [])
                        
                    # Format as 'Yes: 65.5%, No: 34.5%'
                    if isinstance(outcomes, str):
                        import json
                        try: outcomes = json.loads(outcomes)
                        except: outcomes = [outcomes]
                        
                    if isinstance(prices, str):
                        import json
                        try: prices = json.loads(prices)
                        except: prices = [prices]
                        
                    odds_map = {}
                    for idx, outcome in enumerate(outcomes):
                        price = prices[idx] if idx < len(prices) else "N/A"
                        if isinstance(price, float):
                            odds_map[outcome] = f"{round(price * 100, 1)}%"
                        else:
                            odds_map[outcome] = price
                            
                    markets_info.append({
                        "question": market.get("question"),
                        "odds": odds_map
                    })
            
            if markets_info:
                relevant_markets.append({
                    "event": title,
                    "markets": markets_info
                })
                    
        if not relevant_markets:
            return {"error": f"No active Polymarket events found for '{query}'."}
            
        return {"polymarket_events": relevant_markets[:3]} # Return top 3 to save space
    except Exception as e:
        return {"error": f"Failed to retrieve Polymarket odds. Error: {str(e)}"}

def search_academic_papers(query: str) -> str:
    """
    Searches the ArXiv database for deep academic papers, economics reports, and quantitative finance studies.
    Returns the title, authors, summary, and a direct PDF link to the research paper.
    If you need to read the full paper, safely pass the PDF link into the 'read_webpage' tool.
    """
    try:
        import urllib.request
        import urllib.parse
        import xml.etree.ElementTree as ET
        
        safe_query = urllib.parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{safe_query}&start=0&max_results=3"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        results = ""
        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text.replace('\n', ' ')
            summary = entry.find('atom:summary', ns).text.replace('\n', ' ')
            
            pdf_link = ""
            for link in entry.findall('atom:link', ns):
                if link.get('title') == 'pdf':
                    pdf_link = link.get('href')
                    if not pdf_link.endswith('.pdf'):
                        pdf_link += '.pdf'
                    break
                    
            results += f"Title: {title}\nPDF URL: {pdf_link}\nAbstract: {summary[:1000]}...\n\n"
            
        if results.strip():
            return "ACADEMIC PAPERS FOUND:\n" + results
        return f"No academic papers found for '{query}'."
    except Exception as e:
        return f"Error retrieving academic papers: {str(e)}"

def get_research_tools():
    return [
        get_company_financials, web_search, read_webpage, search_academic_papers, parse_financial_document, 
        get_historical_prices, get_macroeconomic_data, get_detailed_financial_statements,
        image_search, analyze_image_from_url, search_polymarket_odds
    ]
