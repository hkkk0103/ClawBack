"""
Mode B: Multi-token cross-reference analysis with Moralis swaps
Scan buyers in a time window and find overlapping wallets
"""
import requests
from typing import List, Dict
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from config import MORALIS_API_KEYS, MORALIS_API_BASE

MORALIS_KEY_INDEX = 0

# BSC block time: ~3 seconds per block
BLOCKS_PER_MINUTE = 20


def _moralis_get(path: str, params: Dict) -> Dict:
    global MORALIS_KEY_INDEX

    for _ in range(len(MORALIS_API_KEYS)):
        current_key = MORALIS_API_KEYS[MORALIS_KEY_INDEX]
        headers = {
            'accept': 'application/json',
            'X-API-Key': current_key
        }
        try:
            resp = requests.get(f'{MORALIS_API_BASE}{path}', headers=headers, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                MORALIS_KEY_INDEX = (MORALIS_KEY_INDEX + 1) % len(MORALIS_API_KEYS)
                continue
            return {}
        except Exception:
            MORALIS_KEY_INDEX = (MORALIS_KEY_INDEX + 1) % len(MORALIS_API_KEYS)
            continue
    return {}


def _parse_iso(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))


def get_token_swaps_by_time(token: str, from_date: str, to_date: str, limit: int = 100) -> List[Dict]:
    """Get token buy swaps in a specific time range with pagination."""
    all_results = []
    cursor = None

    while True:
        params = {
            'chain': 'bsc',
            'limit': min(limit, 100),
            'transactionTypes': 'buy',
            'fromDate': from_date,
            'toDate': to_date,
        }
        if cursor:
            params['cursor'] = cursor

        data = _moralis_get(f'/erc20/{token}/swaps', params) or {}
        batch = data.get('result', [])
        all_results.extend(batch)
        cursor = data.get('cursor')
        if not cursor:
            break

    return all_results


def analyze_token_buyers_by_time(token: str, shill_time_iso: str, window_minutes: int = 30) -> Dict:
    """Analyze real buyers before shill time using Moralis swaps."""
    print(f"\n{'='*60}")
    print(f"分析代币: {token[:10]}...{token[-8:]}")
    print(f"喊单时间: {shill_time_iso}")
    print(f"{'='*60}")

    shill_dt = _parse_iso(shill_time_iso)
    from_dt = shill_dt - timedelta(minutes=window_minutes)
    from_date = from_dt.isoformat().replace('+00:00', 'Z')
    to_date = shill_dt.isoformat().replace('+00:00', 'Z')

    print(f"扫描窗口: {window_minutes} 分钟")
    print(f"时间范围: {from_date} - {to_date}")
    print(f"\n获取代币 swap 记录...")

    swaps = get_token_swaps_by_time(token, from_date, to_date, limit=100)
    if not swaps:
        print("❌ 未获取到 swap 记录")
        return {
            'token': token,
            'buyers': {},
            'total_swaps': 0,
            'from_date': from_date,
            'to_date': to_date,
        }

    print(f"✅ 获取到 {len(swaps)} 笔 swap")

    buyers = {}
    for swap in swaps:
        buyer_addr = (swap.get('walletAddress') or '').lower()
        if not buyer_addr or buyer_addr == '0x0000000000000000000000000000000000000000':
            continue
        if buyer_addr == token.lower():
            continue

        block_number = int(swap.get('blockNumber', 0) or 0)
        if buyer_addr not in buyers:
            buyers[buyer_addr] = {
                'address': buyer_addr,
                'first_buy_block': block_number,
                'first_buy_time': swap.get('blockTimestamp'),
                'buy_count': 0,
                'total_value': 0.0,
            }

        buyers[buyer_addr]['buy_count'] += 1
        if block_number and block_number < buyers[buyer_addr]['first_buy_block']:
            buyers[buyer_addr]['first_buy_block'] = block_number
            buyers[buyer_addr]['first_buy_time'] = swap.get('blockTimestamp')

        sold = swap.get('sold') or {}
        bought = swap.get('bought') or {}
        bnb_value = 0.0
        if (sold.get('symbol') or '').upper() == 'WBNB':
            bnb_value = float(sold.get('amount') or 0)
        elif (bought.get('symbol') or '').upper() == 'WBNB':
            bnb_value = float(bought.get('amount') or 0)
        buyers[buyer_addr]['total_value'] += bnb_value

    print(f"\n✅ 找到 {len(buyers)} 个真实买家在窗口期内买入")

    return {
        'token': token,
        'buyers': buyers,
        'window_minutes': window_minutes,
        'from_date': from_date,
        'to_date': to_date,
        'total_swaps': len(swaps)
    }


def analyze_token_buyers_by_block(token: str, shill_block: int, window_blocks: int = 600) -> Dict:
    """Legacy compatibility wrapper. Prefer time-window swap analysis."""
    return {
        'token': token,
        'shill_block': shill_block,
        'window_blocks': window_blocks,
        'buyers': {},
        'total_transfers': 0
    }


def cross_reference_buyers(token_analyses: List[Dict]) -> List[Dict]:
    """Cross-reference buyers across multiple tokens and return all overlaps."""
    print(f"\n{'='*60}")
    print("交叉比对分析")
    print(f"{'='*60}")

    wallet_appearances = defaultdict(list)

    for analysis in token_analyses:
        token = analysis['token']
        for wallet, info in analysis['buyers'].items():
            wallet_appearances[wallet].append({
                'token': token,
                'first_buy_block': info['first_buy_block'],
                'first_buy_time': info['first_buy_time'],
                'buy_count': info['buy_count'],
                'total_value': info['total_value']
            })

    overlapping_wallets = []
    for wallet, appearances in wallet_appearances.items():
        if len(appearances) >= 2:
            overlap_count = len(appearances)
            total_buys = sum(a['buy_count'] for a in appearances)
            buy_blocks = [a['first_buy_block'] for a in appearances if a['first_buy_block']]
            block_variance = (max(buy_blocks) - min(buy_blocks)) if buy_blocks else 0
            time_variance_minutes = block_variance / BLOCKS_PER_MINUTE if buy_blocks else 0
            total_tokens = len(token_analyses)
            overlap_ratio = overlap_count / total_tokens

            overlapping_wallets.append({
                'address': wallet,
                'overlap_count': overlap_count,
                'total_tokens': total_tokens,
                'overlap_ratio': overlap_ratio,
                'total_buys': total_buys,
                'block_variance': block_variance,
                'time_variance_minutes': int(time_variance_minutes),
                'appearances': appearances
            })

    overlapping_wallets.sort(key=lambda x: (x['overlap_count'], x['total_buys']), reverse=True)

    print(f"\n找到 {len(overlapping_wallets)} 个重合钱包")
    print("（出现在 2+ 个代币中）")

    return overlapping_wallets
