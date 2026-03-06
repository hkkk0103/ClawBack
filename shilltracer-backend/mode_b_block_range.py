"""
Mode B: Multi-token cross-reference analysis with block range
Scan all buyers in a block range and find overlapping wallets
"""
import requests
from typing import List, Dict
from collections import defaultdict
from config import MORALIS_API_KEYS, MORALIS_API_BASE

MORALIS_KEY_INDEX = 0

# BSC block time: ~3 seconds per block
BLOCKS_PER_MINUTE = 20

def get_token_transfers_by_block(token: str, from_block: int, to_block: int, limit: int = 100) -> List[Dict]:
    """
    Get all token transfers in a specific block range (with pagination)
    """
    global MORALIS_KEY_INDEX

    url = f'{MORALIS_API_BASE}/erc20/{token}/transfers'
    all_results = []
    cursor = None

    while True:
        params = {
            'chain': 'bsc',
            'from_block': from_block,
            'to_block': to_block,
            'limit': min(limit, 100),
            'order': 'DESC'
        }
        if cursor:
            params['cursor'] = cursor

        success = False
        for attempt in range(len(MORALIS_API_KEYS)):
            current_key = MORALIS_API_KEYS[MORALIS_KEY_INDEX]
            headers = {
                'accept': 'application/json',
                'X-API-Key': current_key
            }

            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)

                if resp.status_code == 200:
                    data = resp.json()
                    batch = data.get('result', [])
                    all_results.extend(batch)
                    cursor = data.get('cursor')
                    success = True
                    break
                elif resp.status_code == 429:
                    MORALIS_KEY_INDEX = (MORALIS_KEY_INDEX + 1) % len(MORALIS_API_KEYS)
                    print(f"  ⚠️ Rate limited, switching to key #{MORALIS_KEY_INDEX + 1}")
                    continue
                else:
                    print(f"  ❌ HTTP {resp.status_code}")
                    return all_results
            except Exception as e:
                print(f"  ❌ Error: {e}")
                MORALIS_KEY_INDEX = (MORALIS_KEY_INDEX + 1) % len(MORALIS_API_KEYS)
                continue

        if not success or not cursor:
            break

    return all_results

def analyze_token_buyers_by_block(token: str, shill_block: int, window_blocks: int = 600) -> Dict:
    """
    Analyze buyers of a token before shill block
    
    Args:
        token: Token contract address
        shill_block: Block number when shill happened
        window_blocks: Number of blocks before shill to scan (default 600 = ~30 min)
    
    Returns:
        Dict with buyers and their buy info
    """
    print(f"\n{'='*60}")
    print(f"分析代币: {token[:10]}...{token[-8:]}")
    print(f"喊单区块: {shill_block}")
    print(f"{'='*60}")
    
    from_block = shill_block - window_blocks
    to_block = shill_block
    
    window_minutes = window_blocks / BLOCKS_PER_MINUTE
    print(f"扫描窗口: {window_blocks} 个区块 (~{int(window_minutes)} 分钟)")
    print(f"区块范围: {from_block} - {to_block}")
    
    # Get token transfers
    print(f"\n获取代币转账记录...")
    transfers = get_token_transfers_by_block(token, from_block, to_block, limit=100)
    
    if not transfers:
        print(f"❌ 未获取到转账记录")
        return {'token': token, 'buyers': {}, 'total_transfers': 0}
    
    print(f"✅ 获取到 {len(transfers)} 笔转账")
    
    # Extract buyers
    buyers = {}
    
    for tx in transfers:
        to_address = tx.get('to_address', '').lower()
        block_number = int(tx.get('block_number', 0))
        
        if to_address and to_address != '0x0000000000000000000000000000000000000000':
            if to_address not in buyers:
                buyers[to_address] = {
                    'address': to_address,
                    'first_buy_block': block_number,
                    'first_buy_time': tx.get('block_timestamp'),
                    'buy_count': 0,
                    'total_value': 0
                }
            
            buyers[to_address]['buy_count'] += 1
            
            # Update first buy if earlier
            if block_number < buyers[to_address]['first_buy_block']:
                buyers[to_address]['first_buy_block'] = block_number
                buyers[to_address]['first_buy_time'] = tx.get('block_timestamp')
            
            # Try to get value
            value = int(tx.get('value', '0'))
            buyers[to_address]['total_value'] += value
    
    print(f"\n✅ 找到 {len(buyers)} 个买家在窗口期内买入")
    
    return {
        'token': token,
        'shill_block': shill_block,
        'window_blocks': window_blocks,
        'from_block': from_block,
        'to_block': to_block,
        'buyers': buyers,
        'total_transfers': len(transfers)
    }

