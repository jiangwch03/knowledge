# Firecrawl 单页抓取与整站爬取（项目参考）

> 记录日期：2026-08-01  
> 目的：对照 Firecrawl 实现，方便本项目（Crawl4AI + Agent）借鉴，不替代现有链路。

## 1. 总体结论

| 能力 | Firecrawl | 本项目 |
|------|-----------|--------|
| 单页抓取 | 有（scrape，同步返回） | probe / trial 等偏单页验证 |
| 整站爬取 | 有（crawl，异步任务） | 正式 crawl 长任务 |
| 跟用户沟通 | 基本没有 | 有（规划、试爬、人工确认） |
| 浏览器渲染 | Playwright（自托管）/ 云上更强引擎 | Crawl4AI（底层也是 Playwright） |
| PDF / 文档 | 有专用抓法 | 需按自身链路核对 |

一句话：Firecrawl 偏「你说完就爬」的 API；本项目偏「先沟通再爬」的顾问式入库。

---

## 2. 单页抓取 vs 整站爬取

### 单页（scrape）

流程：给一个网址 → 当场抓完 → 直接返回内容。

特点：

- 同步等待结果
- 通常只处理这一页
- 底层走「引擎 + 清洗」

### 整站（crawl）

流程：给起始网址 → 立刻返回任务 ID → 后台边发现链接边爬 → 再查进度/结果。

特点：

- 异步任务
- **不是**先列完全站所有网址再开爬
- 而是：**边发现、边并发爬**
- 真正抓每一页，仍复用单页那套抓取能力

```text
整站 = 找链接 + 调度
单页抓取 = 真正打开/下载某一页

整站发现新链接后 → 每个链接再当「单页」去抓
→ 抓完可能再发现新链接 → 继续入队
→ 直到没有新链接或触达深度/数量上限
```

sitemap 有的话，开头能多知道一些网址；站内链接仍可能爬着才发现。

---

## 3. 爬取策略会不会按每个链接动态调整？

**整站规则基本固定**（爬多深、包含/排除路径、是否外链等），不会每个链接重新规划一套策略，也不会跟用户商量。

**会动态变的是「这一页怎么抓」**，偏自动兜底：

1. 链接像 PDF / Word 等 → 走文件下载 + 专用解析  
2. 简单下载不行 → 再换浏览器等方式试  
3. 碰到反爬迹象 → 可能加重试 / 换更强方式  

本项目若要借鉴：优先借鉴「按链接类型换抓法」和「失败再升级」，不必照搬「完全不问人」。

---

## 4. 真正干活的代码在哪（Firecrawl 开源）

总调度：

- `apps/api/src/scraper/scrapeURL/index.ts`（特征标记、引擎瀑布、失败加能力重试）
- `apps/api/src/scraper/scrapeURL/engines/index.ts`（可选引擎列表、排序）

### 4.1 普通网页：直接下载

文件：`apps/api/src/scraper/scrapeURL/engines/fetch/index.ts`

- 用 HTTP 客户端下载页面 HTML
- 不跑 JavaScript
- 适合静态页

### 4.2 需要 JS 的网页：Playwright

API 侧只负责调用微服务：

- `apps/api/src/scraper/scrapeURL/engines/playwright/index.ts`  
  → `POST` 到 `PLAYWRIGHT_MICROSERVICE_URL`

真正开浏览器：

- `apps/playwright-service-ts/api.ts`
  - 启动 Chromium
  - `page.goto(url)`
  - `page.content()` 取渲染后的 HTML

### 4.3 PDF

文件：`apps/api/src/scraper/scrapeURL/engines/pdf/index.ts`

- 先下载 PDF 文件
- 再解析成可读文本 / Markdown
- **不是**「整个网页等于一个 PDF」，而是链接本身指向 PDF 文件时用这套

### 4.4 Word / Excel 等文档

文件：`apps/api/src/scraper/scrapeURL/engines/document/index.ts`

- 先下载文件
- 再用转换器变成 HTML

### 4.5 如何识别要走 PDF / 文档

- URL 后缀判断：`.pdf` / `.docx` 等  
  → `scrapeURL/index.ts` 里 `buildFeatureFlags`
- 下载后看 `Content-Type`  
  → `engines/utils/specialtyHandler.ts`  
  → 发现是 PDF/文档就切换专用引擎

### 4.6 失败再换引擎 / 反爬加重

- 引擎一个个试：`scrapeURL/index.ts` 里瀑布循环
- 状态码像被拦（如 401/403/429）且代理为 auto → 加更强代理标记再试
- 注意：更强反爬能力很多依赖云上 `fire-engine`，开源自托管常见只有 **fetch + Playwright**

---

## 5. Playwright 是什么？Crawl4AI 有没有？

**Playwright**：用代码控制真实浏览器打开网页、等加载、再取内容。  
和「直接下载 HTML」比，能拿到 JS 渲染后的页面。

**Crawl4AI 底层也用 Playwright**（或同类浏览器自动化）。

对照：

| | Firecrawl 自托管 | 本项目 |
|--|------------------|--------|
| 浏览器层 | Playwright 微服务 | Crawl4AI（内部开浏览器） |
| 额外封装 | 引擎瀑布、清洗、队列 | Agent 规划、试爬、入库 RAG |

技术底层类似，产品形态不同。

---

## 6. PDF / 文档 / Markdown 别搞混

爬站时，链接不一定都是「网页」：

| 链接类型 | 是什么 | 怎么处理 |
|----------|--------|----------|
| 普通页面 | HTML，可能要跑 JS | 下载或浏览器渲染 |
| `.pdf` | PDF 文件 | 下载 + 专用解析 |
| `.docx` / `.xlsx` 等 | Office 文件 | 下载 + 专用解析 |
| `.md` | Markdown 文本文件 | 一般直接下载即可（已是文字，通常不必像 PDF 那样复杂解析） |

要点：

- 不是「网页整体是一个 PDF」
- 而是「有的链接指向附件文件，要换抓法」
- `.md` 和 PDF「都可能是文件链接」，但 `.md` 处理简单得多

---

## 7. 对本项目可借鉴点（精简）

1. **整站 = 发现链接 + 单页抓取复用**，不必另写两套互不相干的抓取内核。  
2. **边发现边爬**，不必强求先枚举全站 URL。  
3. **按链接类型分流**：网页 / PDF / 文档分开处理。  
4. **失败升级**：简单方式不行再上浏览器（本项目已有 Crawl4AI，可再考虑「轻量 HTTP 先试」）。  
5. **智能规划、跟人确认**是本项目优势，Firecrawl 没有对等物，继续保持即可。

---

## 8. 相关文档

- 搜索层选型（Tavily）：[搜索能力选型-Tavily.md](./搜索能力选型-Tavily.md)
- Firecrawl 源码关键目录：
  - `apps/api/src/scraper/scrapeURL/`
  - `apps/api/src/controllers/v2/scrape.ts`
  - `apps/api/src/controllers/v2/crawl.ts`
  - `apps/playwright-service-ts/api.ts`
