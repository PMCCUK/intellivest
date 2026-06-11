#!/usr/bin/env python3
"""
IntelliVest AI Engine
Runs on GitHub Actions server on schedule.
Fetches live market data, runs Claude AI analysis,
saves results as JSON for the dashboard to read.
"""

import json
import os
import sys
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
import anthropic

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
FINNHUB_KEY   = os.environ.get('FINNHUB_API_KEY', '')
FORCE_RUN     = os.environ.get('FORCE_RUN', 'false').lower() == 'true'
MODEL         = 'claude-haiku-4-5-20251001'
DATA_DIR      = Path('data')

DATA_DIR.mkdir(exist_ok=True)

# ── Market hours check ────────────────────────────────────────────────────────

def is_market_open():
    """Check if US market is currently open (9:30-16:00 EST, Mon-Fri)"""
    from datetime import timezone as tz
    import datetime as dt

    # Get current EST time
    utc_now = datetime.now(timezone.utc)
    est_offset = dt.timedelta(hours=-5)  # EST (no DST adjustment for simplicity)
    est_now = utc_now + est_offset

    if est_now.weekday() >= 5:  # Weekend
        return False, 'weekend'

    market_open  = est_now.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = est_now.replace(hour=16, minute=0,  second=0, microsecond=0)

    if market_open <= est_now <= market_close:
        return True, 'open'
    elif est_now < market_open:
        return False, 'pre-market'
    else:
        return False, 'after-hours'

# ── Market data ───────────────────────────────────────────────────────────────

def fetch_quote(symbol: str) -> dict | None:
    """Fetch live quote from Finnhub"""
    if not FINNHUB_KEY:
        return None
    try:
        r = requests.get(
            f'https://finnhub.io/api/v1/quote',
            params={'symbol': symbol, 'token': FINNHUB_KEY},
            timeout=8
        )
        d = r.json()
        if d.get('c', 0) > 0:
            return {
                'symbol': symbol,
                'price': d['c'],
                'change': d['d'],
                'changePct': d['dp'],
                'open': d['o'],
                'high': d['h'],
                'low': d['l'],
                'prev': d['pc'],
            }
    except Exception as e:
        print(f'  Quote error {symbol}: {e}')
    return None

def fetch_batch_quotes(symbols: list[str], delay: float = 0.12) -> dict:
    """Fetch multiple quotes with rate limiting"""
    results = {}
    for sym in symbols:
        q = fetch_quote(sym)
        if q:
            results[sym] = q
        time.sleep(delay)  # Respect Finnhub 60/min limit
    return results

def fetch_news_rss() -> list[dict]:
    """Fetch latest financial news from free RSS feeds"""
    feeds = [
        ('Reuters', 'https://feeds.reuters.com/reuters/businessNews'),
        ('MarketWatch', 'https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines'),
        ('Yahoo Finance', 'https://finance.yahoo.com/news/rssindex'),
    ]

    headlines = []
    for source, url in feeds:
        try:
            proxy = f'https://api.allorigins.win/raw?url={requests.utils.quote(url)}'
            r = requests.get(proxy, timeout=8)

            # Simple XML title extraction
            import re
            titles = re.findall(r'<title><!\[CDATA\[(.+?)\]\]></title>|<title>(.+?)</title>', r.text)
            for t in titles[:8]:
                title = (t[0] or t[1]).strip()
                if title and len(title) > 20 and 'RSS' not in title:
                    headlines.append({'title': title, 'source': source})
        except Exception as e:
            print(f'  News error {source}: {e}')

    return headlines[:20]

# ── AI Engine ─────────────────────────────────────────────────────────────────