def cross_reference_buyers(token_analyses: List[Dict]) -> List[Dict]:
    """
    Cross-reference buyers across multiple tokens
    Find wallets that appear in multiple tokens
    No scoring - just return all overlapping wallets with their data
    """
    print(f"\n{'='*60}")
    print(f"交叉比对分析")
    print(f"{'='*60}")
    
    # Count appearances
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
    
    # Filter for wallets appearing in 2+ tokens
    overlapping_wallets = []
    
    for wallet, appearances in wallet_appearances.items():
        if len(appearances) >= 2:
            overlap_count = len(appearances)
            total_buys = sum(a['buy_count'] for a in appearances)
            
            # Calculate time variance
            buy_blocks = [a['first_buy_block'] for a in appearances]
            block_variance = max(buy_blocks) - min(buy_blocks)
            time_variance_minutes = block_variance / BLOCKS_PER_MINUTE
            
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
    
    # Sort by overlap count (most overlaps first), then by total buys
    overlapping_wallets.sort(key=lambda x: (x['overlap_count'], x['total_buys']), reverse=True)
    
    print(f"\n找到 {len(overlapping_wallets)} 个重合钱包")
    print(f"（出现在 2+ 个代币中）")
    
    return overlapping_wallets

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🦞 龙虾侦探 - 模式 B 测试（区块范围查询）")
    print("="*60)
    
    # Test with 零一's tokens
    # We know: 0x2bf7befc... and 0x19e884dd... both bought at block 84916650
    tokens_with_blocks = [
        {
            'token': '0x8c8971b7d0162a93712a7b3f359220ad039e4444',
            'shill_block': 84917000  # ~350 blocks after first buy
        },
        {
            'token': '0xda4f7a7a11294bb0c713e96f9375addd612d4444',
            'shill_block': 84917800  # Different shill time
        }
    ]
    
    print(f"\n测试案例: 零一的代币")
    print(f"代币数量: {len(tokens_with_blocks)}")
    
    # Analyze each token
    analyses = []
    for item in tokens_with_blocks:
        analysis = analyze_token_buyers_by_block(
            item['token'], 
            item['shill_block'], 
            window_blocks=500  # ~25 minutes
        )
        analyses.append(analysis)
    
    # Cross-reference
    overlapping = cross_reference_buyers(analyses)
    
    # Display results
    print(f"\n{'='*60}")
    print(f"结果 - Top 10 疑似大小号")
    print(f"{'='*60}")
    
    for i, wallet in enumerate(overlapping[:10]):
        print(f"\n{i+1}. {wallet['address'][:10]}...{wallet['address'][-8:]}")
        print(f"   重合: {wallet['overlap_count']}/{wallet['total_tokens']} 代币 ({wallet['overlap_ratio']:.0%})")
        print(f"   总买入: {wallet['total_buys']} 笔")
        print(f"   时间方差: {wallet['time_variance_minutes']} 分钟")
        
        # Check if it's one of our known wallets
        known_wallets = [
            '0x19e884dd1bb5247e3a83d30694137795bd5143c7',
            '0x2bf7befc0b8d2318c4416f5fc80dfc45f12facab'
        ]
        if wallet['address'] in [w.lower() for w in known_wallets]:
            print(f"   ✅ 这是已知的零一钱包！")
