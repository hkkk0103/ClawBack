"""
Dual API rotation: Moralis + BSCScan fallback
Automatically switches between APIs for rate limiting and reliability
"""
import requests
from typing import List, Dict, Optional
from datetime import datetime
from config import MORALIS_API_KEYS, BSCSCAN_API_KEY, MORALIS_API_BASE, BSCSCAN_API_BASE

# API rotation state
api_stats = {
    'moralis': {'calls': 0, 'errors': 0, 'last_error': None},
    'bscscan': {'calls': 0, 'errors': 0, 'last_error': None}
}

def get_wallet_transfers_moralis(wallet: str, token: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """Get token transfers using Moralis API with key rotation"""
    global MORALIS_KEY_INDEX
    
    url = f'{MORALIS_API_BASE}/{wallet}/erc20/transfers'
    params = {
        'chain': 'bsc',
        'limit': limit
    }
    
    if token:
        params['contract_addresses'] = [token]
    
    # Try all available Moralis keys
    for attempt in range(len(MORALIS_API_KEYS)):
        current_key = MORALIS_API_KEYS[MORALIS_KEY_INDEX]
        headers = {
            'accept': 'application/json',
            'X-API-Key': current_key
        }
        
        try:
            api_stats['moralis']['calls'] += 1
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            
            if resp.status_code == 200:
                data = resp.json()
                return data.get('result', [])
            elif resp.status_code == 429:  # Rate limited
                # Rotate to next key
                MORALIS_KEY_INDEX = (MORALIS_KEY_INDEX + 1) % len(MORALIS_API_KEYS)
                print(f"  ⚠️ Moralis rate limited, switching to key #{MORALIS_KEY_INDEX + 1}")
                continue
            else:
                api_stats['moralis']['errors'] += 1
                api_stats['moralis']['last_error'] = f"HTTP {resp.status_code}"
                return None
                
        except Exception as e:
            api_stats['moralis']['errors'] += 1
            api_stats['moralis']['last_error'] = str(e)
            # Try next key on error
            MORALIS_KEY_INDEX = (MORALIS_KEY_INDEX + 1) % len(MORALIS_API_KEYS)
            continue
    
    # All keys failed
    return None

def get_wallet_transfers_bscscan(wallet: str, token: Optional[str] = None) -> List[Dict]:
    """Get token transfers using BSCScan API (fallback)"""
    params = {
        'module': 'account',
        'action': 'tokentx',
        'address': wallet,
        'sort': 'desc',
        'apikey': BSCSCAN_API_KEY
    }
    
    if token:
        params['contractaddress'] = token
    
    try:
        api_stats['bscscan']['calls'] += 1
        resp = requests.get(BSCSCAN_API_BASE, params=params, timeout=30)
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == '1':
                # Convert BSCScan format to Moralis-like format
                result = []
                for tx in data.get('result', []):
                    result.append({
                        'transaction_hash': tx['hash'],
                        'address': tx['contractAddress'],
                        'block_timestamp': datetime.fromtimestamp(int(tx['timeStamp'])).isoformat() + 'Z',
                        'block_number': tx['blockNumber'],
                        'to_address': tx['to'],
                        'from_address': tx['from'],
                        'value': tx['value'],
                        'token_symbol': tx.get('tokenSymbol', 'UNKNOWN'),
                        'token_name': tx.get('tokenName', ''),
                        'token_decimals': tx.get('tokenDecimal', '18')
                    })
                return result
            else:
                api_stats['bscscan']['errors'] += 1
                api_stats['bscscan']['last_error'] = data.get('message', 'Unknown error')
                return None
        else:
            api_stats['bscscan']['errors'] += 1
            api_stats['bscscan']['last_error'] = f"HTTP {resp.status_code}"
            return None
            
    except Exception as e:
        api_stats['bscscan']['errors'] += 1
        api_stats['bscscan']['last_error'] = str(e)
        return None

def get_wallet_transfers(wallet: str, token: Optional[str] = None, limit: int = 100) -> List[Dict]:
    """
    Get token transfers with automatic API rotation
    Tries Moralis first, falls back to BSCScan if needed
    """
    # Try Moralis first
    result = get_wallet_transfers_moralis(wallet, token, limit)
    
    if result is not None:
        return result
    
    # Fallback to BSCScan
    print(f"  ⚠️ Moralis failed, trying BSCScan...")
    result = get_wallet_transfers_bscscan(wallet, token)
    
    if result is not None:
        return result
    
    # Both failed
    print(f"  ❌ Both APIs failed")
    return []

def get_api_stats() -> Dict:
    """Get API usage statistics"""
    return {
        'moralis': {
            'calls': api_stats['moralis']['calls'],
            'errors': api_stats['moralis']['errors'],
            'success_rate': f"{(1 - api_stats['moralis']['errors'] / max(1, api_stats['moralis']['calls'])) * 100:.1f}%",
            'last_error': api_stats['moralis']['last_error']
        },
        'bscscan': {
            'calls': api_stats['bscscan']['calls'],
            'errors': api_stats['bscscan']['errors'],
            'success_rate': f"{(1 - api_stats['bscscan']['errors'] / max(1, api_stats['bscscan']['calls'])) * 100:.1f}%",
            'last_error': api_stats['bscscan']['last_error']
        }
    }

def analyze_wallet_buys(wallet: str, tokens: List[str]) -> Dict:
    """Analyze wallet buy pattern across multiple tokens"""
    print(f"\n{'='*60}")
    print(f"分析钱包: {wallet[:10]}...{wallet[-8:]}")
    print(f"{'='*60}")
    
    wallet_lower = wallet.lower()
    wallet_data = {
        'address': wallet,
        'buys': {},
        'first_buy_times': {},
        'buy_sequence': []
    }
    
    for token in tokens:
        print(f"\n  代币: {token[:10]}...{token[-8:]}")
        
        transfers = get_wallet_transfers(wallet, token)
        
        # Filter for buys (wallet is recipient)
        buys = [tx for tx in transfers if tx.get('to_address', '').lower() == wallet_lower]
        
        if buys:
            print(f"    ✅ 找到 {len(buys)} 笔买入")
            wallet_data['buys'][token] = buys
            
            # Get timestamp of first buy
            first_buy = buys[-1]  # Last in list is oldest
            timestamp = datetime.fromisoformat(first_buy['block_timestamp'].replace('Z', '+00:00')).timestamp()
            wallet_data['first_buy_times'][token] = int(timestamp)
            wallet_data['buy_sequence'].append((int(timestamp), token, first_buy['block_number']))
            
            dt = datetime.fromtimestamp(timestamp)
            print(f"    首次买入: 区块 {first_buy['block_number']} 于 {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"    ❌ 未找到买入记录")
    
    wallet_data['buy_sequence'].sort()
    
    return wallet_data

def compare_wallets(w1_data: Dict, w2_data: Dict) -> Dict:
    """Compare two wallet patterns to detect if they're related"""
    tokens1 = set(w1_data['buys'].keys())
    tokens2 = set(w2_data['buys'].keys())
    
    overlap = tokens1 & tokens2
    total_tokens = tokens1 | tokens2
    
    overlap_ratio = len(overlap) / len(total_tokens) if total_tokens else 0
    
    print(f"\n{'='*60}")
    print(f"对比分析")
    print(f"{'='*60}")
    print(f"钱包 1 买入: {len(tokens1)} 个代币")
    print(f"钱包 2 买入: {len(tokens2)} 个代币")
    print(f"重合代币: {len(overlap)} 个")
    print(f"重合率: {overlap_ratio:.1%}")
    
    # Calculate time differences
    time_diffs = []
    time_details = []
    
    for token in overlap:
        t1 = w1_data['first_buy_times'].get(token, 0)
        t2 = w2_data['first_buy_times'].get(token, 0)
        
        if t1 and t2:
            diff_seconds = abs(t1 - t2)
            diff_minutes = diff_seconds / 60
            time_diffs.append(diff_minutes)
            
            dt1 = datetime.fromtimestamp(t1)
            dt2 = datetime.fromtimestamp(t2)
            
            time_details.append({
                'token': token,
                'w1_time': dt1.strftime('%H:%M:%S'),
                'w2_time': dt2.strftime('%H:%M:%S'),
                'diff_minutes': int(diff_minutes),
                'diff_seconds': int(diff_seconds % 60)
            })
    
    if time_details:
        print(f"\n时间差分析:")
        for detail in time_details[:5]:  # Show first 5
            print(f"\n  代币 {detail['token'][:10]}...")
            print(f"    钱包1: {detail['w1_time']}")
            print(f"    钱包2: {detail['w2_time']}")
            print(f"    时差: {detail['diff_minutes']}分{detail['diff_seconds']}秒")
    
    avg_time_diff = sum(time_diffs) / len(time_diffs) if time_diffs else 999999
    
    # Check sequence match
    seq1 = [t for _, t, _ in w1_data['buy_sequence'] if t in overlap]
    seq2 = [t for _, t, _ in w2_data['buy_sequence'] if t in overlap]
    sequence_match = seq1 == seq2
    
    # Scoring
    score = 0
    signals = []
    
    if overlap_ratio >= 0.8:
        score += 40
        signals.append({'type': 'red', 'text': f'重合 {len(overlap)}/{len(total_tokens)} 币'})
    elif overlap_ratio >= 0.5:
        score += 25
        signals.append({'type': 'yellow', 'text': f'重合 {len(overlap)}/{len(total_tokens)} 币'})
    else:
        score += 10
        signals.append({'type': 'green', 'text': f'重合 {len(overlap)}/{len(total_tokens)} 币'})
    
    if avg_time_diff <= 60:
        score += 30
        signals.append({'type': 'red', 'text': f'平均时差 {int(avg_time_diff)}分钟'})
    elif avg_time_diff <= 300:
        score += 20
        signals.append({'type': 'yellow', 'text': f'平均时差 {int(avg_time_diff)}分钟'})
    else:
        score += 5
        signals.append({'type': 'green', 'text': f'平均时差 {int(avg_time_diff)}分钟'})
    
    if sequence_match and len(seq1) >= 2:
        score += 30
        signals.append({'type': 'red', 'text': '买入顺序完全一致'})
    
    risk = 'HIGH' if score >= 70 else 'MID' if score >= 50 else 'LOW'
    
    print(f"\n{'='*60}")
    print(f"分析结果")
    print(f"{'='*60}")
    print(f"评分: {score}/100")
    print(f"风险等级: {risk}")
    print(f"顺序匹配: {'是' if sequence_match else '否'}")
    print(f"\n信号:")
    for sig in signals:
        emoji = '🔴' if sig['type'] == 'red' else '🟡' if sig['type'] == 'yellow' else '🟢'
        print(f"  {emoji} {sig['text']}")
    
    conclusion = '✅ 高度疑似大小号' if score >= 70 else '⚠️ 可能相关' if score >= 50 else '❌ 关联度低'
    print(f"\n{'='*60}")
    print(f"结论: {conclusion}")
    print(f"{'='*60}")
    
    # Print API stats
    stats = get_api_stats()
    print(f"\n{'='*60}")
    print(f"API 使用统计")
    print(f"{'='*60}")
    print(f"Moralis: {stats['moralis']['calls']} 次调用, 成功率 {stats['moralis']['success_rate']}")
    print(f"BSCScan: {stats['bscscan']['calls']} 次调用, 成功率 {stats['bscscan']['success_rate']}")
    
    return {
        'overlap_count': len(overlap),
        'overlap_ratio': overlap_ratio,
        'avg_time_diff_minutes': int(avg_time_diff),
        'sequence_match': sequence_match,
        'score': score,
        'risk': risk,
        'signals': signals,
        'time_details': time_details,
        'api_stats': stats
    }

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🦞 龙虾侦探 - 双 API 轮询测试")
    print("="*60)
    
    # Test with 零一
    wallet1 = '0x19e884dd1bb5247e3a83d30694137795bd5143c7'
    wallet2 = '0x2bf7befc0b8d2318c4416f5fc80dfc45f12facab'
    tokens = [
        '0xda4f7a7a11294bb0c713e96f9375addd612d4444',
        '0xbe9f768c2fb25614c4237c7bb249f6f669aa4444',
        '0x2b037e745265d2adaf42f44b0fa6295bd7194444',
        '0x8c8971b7d0162a93712a7b3f359220ad039e4444'
    ]
    
    print(f"\n测试案例: 零一")
    print(f"钱包 1: {wallet1}")
    print(f"钱包 2: {wallet2}")
    print(f"共同代币: {len(tokens)}")
    
    data1 = analyze_wallet_buys(wallet1, tokens)
    data2 = analyze_wallet_buys(wallet2, tokens)
    comparison = compare_wallets(data1, data2)