STRATEGIES = {
    'master': {
        'name': 'AI Master',
        'symbols': ['AAPL','MSFT','NVDA','GOOGL','AMZN','META','JPM','V',
                    'JNJ','XOM','SPY','QQQ','GLD','TSLA','AVGO','AMD'],
        'prompt': 'You are a balanced institutional portfolio manager. Identify the best risk-adjusted opportunities.',
    },
    'growth': {
        'name': 'AI Growth',
        'symbols': ['NVDA','MSFT','GOOGL','META','AMZN','AVGO','AMD','TSLA',
                    'NFLX','CRM','SNOW','PLTR','ASML','TSM'],
        'prompt': 'You are a global growth fund manager focused on technology, AI, and high-growth companies.',
    },
    'value': {
        'name': 'AI Value',
        'symbols': ['JPM','BAC','V','JNJ','PFE','XOM','CVX','WMT','KO','MCD',
                    'BRK-B','ABBV','MRK','GS','MS'],
        'prompt': 'You are a value fund manager focused on undervalued stocks with strong fundamentals.',
    },
    'momentum': {
        'name': 'AI Momentum',
        'symbols': ['SPY','QQQ','XLK','XLF','XLE','XLV','XLI','GLD','TLT','IWM',
                    'VWO','EEM','DBA','USO','BITO','GBTC','MSTR'],
        'prompt': 'You are a momentum fund manager focused on trend-following, sector rotation, ETFs, commodities, and crypto proxies.',
    },
    'uk': {
        'name': 'AI UK & Europe',
        'symbols': ['AZN','SHEL','GSK','ULVR.L','BARC.L','LLOY.L',
                    'ASML','SAP','NESN.SW','EWU','EWG','EFA'],
        'prompt': 'You are a UK and European equity fund manager. Focus on FTSE 100 and European leaders.',
    },
    'crypto': {
        'name': 'AI Crypto',
        # Use stock-market listed crypto proxies — Finnhub free supports these
        # BTC-USD etc. don't work on Finnhub free; use ETFs and mining stocks instead
        'symbols': ['GBTC','ETHE','BITO','MARA','RIOT','HUT','BITF','CIFR',
                    'COIN','MSTR','CLSK','BTBT','WGMI','IBIT','FBTC'],
        'prompt': 'You are a crypto and digital assets fund manager using crypto-proxy stocks and ETFs (GBTC=Bitcoin trust, ETHE=Ethereum trust, BITO=Bitcoin futures ETF, MARA/RIOT/HUT=Bitcoin miners, COIN=Coinbase, MSTR=MicroStrategy). Analyse momentum and crypto market correlation. Be cautious of high volatility.',
    },
    'smallcap': {
        'name': 'AI Small Cap',
        # Actively traded small caps with Finnhub free coverage — removed delisted tickers
        'symbols': ['MARA','RIOT','CIFR','CLSK','BTBT',
                    'APPS','PUBM','DV','CREX','SOUN',
                    'MNMD','CMPS','ATAI','NVAX','SNDL',
                    'NIO','XPEV','LI','RIVN','LCID',
                    'TLRY','CGC','ACB','CRON',
                    'ACMR','AEHR','KRTX','RCKT','VERA'],
        'prompt': 'You are a small-cap specialist. Only buy when Opportunity >75, Confidence >70, Risk <45. Focus on stocks showing unusual volume, momentum, or catalyst. These are higher risk — be selective.',
    },
}

