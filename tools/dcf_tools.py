import yfinance as yf
import pandas as pd
import numpy as np

# Override user-agent to prevent blocking
import requests
_original_get_json = yf.utils.get_json if hasattr(yf.utils, 'get_json') else None
if _original_get_json:
    yf.utils.get_json = lambda url, proxy=None, headers=None: requests.get(url, proxies=proxy, headers={'User-agent': 'Mozilla/5.0'}).json()

def _get_series(df, potential_keys):
    """Helper to find a column matching one of the keys."""
    for key in potential_keys:
        if key in df.columns:
            return df[key]
    return None

def get_financial_data(ticker_symbol):
    ticker = yf.Ticker(ticker_symbol)
    try:
        financials = ticker.financials.T.sort_index()
        balance_sheet = ticker.balance_sheet.T.sort_index()
        cashflow = ticker.cashflow.T.sort_index()
    except Exception as e:
        return {"error": f"Failed to fetch statements: {str(e)}"}

    if financials.empty or balance_sheet.empty or cashflow.empty:
        return {"error": "Insufficient data"}

    revenue = _get_series(financials, ['Total Revenue', 'Revenue'])
    ebit = _get_series(financials, ['Operating Income', 'EBIT'])
    
    capex = _get_series(cashflow, ['Capital Expenditure', 'Capital Expenditures'])
    if capex is not None: capex = capex.abs()
        
    dep_amort = _get_series(cashflow, ['Depreciation And Amortization', 'Depreciation', 'Depreciation & Amortization'])
    delta_wc = _get_series(cashflow, ['Change In Working Capital', 'Changes In Working Capital'])

    total_debt = _get_series(balance_sheet, ['Total Debt', 'Long Term Debt And Capital Lease Obligation'])
    cash_equivalents = _get_series(balance_sheet, ['Cash And Cash Equivalents', 'Cash & Cash Equivalents'])

    try:
        info = ticker.info
        beta = info.get('beta', 1.0)
        shares = info.get('sharesOutstanding', 0)
        price = info.get('currentPrice', 0)
        market_cap = info.get('marketCap', shares * price)
    except:
        beta, shares, price, market_cap = 1.0, 0, 0, 0

    try:
        tnx = yf.Ticker("^TNX")
        risk_free_rate = tnx.history(period="1d")['Close'].iloc[-1] / 100.0
    except:
        risk_free_rate = 0.04

    ie = _get_series(financials, ['Interest Expense'])
    if ie is None: ie = 0

    hist_df = pd.DataFrame({
        'Revenue': revenue,
        'EBIT': ebit,
        'Depreciation': dep_amort,
        'CapEx': capex,
        'Change in WC': delta_wc,
        'Tax Provision': _get_series(financials, ['Tax Provision', 'Income Tax Expense']),
        'Interest Expense': ie,
        'Pretax Income': _get_series(financials, ['Pretax Income', 'Pre-Tax Income'])
    }).apply(pd.to_numeric, errors='coerce').fillna(0)

    hist_df['EBIT Margin'] = hist_df['EBIT'] / hist_df['Revenue'].replace(0, np.nan)
    ebit_minus_int = hist_df['EBIT'] - hist_df['Interest Expense']
    hist_df['Tax Rate'] = (hist_df['Tax Provision'] / ebit_minus_int.replace(0, np.nan)).fillna(0.21)

    implied_cod = 0.05
    try:
        if (total_debt is not None) and (total_debt.iloc[-1] > 0) and (hist_df['Interest Expense'].iloc[-1] > 0):
            implied_cod = hist_df['Interest Expense'].iloc[-1] / total_debt.iloc[-1]
    except: pass

    return {
        'historicals': hist_df,
        'beta': beta,
        'shares_outstanding': shares,
        'market_cap': market_cap,
        'risk_free_rate': risk_free_rate,
        'total_debt': total_debt.iloc[-1] if total_debt is not None and not total_debt.empty else 0,
        'cash': cash_equivalents.iloc[-1] if cash_equivalents is not None and not cash_equivalents.empty else 0,
        'implied_cost_of_debt': implied_cod
    }

def get_granular_dcf_inputs(ticker_symbol):
    data = get_financial_data(ticker_symbol)
    if "error" in data: return None
    hist = data['historicals']
    
    hist['Revenue Growth'] = hist['Revenue'].pct_change()
    hist['CapEx % Rev'] = hist['CapEx'] / hist['Revenue'].replace(0, np.nan)
    hist['NWC Change % Rev'] = hist['Change in WC'] / hist['Revenue'].replace(0, np.nan)
    hist['DA % Rev'] = hist['Depreciation'] / hist['Revenue'].replace(0, np.nan)
    
    recent = hist.tail(3)
    drivers = {
        "revenue": hist['Revenue'].iloc[-1] if not hist.empty else 0,
        "growth_rate": recent['Revenue Growth'].mean(),
        "ebit_margin": recent['EBIT Margin'].mean(),
        "tax_rate": recent['Tax Rate'].mean(),
        "capex_percent": recent['CapEx % Rev'].mean(),
        "nwc_percent": recent['NWC Change % Rev'].mean(),
        "da_percent": recent['DA % Rev'].mean(),
        "net_debt": data['total_debt'] - data['cash'],
        "shares": data['shares_outstanding'],
        "beta": data['beta'],
        "market_cap": data['market_cap'],
        "risk_free_rate": data['risk_free_rate'],
        "implied_cost_of_debt": data['implied_cost_of_debt']
    }
    for k, v in drivers.items():
        if pd.isna(v): drivers[k] = 0.0
    if drivers['tax_rate'] <= 0 or drivers['tax_rate'] > 0.5: drivers['tax_rate'] = 0.21
    return drivers

