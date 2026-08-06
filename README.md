# 基金日报（每日自动更新）

面向「只在支付宝买基金、不买股票」的投资者：一份**基金版市场情绪日报**，每天自动抓取当天数据并生成单页 HTML，通过 GitHub Pages 发布成固定地址，每天显示最新交易日的情况。

包含：

- **我的持仓 · 收益与归因**：基于官方净值 + 季报前十大重仓，计算持仓市值、累计/当日盈亏，并穿透到个股与行业
- **基金自选追踪（可交互）**：输入任意基金代码/名称，即时查询净值与日/周/月/年业绩；可加入本机自选（离线可用，全部 2 万只基金数据已内嵌）
- **基金排行榜**：日涨幅 / 近1周 / 近1月 / 近1年 × 股票/混合/指数/债券/QDII/FOF 多维筛选
- **行业轮动**：哪些板块在驱动你的基金
- **基金类型表现分布**

> 数据源：天天基金（净值/排行/季报）、东方财富行业板块、腾讯财经行情。报告为公开数据整理，**不构成投资建议**。

**当前在线预览**：https://a27622533c5bfff5c.bj2.agentos-app.net （由本环境直接发布，为今日快照；下方部署到 GitHub Pages 后，`https://<用户名>.github.io/<仓库名>/` 才是长期稳定、可被他人通过 GitHub 发现的入口。）

---

## 一、本地运行

```bash
pip install -r requirements.txt
python3 daily_report.py              # 自动取最近交易日
python3 daily_report.py 2026-08-05   # 指定交易日
python3 daily_report.py --no-fund    # 只出基金榜单，不出我的持仓
```

生成文件：

- `reports/基金日报_YYYY-MM-DD.html`：当天报告（带日期，本地归档）
- `reports/index.html`：**稳定入口**，每天覆盖，作为网页固定地址

## 二、配置你自己的基金

编辑 `config/holdings.csv`（首次运行会自动生成示例持仓）：

```csv
基金代码,基金名称(可留空自动获取),持有份额,成本单价,买入日期(YYYY-MM-DD)
005827,,12000,1.8520,2026-03-12
161725,,15000,0.9180,2026-02-20
```

> 支付宝里买的都是**场外份额**，系统一律以基金公司官方单位净值为准（非二级市场价格），所以成本单价填你买入时的「单位净值」。

改完重跑 `python3 daily_report.py` 即可在「我的持仓」看到你的真实盈亏与归因。
网页里的「导出追踪码」可一键复制代码，粘到该 CSV 第 1 列也能纳入完整归因。

## 三、部署到 GitHub Pages（每天自动更新）

1. 在 GitHub 新建一个**公开**仓库（如 `fund-daily`）。
2. 把本仓库内容推送上去：

   ```bash
   git init
   git add .
   git commit -m "init fund daily report"
   git branch -M main
   git remote add origin https://github.com/<你的用户名>/<仓库名>.git
   git push -u origin main
   ```

3. 仓库 **Settings → Pages → Build and deployment → Source** 选择
   **Deploy from a branch**，Branch 选 **`gh-pages`**，目录 **`/ (root)`**，保存。
4. 等待 1～2 分钟，访问 `https://<你的用户名>.github.io/<仓库名>/` 即为当天日报。
5. 之后由 `.github/workflows/daily.yml` 在每个交易日 **北京时间 23:30** 自动重跑并发布；
   也可在 **Actions → 基金日报每日更新 → Run workflow** 手动触发。

> 首次部署后 gh-pages 分支由 Actions 自动创建，无需手动建分支。

## 四、注意事项 / 局限

- **定时延迟**：GitHub Actions 的定时任务对个人仓库可能有几分钟到几十分钟的延迟，属正常现象。
- **净值披露时间**：基金净值通常在交易日 20:00–23:00 披露，少数 QDII/海外债基滞后 1 天；报告会标注实际净值日期。
- **数据源限流**：若 GitHub 服务器 IP 被数据源临时限流，行业板块等少数模块可能为空，但基金榜单/自选追踪/持仓归因不受影响；次日会自动重试。
- **长期不活跃**：仓库超过 60 天无任何提交/访问，GitHub 可能自动暂停定时任务，手动 Run 一次即可恢复。
- **自选追踪持久化**：网页里的自选存在浏览器本地（localStorage）；若浏览器禁用本地存储或隐私模式，加入仍即时显示但不跨会话保留，可用「导出追踪码」落到 `holdings.csv` 做长期跟踪。

## 五、目录结构

```
daily_report.py          # 主流水线入口
lib/
  common.py               # HTTP/交易日工具
  market.py               # 行业板块/指数
  fund.py                 # 净值/持仓/归因计算
  funds_api.py            # 基金全量排行（内嵌交互数据）
  attribute.py            # 持仓穿透归因
  render.py               # 单文件 HTML 渲染 + 交互脚本
config/holdings.csv       # 你的基金持仓
.github/workflows/daily.yml  # 每日自动更新 + 发布
```