def run_strategy(client: anthropic.Anthropic, strategy_id: str, strategy: dict,
                 quotes: dict, news_headlines: list, portfolio_state: dict,
                 config: dict) -> dict:
    """Run AI analysis for one strategy"""

    price_lines = []
    for sym in strategy['symbols']:
        q = quotes.get(sym)
        if q:
            price_lines.append(
                f"{sym}: £{q['price']:.2f} ({'+' if q['changePct']>=0 else ''}{q['changePct']:.2f}%)"
            )

    if not price_lines:
        print(f'  {strategy["name"]}: No price data available, skipping')
        return {}

    news_ctx = '\n'.join(f"- {n['title']} ({n['source']})" for n in news_headlines[:8])
    holdings = ', '.join(portfolio_state.get('positions', {}).get(strategy_id, [])) or 'None'
    balance = portfolio_state.get('balances', {}).get(strategy_id, 100000)

    min_opp  = config.get('minOpp', 80)
    min_conf = config.get('minConf', 75)
    max_risk = config.get('maxRisk', 40)

    prompt = f"""{strategy['prompt']}

PORTFOLIO STATE:
- Cash available: £{balance:,.2f}
- Open positions: {holdings}

LIVE MARKET DATA:
{chr(10).join(price_lines)}

RECENT NEWS:
{news_ctx or 'No news available'}

RULES: Only BUY if Opportunity>{min_opp} AND Confidence>{min_conf} AND Risk<{max_risk}.
Max position: {config.get('maxPosPct', 5)}% of portfolio. Max {config.get('maxPositions', 15)} positions.

Respond ONLY with valid JSON (no markdown):
{{
  "decisions": [
    {{
      "action": "BUY" or "SELL" or "HOLD",
      "symbol": "<TICKER>",
      "qty_pct": <1-{config.get('maxPosPct', 5)}>,
      "opportunityScore": <0-100>,
      "riskScore": <0-100>,
      "confidenceScore": <0-100>,
      "reasoning": "<why — 1 sentence>"
    }}
  ],
  "assessment": "<1 sentence market view for this strategy>"
}}"""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = response.content[0].text if response.content else ''

        # Strip markdown if present
        text = text.replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        result['strategy'] = strategy_id
        result['strategy_name'] = strategy['name']
        result['timestamp'] = datetime.now(timezone.utc).isoformat()
        result['prices_used'] = {sym: quotes[sym]['price'] for sym in strategy['symbols'] if sym in quotes}
        return result
    except Exception as e:
        print(f'  {strategy["name"]} AI error: {e}')
        return {
            'strategy': strategy_id,
            'strategy_name': strategy['name'],
            'decisions': [],
            'assessment': f'Engine error: {str(e)[:80]}',
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

# ── Daily Insight ─────────────────────────────────────────────────────────────

def generate_daily_insight(client: anthropic.Anthropic, quotes: dict,
                           news_headlines: list) -> dict:
    """Generate the morning AI briefing"""

    index_lines = '\n'.join(
        f"{sym}: £{q['price']:.2f} ({'+' if q['changePct']>=0 else ''}{q['changePct']:.2f}%)"
        for sym, q in quotes.items()
        if sym in ['SPY','QQQ','DIA','IWM','GLD','TLT']
    )

    news_ctx = '\n'.join(f"[{n['source']}] {n['title']}" for n in news_headlines[:12])

    prompt = f"""You are a senior investment research analyst. Generate today's morning briefing.

MARKET INDICES:
{index_lines or 'Data unavailable'}

NEWS:
{news_ctx or 'No news available'}

Respond ONLY with valid JSON:
{{
  "marketSummary": "<3 sentence overall market assessment>",
  "topOpportunities": [
    {{"symbol":"<TICKER>","name":"<Name>","reason":"<why>","score":<50-100>,"riskScore":<0-100>,"confidenceScore":<0-100>,"historicalComparison":"<brief>"}}
  ],
  "topRisks": [
    {{"symbol":"<TICKER>","name":"<Name>","reason":"<why>","riskLevel":"LOW|MEDIUM|HIGH|CRITICAL","riskScore":<50-100>}}
  ],
  "bullishSectors": [{{"sector":"<name>","score":<50-100>,"reason":"<why>"}}],
  "bearishSectors":  [{{"sector":"<name>","score":<0-50>, "reason":"<why>"}}],
  "keyEvents": ["<event 1>","<event 2>"]
}}
Provide 8 opportunities, 8 risks, 3 bullish, 2 bearish."""

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2500,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = response.content[0].text if response.content else ''
        text = text.replace('```json', '').replace('```', '').strip()
        result = json.loads(text)
        result['date'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        result['generatedAt'] = datetime.now(timezone.utc).isoformat()
        return result
    except Exception as e:
        print(f'  Daily insight error: {e}')
        return {
            'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            'marketSummary': f'Insight generation error: {str(e)[:100]}',
            'topOpportunities': [], 'topRisks': [],
            'bullishSectors': [], 'bearishSectors': [], 'keyEvents': [],
        }

# ── Persistence helpers ───────────────────────────────────────────────────────

def load_state() -> dict:
    """Load existing portfolio state from data/state.json"""
    state_file = DATA_DIR / 'state.json'
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return {
        'portfolios': {},
        'recommendations': [],
        'aiTradeLog': [],
        'startingBalance': 100000,
        'lastRun': None,
    }

def save_state(state: dict):
    """Save portfolio state to data/state.json"""
    (DATA_DIR / 'state.json').write_text(json.dumps(state, indent=2, default=str))

def apply_decisions(state: dict, strategy_id: str, decisions: list,
                    quotes: dict, config: dict) -> list:
    """Apply AI decisions to portfolio state, return trade log entries"""

    if strategy_id not in state['portfolios']:
        state['portfolios'][strategy_id] = {
            'balance': state['startingBalance'],
            'positions': {},  # symbol -> {qty, entryPrice, entryTs, aiScores, reason}
            'trades': [],
            'history': [],
        }

    p = state['portfolios'][strategy_id]
    total_value = p['balance'] + sum(
        quotes.get(sym, {}).get('price', info['entryPrice']) * info['qty']
        for sym, info in p['positions'].items()
    )

    log_entries = []

    for d in decisions:
        action = d.get('action', 'HOLD')
        symbol = d.get('symbol', '')
        price = quotes.get(symbol, {}).get('price')

        if not price or not symbol:
            continue

        if action == 'BUY':
            # Gate checks
            if d.get('opportunityScore', 0) < config.get('minOpp', 80): continue
            if d.get('confidenceScore', 0) < config.get('minConf', 75): continue
            if d.get('riskScore', 100) > config.get('maxRisk', 40): continue
            if len(p['positions']) >= config.get('maxPositions', 15): continue
            if symbol in p['positions']: continue  # Already held

            alloc_pct = min(d.get('qty_pct', config.get('maxPosPct', 5)), config.get('maxPosPct', 5))
            alloc_amt = total_value * alloc_pct / 100
            qty = int(alloc_amt / price)

            if qty < 1 or qty * price > p['balance']:
                continue

            p['positions'][symbol] = {
                'qty': qty,
                'entryPrice': price,
                'entryTs': datetime.now(timezone.utc).isoformat(),
                'aiScores': {
                    'opp': d.get('opportunityScore'),
                    'risk': d.get('riskScore'),
                    'conf': d.get('confidenceScore'),
                },
                'reason': d.get('reasoning', ''),
            }
            p['balance'] -= qty * price

            log_entry = f"BUY {qty}× {symbol} @ £{price:.2f} — {d.get('reasoning', '')}"
            log_entries.append({'ts': datetime.now(timezone.utc).isoformat(),
                                'portfolio': strategy_id, 'msg': log_entry})

            # Record recommendation
            state['recommendations'].insert(0, {
                'id': f"{datetime.now(timezone.utc).timestamp()}{symbol}",
                'symbol': symbol,
                'strategy': strategy_id,
                'ts': datetime.now(timezone.utc).isoformat(),
                'entryPrice': price,
                'oppScore': d.get('opportunityScore'),
                'riskScore': d.get('riskScore'),
                'confScore': d.get('confidenceScore'),
                'reasoning': d.get('reasoning', ''),
                'perf1d': None, 'perf7d': None, 'perf30d': None,
            })

        elif action == 'SELL':
            if symbol not in p['positions']:
                continue

            pos = p['positions'].pop(symbol)
            pnl = (price - pos['entryPrice']) * pos['qty']
            pnl_pct = (price - pos['entryPrice']) / pos['entryPrice'] * 100

            p['trades'].append({
                'symbol': symbol,
                'qty': pos['qty'],
                'entryPrice': pos['entryPrice'],
                'exitPrice': price,
                'pnl': round(pnl, 2),
                'pnlPct': round(pnl_pct, 2),
                'entryTs': pos['entryTs'],
                'exitTs': datetime.now(timezone.utc).isoformat(),
                'reason': d.get('reasoning', ''),
            })
            p['balance'] += pos['qty'] * price

            log_entry = f"SELL {pos['qty']}× {symbol} @ £{price:.2f} — {d.get('reasoning', '')} — P&L: {'+'if pnl>=0 else ''}£{pnl:.2f}"
            log_entries.append({'ts': datetime.now(timezone.utc).isoformat(),
                                'portfolio': strategy_id, 'msg': log_entry})

    # Check stop-loss / take-profit on existing positions
    stop_loss   = config.get('stopLoss', 8)
    take_profit = config.get('takeProfit', 20)

    to_close = []
    for sym, pos in p['positions'].items():
        cur_price = quotes.get(sym, {}).get('price', pos['entryPrice'])
        pct = (cur_price - pos['entryPrice']) / pos['entryPrice'] * 100
        if pct <= -stop_loss:
            to_close.append((sym, pos, cur_price, f'Stop-loss triggered ({pct:.1f}%)'))
        elif pct >= take_profit:
            to_close.append((sym, pos, cur_price, f'Take-profit triggered (+{pct:.1f}%)'))

    for sym, pos, cur_price, reason in to_close:
        pnl = (cur_price - pos['entryPrice']) * pos['qty']
        p['trades'].append({
            'symbol': sym, 'qty': pos['qty'],
            'entryPrice': pos['entryPrice'], 'exitPrice': cur_price,
            'pnl': round(pnl, 2),
            'pnlPct': round((cur_price - pos['entryPrice']) / pos['entryPrice'] * 100, 2),
            'entryTs': pos['entryTs'], 'exitTs': datetime.now(timezone.utc).isoformat(),
            'reason': reason,
        })
        p['balance'] += pos['qty'] * cur_price
        p['positions'].pop(sym)
        log_entries.append({'ts': datetime.now(timezone.utc).isoformat(),
                            'portfolio': strategy_id, 'msg': f'AUTO-CLOSE {sym}: {reason}'})

    # Update position current prices
    for sym in list(p['positions'].keys()):
        if sym in quotes:
            p['positions'][sym]['currentPrice'] = quotes[sym]['price']

    # Record equity snapshot
    total = p['balance'] + sum(
        quotes.get(sym, {}).get('price', info['entryPrice']) * info['qty']
        for sym, info in p['positions'].items()
    )
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if not p['history'] or p['history'][-1]['date'] != today:
        p['history'].append({'date': today, 'value': round(total, 2)})
    else:
        p['history'][-1]['value'] = round(total, 2)

    # Update recommendation performance
    for rec in state['recommendations']:
        entry = rec.get('entryPrice')
        sym   = rec.get('symbol')
        if not entry or not sym or sym not in quotes: continue
        cur   = quotes[sym]['price']
        pct   = (cur - entry) / entry * 100
        from datetime import datetime as dt2
        try:
            rec_ts = dt2.fromisoformat(rec['ts'].replace('Z','+00:00'))
            age_days = (datetime.now(timezone.utc) - rec_ts).days
            if age_days >= 1  and rec['perf1d']  is None: rec['perf1d']  = round(pct, 2)
            if age_days >= 7  and rec['perf7d']  is None: rec['perf7d']  = round(pct, 2)
            if age_days >= 30 and rec['perf30d'] is None: rec['perf30d'] = round(pct, 2)
        except Exception:
            pass

    return log_entries

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f'\n{"="*50}')
    print(f'IntelliVest AI Engine — {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}')
    print(f'{"="*50}')

    market_open, market_status = is_market_open()
    print(f'Market status: {market_status}')

    if not ANTHROPIC_KEY:
        print('ERROR: ANTHROPIC_API_KEY not set in GitHub secrets')
        sys.exit(1)

    if not FINNHUB_KEY:
        print('WARNING: FINNHUB_API_KEY not set — using limited data')

    # Load existing state
    state = load_state()

    # Load config from data/config.json (synced from dashboard)
    config_file = DATA_DIR / 'config.json'
    config = json.loads(config_file.read_text()) if config_file.exists() else {
        'minOpp': 80, 'minConf': 75, 'maxRisk': 40,
        'stopLoss': 8, 'takeProfit': 20, 'maxPosPct': 5,
        'maxSectorPct': 20, 'maxPositions': 15,
    }

    # Collect all symbols needed
    all_symbols = set()
    for s in STRATEGIES.values():
        all_symbols.update(s['symbols'])
    all_symbols.update(['SPY','QQQ','DIA','IWM','GLD','TLT'])

    print(f'\nFetching prices for {len(all_symbols)} symbols...')
    quotes = fetch_batch_quotes(list(all_symbols))
    print(f'Got {len(quotes)} quotes')

    print('\nFetching news...')
    news = fetch_news_rss()
    print(f'Got {len(news)} headlines')

    # Generate daily insight (only once per day, on first run)
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    insight_file = DATA_DIR / 'daily_insight.json'
    existing_insight = {}
    if insight_file.exists():
        try: existing_insight = json.loads(insight_file.read_text())
        except: pass

    if existing_insight.get('date') != today:
        print('\nGenerating daily insight...')
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        insight = generate_daily_insight(client, quotes, news)
        insight_file.write_text(json.dumps(insight, indent=2))
        print(f'Daily insight saved')
    else:
        print('\nDaily insight already generated today, skipping')
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    # Run each strategy
    all_log_entries = []
    strategy_results = {}

    # Pre-market: only run Master and Momentum (lighter scan)
    # Market hours: run all strategies
    active_strategies = list(STRATEGIES.keys())
    if not market_open and market_status == 'pre-market' and not FORCE_RUN:
        active_strategies = ['master', 'momentum']
        print('\nPre-market mode: running Master + Momentum only')
    elif not market_open and not FORCE_RUN:
        print('\nOutside market hours: skipping strategy runs (already ran today)')
        # Still save prices update
        (DATA_DIR / 'prices.json').write_text(json.dumps({
            'quotes': quotes,
            'updatedAt': datetime.now(timezone.utc).isoformat(),
        }, indent=2))
        state['lastRun'] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        return

    print(f'\nRunning {len(active_strategies)} strategies...')

    for sid in active_strategies:
        strategy = STRATEGIES[sid]
        print(f'  {strategy["name"]}...', end=' ')

        result = run_strategy(client, sid, strategy, quotes, news, state, config)
        strategy_results[sid] = result

        if result.get('decisions'):
            log = apply_decisions(state, sid, result['decisions'], quotes, config)
            all_log_entries.extend(log)
            bought  = sum(1 for d in result['decisions'] if d['action'] == 'BUY')
            sold    = sum(1 for d in result['decisions'] if d['action'] == 'SELL')
            print(f'✓ ({bought} buys, {sold} sells)')
        else:
            print('✓ (no trades)')

        time.sleep(0.5)  # Small delay between API calls

    # Add log entries
    state.setdefault('aiTradeLog', [])
    state['aiTradeLog'] = all_log_entries + state['aiTradeLog']
    state['aiTradeLog'] = state['aiTradeLog'][:500]  # Keep last 500 entries
    state['lastRun'] = datetime.now(timezone.utc).isoformat()
    state['recommendations'] = state.get('recommendations', [])[:500]

    # Save all data
    save_state(state)

    # Record benchmark prices (SPY, QQQ) for dashboard comparison
    benchmarks_file = DATA_DIR / 'benchmarks.json'
    existing_benchmarks = {}
    if benchmarks_file.exists():
        try: existing_benchmarks = json.loads(benchmarks_file.read_text())
        except: pass

    for bench_sym in ['SPY', 'QQQ']:
        q = quotes.get(bench_sym)
        if q:
            if bench_sym not in existing_benchmarks:
                # First time seeing this — record as entry price
                existing_benchmarks[bench_sym] = {
                    'entryPrice': q['price'],
                    'entryDate': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                    'currentPrice': q['price'],
                    'currentDate': datetime.now(timezone.utc).isoformat(),
                }
            else:
                # Update current price only
                existing_benchmarks[bench_sym]['currentPrice'] = q['price']
                existing_benchmarks[bench_sym]['currentDate'] = datetime.now(timezone.utc).isoformat()

    benchmarks_file.write_text(json.dumps(existing_benchmarks, indent=2))

    (DATA_DIR / 'prices.json').write_text(json.dumps({
        'quotes': quotes,
        'updatedAt': datetime.now(timezone.utc).isoformat(),
    }, indent=2))

    (DATA_DIR / 'strategy_results.json').write_text(json.dumps({
        'results': strategy_results,
        'marketStatus': market_status,
        'runAt': datetime.now(timezone.utc).isoformat(),
    }, indent=2))

    (DATA_DIR / 'run_log.json').write_text(json.dumps({
        'lastRun': datetime.now(timezone.utc).isoformat(),
        'marketStatus': market_status,
        'symbolsFetched': len(quotes),
        'strategiesRun': len(active_strategies),
        'tradesExecuted': len(all_log_entries),
        'recentLog': all_log_entries[:20],
    }, indent=2))

    print(f'\nEngine complete. {len(all_log_entries)} trades executed.')
    print(f'Data saved to {DATA_DIR}/')

    # Print portfolio summaries
    print('\nPortfolio summary:')
    starting = state.get('startingBalance', 100000)
    for sid, p in state['portfolios'].items():
        invested = sum(
            quotes.get(sym, {}).get('price', info['entryPrice']) * info['qty']
            for sym, info in p['positions'].items()
        )
        total = p['balance'] + invested
        ret   = (total - starting) / starting * 100
        name  = STRATEGIES.get(sid, {}).get('name', sid)
        print(f'  {name}: £{total:,.2f} ({ret:+.2f}%) | {len(p["positions"])} positions')

if __name__ == '__main__':
    main()