def generate_auto_dcf_model(ticker: str) -> str:
    """
    Autonomously fetches all historical granular financial data for a ticker, extracts logical assumptions from the 
    last 3 years (Revenue Growth, EBIT Margin, CapEx, WACC), and projects an intrinsic 5-year DCF valuation!
    Use this to mathematically settle debates about a company's true value based on live data!
    Returns the explicitly calculated intrinsic share price along with all the key assumptions used.
    """
    try:
        inputs = get_granular_dcf_inputs(ticker)
        if not inputs:
            return f"Failed to acquire necessary data for {ticker} to build DCF."

        # 1. WACC Calculation
        cost_of_equity = inputs['risk_free_rate'] + (inputs['beta'] * 0.05) # 5% ERP
        total_value = inputs['market_cap'] + inputs['net_debt'] + inputs.get('cash', 0)
        if total_value == 0: total_value = 1
        
        weight_equity = inputs['market_cap'] / total_value
        weight_debt = max(0, (total_value - inputs['market_cap']) / total_value)
        wacc = (weight_equity * cost_of_equity) + (weight_debt * inputs['implied_cost_of_debt'] * (1 - inputs['tax_rate']))
        
        if wacc < 0.05: wacc = 0.08 # Safe floor

        # 2. Granular 5-Year Projection DCF Loop
        wacc_discount = wacc
        terminal_g = 0.02 # 2% perpetual growth assumption
        proj_years = 5
        
        current_rev = inputs['revenue']
        discounted_fcfs = []
        proj_fcf = []
        
        for year in range(1, proj_years + 1):
            current_rev *= (1 + inputs['growth_rate'])
            ebit = current_rev * inputs['ebit_margin']
            taxes = ebit * inputs['tax_rate']
            nopat = ebit - taxes
            
            capex = current_rev * inputs['capex_percent']
            nwc_change = current_rev * inputs['nwc_percent']
            dep = current_rev * inputs['da_percent']
            
            fcf = nopat + dep - capex - nwc_change
            proj_fcf.append(fcf)
            
            df = 1 / ((1 + wacc_discount) ** year)
            discounted_fcfs.append(fcf * df)

        # 3. Terminal Value
        safe_g = min(terminal_g, wacc_discount - 0.005)
        terminal_value = (proj_fcf[-1] * (1 + safe_g)) / (wacc_discount - safe_g)
        pv_tv = terminal_value * (1 / ((1 + wacc_discount) ** proj_years))
        
        enterprise_value = sum(discounted_fcfs) + pv_tv
        equity_value = max(0, enterprise_value - inputs['net_debt'])
        
        price = 0
        if inputs['shares'] > 0:
            price = equity_value / inputs['shares']

        return (
            f"Autonomous DCF Valuation Build Complete for {ticker}:\n"
            f"--- Extracted Assumptions (3Y Averages) ---\n"
            f"Revenue Growth: {inputs['growth_rate']*100:.1f}%\n"
            f"EBIT Margin: {inputs['ebit_margin']*100:.1f}%\n"
            f"Tax Rate: {inputs['tax_rate']*100:.1f}%\n"
            f"Reinvestment (CapEx/DA/NWC): {(inputs['capex_percent']+inputs['nwc_percent'])*100:.1f}% Rev\n\n"
            f"--- Capital Structure & Discount Rate ---\n"
            f"Beta: {inputs['beta']:.2f}\n"
            f"Risk Free Rate: {inputs['risk_free_rate']*100:.1f}%\n"
            f"WACC: {wacc*100:.1f}%\n"
            f"Terminal Growth Rate: {safe_g*100:.1f}%\n\n"
            f"--- Intrinsic Valuation ---\n"
            f"Enterprise Value: ${enterprise_value/1e9:.2f}B\n"
            f"Implied Equity Value: ${equity_value/1e9:.2f}B\n"
            f"Intrinsic Price Target: ${price:.2f} per share\n"
        )

    except Exception as e:
        return f"Error computing Auto-DCF for {ticker}: {str(e)}"

def get_dcf_tools():
    """
    Exports the DCF suite for the swarm.
    """
    return [
        generate_auto_dcf_model
    ]
