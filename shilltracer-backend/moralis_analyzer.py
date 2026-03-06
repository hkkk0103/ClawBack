"""
Moralis API integration for BSC wallet analysis
"""
import requests
from typing import List, Dict
from datetime import datetime
from config import MORALIS_API_KEYS, MORALIS_API_BASE, validate_backend_env

validate_backend_env()

def get_wallet_token_transfers(wallet: str, token: str = None) -> List[Dict]:
    """Get ERC20 token transfers for a wallet"""
    url = f'{MORALIS_API_BASE}/{wallet}/erc20/transfers'
    params = {
        'chain': 'bsc',
        'limit': 100
    }
    
    if token:
        params['contract_addresses'] = [token]
    
    for current_key in MORALIS_API_KEYS:
        headers = {
            'accept': 'application/json',
            'X-API-Key': current_key
        }
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            data = resp.json()
            
            if 'result' in data:
                return data['result']
            if resp.status_code == 429:
                continue
            print(f"API Error: {data}")
        except Exception as e:
            print(f"Exception: {e}")
            continue
    return []

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
        
        transfers = get_wallet_token_transfers(wallet, token)
        
        # Filter for buys (wallet is recipient)
        buys = [tx for tx in transfers if tx.get('to_address', '').lower() == wallet_lower]
        
        if buys:
            print(f"    ✅ 找到 {len(buys)} 笔买入")
            wallet_data['buys'][token] = buys
            
            # Get timestamp of first buy
            first_buy = buys[-1]  # Moralis returns newest first, so last is oldest
            timestamp = datetime.fromisoformat(first_buy['block_timestamp'].replace('Z', '+00:00')).timestamp()
            wallet_data['first_buy_times'][token] = int(timestamp)
            wallet_data['buy_sequence'].append((int(timestamp), token, first_buy['block_number']))
            
            dt = datetime.fromtimestamp(timestamp)
            print(f"    首次买入: 区块 {first_buy['block_number']} 于 {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    交易哈希: {first_buy['transaction_hash'][:20]}...")
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
    
    # Calculate time differences for overlapping tokens
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
        for detail in time_details:
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
    
    # Overlap scoring
    if overlap_ratio >= 0.8:
        score += 40
        signals.append({'type': 'red', 'text': f'重合 {len(overlap)}/{len(total_tokens)} 币'})
    elif overlap_ratio >= 0.5:
        score += 25
        signals.append({'type': 'yellow', 'text': f'重合 {len(overlap)}/{len(total_tokens)} 币'})
    else:
        score += 10
        signals.append({'type': 'green', 'text': f'重合 {len(overlap)}/{len(total_tokens)} 币'})
    
    # Time proximity scoring
    if avg_time_diff <= 60:
        score += 30
        signals.append({'type': 'red', 'text': f'平均时差 {int(avg_time_diff)}分钟'})
    elif avg_time_diff <= 300:
        score += 20
        signals.append({'type': 'yellow', 'text': f'平均时差 {int(avg_time_diff)}分钟'})
    else:
        score += 5
        signals.append({'type': 'green', 'text': f'平均时差 {int(avg_time_diff)}分钟'})
    
    # Sequence match scoring
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
    
    return {
        'overlap_count': len(overlap),
        'overlap_ratio': overlap_ratio,
        'avg_time_diff_minutes': int(avg_time_diff),
        'sequence_match': sequence_match,
        'score': score,
        'risk': risk,
        'signals': signals,
        'time_details': time_details
    }

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🦞 龙虾侦探 - 大小号关系分析")
    print("="*60)
    
    # Test case: 零一
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
    
    # Analyze both wallets
    data1 = analyze_wallet_buys(wallet1, tokens)
    data2 = analyze_wallet_buys(wallet2, tokens)
    
    # Compare
    comparison = compare_wallets(data1, data2)
