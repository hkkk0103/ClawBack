# 🦞 ClawBack

BSC 链上喊单埋伏钱包分析工具。支持两种模式：

- **Mode A · 已知钱包**：输入项目合约、喊单时间、KOL 主钱包，找疑似关联小号
- **Mode B · 未知钱包**：输入多组喊单记录，交叉比对固定埋伏钱包

现在的实现已经按 **可开源 / 可部署 / 可绑域名上线** 的标准整理：

- 后端密钥改为环境变量
- 前端不再暴露 BscScan key
- 前端 API 地址支持运行时配置
- 钱包链接统一跳转 **GMGN**
- Mode B 支持 **15 / 30 / 60 分钟**切换（默认 30）

---

## 功能概览

### Mode A：已知钱包追踪
输入：
- 合约地址
- KOL 喊单时间
- KOL 主钱包（可选，但建议填）

输出：
- 疑似小号列表
- 买入时间 / 金额 / 次数
- Bundle 同块买入识别
- GMGN 钱包直达链接

### Mode B：未知钱包交叉锁定
输入：
- 多组代币地址
- 每组对应喊单时间

输出：
- 所有重合钱包
- 出现次数 / 总买入 / 时间方差
- 每个钱包在每个代币中的出现记录
- GMGN 钱包直达链接

---

## 项目结构

```text
shilltracer-preview.html        # 前端静态页
shilltracer-assets/             # 前端静态资源
shilltracer-backend/
  api.py                        # Flask API
  config.py                     # 环境变量读取
  dual_api_analyzer.py          # Mode A 双 API 轮换
  mode_b_block_range.py         # Mode B 区块范围扫描
  moralis_analyzer.py           # Moralis 分析辅助
  requirements.txt
  start.sh
  .env.example
```

---

## 环境变量

在 `shilltracer-backend/.env` 中配置：

```env
# 必填：一个或多个 Moralis key，支持逗号分隔轮换
MORALIS_API_KEYS=your_moralis_key_1,your_moralis_key_2

# 可选：BscScan 备用 key / 前端代理查询用
BSCSCAN_API_KEY=your_bscscan_api_key

# 可选：后端端口
PORT=5001
```

说明：
- 如果没有 `MORALIS_API_KEYS`，后端会直接报错退出
- `BSCSCAN_API_KEY` 不是 Mode B 主依赖，但建议配置，供前端代理和部分查询兜底使用

---

## 本地启动

### 1) 启动后端

```bash
cd shilltracer-backend
cp .env.example .env
# 填入你自己的 key
chmod +x start.sh
./start.sh
```

默认运行：
- `http://127.0.0.1:5001`

### 2) 打开前端

直接浏览器打开：

```text
file:///.../shilltracer-preview.html
```

默认行为：
- 如果是 `file://` 打开，前端默认请求 `http://127.0.0.1:5001`
- 如果是域名部署，前端默认请求 `当前域名:5001`

### 3) 手动指定 API 地址（可选）

如果前后端不在同一域名，可以在页面加载前注入：

```html
<script>
  window.SHILLTRACER_API_BASE = 'https://api.your-domain.com';
</script>
```

---

## API 接口

### `GET /api/health`
健康检查。

### `GET /api/bnb-price`
返回当前 BNB 价格和 `$20` 对应的 BNB 数量。

### `GET /api/stats`
返回 Moralis / BscScan 调用统计。

### `POST /api/analyze-wallets`
Mode A：两钱包关联分析。

请求：

```json
{
  "wallet1": "0x...",
  "wallet2": "0x...",
  "tokens": ["0x...", "0x..."]
}
```

### `POST /api/analyze-multi-tokens`
Mode B：多代币交叉分析。

请求：

```json
{
  "tokens": [
    {"address": "0x...", "shill_time": "2026-03-06T07:05:00Z"},
    {"address": "0x...", "shill_time": "2026-03-06T07:50:00Z"}
  ],
  "window_minutes": 30
}
```

### `GET /api/bscscan`
前端专用 BscScan 代理。

允许的 action：
- `account/tokentx`
- `account/txlist`
- `block/getblocknobytime`

---

## 部署建议

### 前端
前端是单文件静态页，适合部署到：
- GitHub Pages
- Vercel
- Netlify
- Cloudflare Pages

建议：
- 使用单独前端域名，例如 `shilltracer.xxx.com`

### 后端
后端是 Flask API，适合部署到：
- Railway
- Render
- Fly.io
- VPS / Docker / PM2 / systemd

建议：
- 使用单独 API 域名，例如 `api.shilltracer.xxx.com`

### 域名结构建议
- 前端：`shilltracer.yourdomain.com`
- 后端：`api.shilltracer.yourdomain.com`

前端部署时加：

```html
<script>
  window.SHILLTRACER_API_BASE = 'https://api.shilltracer.yourdomain.com';
</script>
```

---

## 开源前注意事项

在上传 GitHub 公开仓库之前，务必确认：

- [x] 后端源码里没有硬编码 Moralis key
- [x] 前端源码里没有硬编码 BscScan key
- [x] `.env` 已加入 `.gitignore`
- [ ] 仓库历史里如果曾提交过真实 key，仍需 **rotate / 更换密钥**
- [ ] 确认线上部署环境已填入新 key

> 重点：即使当前工作区代码已经清理，**如果历史 commit 里出现过真实 key，仍然算泄露过**。上线前建议把相关 key 全部重置。

---

## 当前已验证

已实际验证通过：

- 前端脚本语法检查
- `GET /api/health`
- `GET /api/bnb-price`
- `POST /api/analyze-wallets`
- `POST /api/analyze-multi-tokens`
- Mode B 目标钱包命中回归
- 钱包链接跳转 GMGN

---

## License

MIT
