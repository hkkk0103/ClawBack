# ClawBack v1.0.0

BSC 链上喊单埋伏钱包分析工具。

## 一句话介绍
- **Mode A · 已知钱包**：输入项目合约、喊单时间、KOL 主钱包，追踪疑似关联小号
- **Mode B · 未知钱包**：输入多组喊单记录，交叉锁定固定埋伏钱包

## 本次发布包含
- Mode A 改为基于 **Moralis swaps** 抽取真实买家
- Mode B 改为基于 **Moralis swaps** 做多代币交叉，修复 four.meme / router 风格买入漏真钱包问题
- 前端接入正式生产 API：`https://api.clawback.win`
- Cloudflare Pages + Railway 生产部署链路打通
- BNB 价格接口增加 fallback
- 新增 `/api/health`
- 钱包链接统一跳转 **GMGN**
- 仓库完成公开前清理：环境变量化、README 对齐、部署说明补齐

## 线上地址
- Frontend: https://clawback.win
- API: https://api.clawback.win

## 部署
### Cloudflare Pages
- Repository: `hkkk0103/ClawBack`
- Framework preset: `None`
- Build command: 留空
- Build output directory: `/`
- Root directory: `/`

### Railway
- Root Directory: `shilltracer-backend`
- Start Command: `cd shilltracer-backend && bash start.sh`
- Required Variables:
  - `MORALIS_API_KEYS`
  - `BSCSCAN_API_KEY`
  - `PORT=5001`

## 发布前最后提醒
如果历史 commit 曾经出现过真实 Moralis / BscScan key，仍建议立即轮换。
