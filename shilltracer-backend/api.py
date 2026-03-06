"""
Flask API for ShillTracer with dual API rotation
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from dual_api_analyzer import analyze_wallet_buys, compare_wallets, get_api_stats
from mode_b_block_range import analyze_token_buyers_by_block, cross_reference_buyers
from config import MORALIS_API_KEYS, MORALIS_API_BASE, BSCSCAN_API_KEY, BSCSCAN_API_BASE, validate_backend_env
import requests
import os

app = Flask(__name__)
CORS(app)


def moralis_get(path, params=None):
    params = params or {}
    for current_key in MORALIS_API_KEYS:
        headers = {'accept': 'application/json', 'X-API-Key': current_key}
        try:
            resp = requests.get(f'{MORALIS_API_BASE}{path}', headers=headers, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                continue
        except Exception:
            continue
    return None


def get_block_by_date(date_str):
    data = moralis_get('/dateToBlock', {'chain': 'bsc', 'date': date_str})
    return int(data.get('block', 0)) if data and data.get('block') else None


def get_date_by_block(block_number):
    data = moralis_get(f'/block/{block_number}', {'chain': 'bsc'})
    return data.get('timestamp') if data else None


def get_wallet_native_history(wallet: str, from_block: int, to_block: int, limit: int = 100):
    data = moralis_get(f'/wallets/{wallet}/history', {
        'chain': 'bsc',
        'from_block': from_block,
        'to_block': to_block,
        'limit': limit,
        'include_internal_transactions': 'true',
        'order': 'DESC'
    })
    return (data or {}).get('result', [])


def get_recent_buy_map(wallet, limit=80):
    if not wallet:
        return {}
    data = moralis_get(f'/{wallet}/erc20/transfers', {'chain': 'bsc', 'limit': limit})
    result = (data or {}).get('result', [])
    buy_map = {}
    for tx in result:
        if tx.get('to_address', '').lower() != wallet:
            continue
        token = (tx.get('address') or '').lower()
        if not token:
            continue
        block_number = int(tx.get('block_number', 0) or 0)
        ts = tx.get('block_timestamp')
        if token not in buy_map or block_number < buy_map[token]['first_buy_block']:
            buy_map[token] = {
                'first_buy_block': block_number,
                'first_buy_time': ts
            }
    return buy_map


def analyze_mode_a_candidates(token_addr: str, shill_block: int, shill_time_iso: str, kol_wallet: str = '', window_minutes: int = 15):
    from datetime import datetime, timedelta
    shill_dt = datetime.fromisoformat(shill_time_iso.replace('Z', '+00:00'))
    from_dt = shill_dt - timedelta(minutes=window_minutes)

    swaps_data = moralis_get(f'/erc20/{token_addr}/swaps', {
        'chain': 'bsc',
        'limit': 100,
        'transactionTypes': 'buy',
        'fromDate': from_dt.isoformat().replace('+00:00', 'Z'),
        'toDate': shill_dt.isoformat().replace('+00:00', 'Z')
    }) or {}

    swaps = swaps_data.get('result', [])
    buyers_map = {}
    for swap in swaps:
        buyer_addr = (swap.get('walletAddress') or '').lower()
        if not buyer_addr or buyer_addr == '0x0000000000000000000000000000000000000000':
            continue
        if buyer_addr == token_addr.lower():
            continue
        if kol_wallet and buyer_addr == kol_wallet:
            continue
        block_number = int(swap.get('blockNumber', 0) or 0)
        if buyer_addr not in buyers_map:
            buyers_map[buyer_addr] = {
                'address': buyer_addr,
                'first_buy_block': block_number,
                'first_buy_time': swap.get('blockTimestamp'),
                'buy_count': 0,
                'bnb_value': 0.0,
            }
        buyers_map[buyer_addr]['buy_count'] += 1
        if block_number and (buyers_map[buyer_addr]['first_buy_block'] == 0 or block_number < buyers_map[buyer_addr]['first_buy_block']):
            buyers_map[buyer_addr]['first_buy_block'] = block_number
            buyers_map[buyer_addr]['first_buy_time'] = swap.get('blockTimestamp')
        bought = swap.get('bought') or {}
        sold = swap.get('sold') or {}
        if (bought.get('symbol') or '').upper() == 'WBNB':
            buyers_map[buyer_addr]['bnb_value'] += float(bought.get('amount') or 0)
        if (sold.get('symbol') or '').upper() == 'WBNB':
            buyers_map[buyer_addr]['bnb_value'] += float(sold.get('amount') or 0)

    buyer_list = sorted(
        buyers_map.values(),
        key=lambda x: (x.get('bnb_value', 0), x.get('buy_count', 0)),
        reverse=True
    )

    kol_buy_map = get_recent_buy_map(kol_wallet) if kol_wallet else {}
    kol_recent_tokens = set(kol_buy_map.keys())
    kol_current_buy_block = kol_buy_map.get(token_addr, {}).get('first_buy_block')

    candidates = []
    for buyer in buyer_list:
        buyer_addr = buyer.get('address', '').lower()
        buyer_buy_map = get_recent_buy_map(buyer_addr, limit=60) if kol_wallet else {}
        buyer_recent_tokens = set(buyer_buy_map.keys())
        overlap_tokens = sorted(kol_recent_tokens & buyer_recent_tokens) if kol_wallet else []
        overlap_count = len(overlap_tokens)
        overlap_total = len(kol_recent_tokens)
        same_block = bool(kol_current_buy_block and buyer.get('first_buy_block') == kol_current_buy_block)

        score = 20
        if overlap_total > 0:
            score += round((overlap_count / overlap_total) * 60)
        if same_block:
            score += 20
        score = min(score, 100)

        candidates.append({
            'address': buyer_addr,
            'suspicious_score': score,
            'overlap_count': overlap_count,
            'overlap_total': overlap_total,
            'same_block': same_block,
            'first_buy_block': buyer.get('first_buy_block'),
            'first_buy_time': buyer.get('first_buy_time'),
            'bnb_value': buyer.get('bnb_value', 0),
            'buy_count': buyer.get('buy_count', 0)
        })

    candidates.sort(key=lambda x: (x['suspicious_score'], x['bnb_value'], x['buy_count']), reverse=True)

    return {
        'candidates': candidates,
        'kol_recent_tokens': len(kol_recent_tokens),
        'kol_wallet': kol_wallet,
        'total_swaps': len(swaps),
        'from_date': from_dt.isoformat().replace('+00:00', 'Z'),
        'to_date': shill_dt.isoformat().replace('+00:00', 'Z')
    }

@app.route('/api/analyze-mode-a', methods=['POST'])
def analyze_mode_a():
    """Mode A: rebuild scanBuyers strategy on Moralis."""
    try:
        data = request.json or {}
        token_addr = data.get('token', '').strip().lower()
        shill_time = data.get('shill_time', '').strip()
        kol_wallet = data.get('kol_wallet', '').strip().lower()
        window_minutes = int(data.get('window_minutes', 15) or 15)

        if not token_addr or not shill_time:
            return jsonify({'error': '需要提供代币地址和喊单时间'}), 400

        shill_block = get_block_by_date(shill_time)
        if not shill_block:
            return jsonify({'error': '无法获取区块号'}), 400

        shill_time_iso = data.get('shill_time_iso')
        if not shill_time_iso:
            from datetime import datetime, timezone, timedelta
            local_dt = datetime.strptime(shill_time, '%Y/%m/%d %H:%M') if '/' in shill_time else datetime.fromisoformat(shill_time.replace('Z', '+00:00'))
            if local_dt.tzinfo is None:
                local_dt = local_dt.replace(tzinfo=timezone(timedelta(hours=8)))
            shill_time_iso = local_dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')

        result = analyze_mode_a_candidates(token_addr, shill_block, shill_time_iso, kol_wallet=kol_wallet, window_minutes=window_minutes)
        candidates = result['candidates']

        return jsonify({
            'token': token_addr,
            'shill_time': shill_time,
            'shill_block': shill_block,
            'window_minutes': window_minutes,
            'kol_wallet': result['kol_wallet'],
            'kol_recent_tokens': result['kol_recent_tokens'],
            'total_found': len(candidates),
            'total_swaps': result.get('total_swaps', 0),
            'from_date': result.get('from_date'),
            'to_date': result.get('to_date'),
            'candidates': candidates
        })

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze-multi-tokens', methods=['POST'])
def analyze_multi_tokens():
    """
    Mode B: Analyze multiple tokens to find overlapping wallets
    
    Request body:
    {
        "tokens": [
            {"address": "0x...", "shill_time": "2026-03-06T10:00:00Z"},
            {"address": "0x...", "shill_time": "2026-03-06T11:00:00Z"}
        ],
        "window_minutes": 15  // optional, default 15
    }
    """
    try:
        data = request.json
        
        tokens_data = data.get('tokens', [])
        window_minutes = data.get('window_minutes', 30)
        
        # Validation
        if not tokens_data or len(tokens_data) < 2:
            return jsonify({'error': '需要提供至少 2 个代币'}), 400
        
        # Convert shill times to block numbers
        def get_block_by_date(date_str):
            url = f'{MORALIS_API_BASE}/dateToBlock'
            params = {'chain': 'bsc', 'date': date_str}
            
            for current_key in MORALIS_API_KEYS:
                headers = {'accept': 'application/json', 'X-API-Key': current_key}
                try:
                    resp = requests.get(url, headers=headers, params=params, timeout=30)
                    if resp.status_code == 200:
                        return int(resp.json().get('block', 0))
                    if resp.status_code == 429:
                        continue
                except Exception:
                    continue
            return None
        
        tokens_with_blocks = []
        for item in tokens_data:
            token_addr = item.get('address', '').strip()
            shill_time = item.get('shill_time', '').strip()
            
            if not token_addr or not shill_time:
                continue
            
            block = get_block_by_date(shill_time)
            if block:
                tokens_with_blocks.append({
                    'token': token_addr,
                    'shill_time': shill_time,
                    'shill_block': block
                })
        
        if len(tokens_with_blocks) < 2:
            return jsonify({'error': '无法获取足够的区块号'}), 400
        
        # Analyze each token
        window_blocks = int(window_minutes * 20)  # ~20 blocks per minute on BSC
        analyses = []
        
        for item in tokens_with_blocks:
            analysis = analyze_token_buyers_by_block(
                item['token'],
                item['shill_block'],
                window_blocks=window_blocks
            )
            analyses.append(analysis)
        
        # Cross-reference
        overlapping = cross_reference_buyers(analyses)
        
        # Format response
        result = {
            'tokens_analyzed': len(tokens_with_blocks),
            'window_minutes': window_minutes,
            'overlapping_wallets': overlapping,
            'total_found': len(overlapping)
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/bscscan', methods=['GET'])
def bscscan_proxy():
    """Proxy BscScan requests so the frontend can stay keyless in open source mode"""
    if not BSCSCAN_API_KEY:
        return jsonify({'error': 'BSCSCAN_API_KEY not configured'}), 503

    allowed_actions = {
        ('account', 'tokentx'),
        ('account', 'txlist'),
        ('block', 'getblocknobytime')
    }

    module = request.args.get('module', '').strip()
    action = request.args.get('action', '').strip()
    if (module, action) not in allowed_actions:
        return jsonify({'error': 'unsupported bscscan action'}), 400

    params = request.args.to_dict(flat=True)
    params['apikey'] = BSCSCAN_API_KEY

    # Use V2 API for block queries
    if module == 'block' and action == 'getblocknobytime':
        api_url = 'https://api.etherscan.io/v2/api'
        params['chainid'] = 56
    else:
        api_url = BSCSCAN_API_BASE

    try:
        resp = requests.get(api_url, params=params, timeout=30)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 502

@app.route('/api/bnb-price', methods=['GET'])
def bnb_price():
    """Get current BNB price from Binance"""
    try:
        import requests
        resp = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT', timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            price = float(data['price'])
            return jsonify({
                'price': price,
                'threshold_20usd': 20 / price
            })
        else:
            return jsonify({'error': 'Failed to fetch price'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def stats():
    """Get API usage statistics"""
    return jsonify(get_api_stats())

if __name__ == '__main__':
    validate_backend_env()
    port = int(os.getenv('PORT', 5001))
    print(f"\n{'='*60}")
    print(f"🦞 龙虾侦探 API Server")
    print(f"{'='*60}")
    print(f"Server running on http://localhost:{port}")
    print(f"Health check: http://localhost:{port}/api/health")
    print(f"{'='*60}\n")
    
    app.run(host='0.0.0.0', port=port, debug=True)
