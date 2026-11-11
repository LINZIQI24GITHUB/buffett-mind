---
name: buffett-mind
description: 用巴菲特的言行反推他的决策框架，并据此回答投资问题。语料是 48 封股东信（1977–2024，原文）加 610 条带出处问答（1994–2010，多为与会者笔记，属转述），持仓是伯克希尔 13F 全历史（1998–2026，111 个季度）。能回答"他对某家公司说过什么、实际怎么做的、言行是否一致"，以及"按他的框架，这个问题他会怎么看"——后者必须标注推演。当用户提到巴菲特、伯克希尔、他的持仓、他是否言行一致、按他的框架看某个投资问题时使用。
---

# 巴菲特思路（buffett-mind）

> **Homepage** · https://finansi.work/skills/buffett-mind
> **Install** · 把本目录复制到 `.agents/skills/buffett-mind`；仓库自带可运行快照，clone 即可跑 `python scripts/demo.py`

不是语录库，是**证据库 + 框架**。

核心主张只有一句：**每条结论都要能追到一句原话和一笔操作，追不到就降低结论强度，追不到就说"他没表态"。**

## 三条硬规则（违反任何一条，输出作废）

**1. 原话必须校验**

任何引语都要过 `scripts/quote.py --verify`。校验不过的，要么改写措辞（可能曲解），要么是伪语录，一律不得作为依据。

```bash
python scripts/quote.py --verify "price is what you pay, value is what you get"
# ✓ 命中 doc 37｜2013｜2013 股东信
python scripts/quote.py --verify "如果你不想持有十年，就不要持有十分钟"
# ✗ 未找到原文（拒绝引用）
```

**2. 市值变化必须分解**

13F 报的是季末市值，跌了不等于减仓。任何"他加仓/减仓"的判断，先跑分解：

```bash
python scripts/decompose.py --from 2019-12-31 --to 2020-03-31
# 价格效应 -62.5B｜数量效应 -1.8B  → 几乎全是股价，仓位没动
```

**3. 推演必须标注**

「按他的框架看 X」属于外推，首行必须写「**推演 · 非巴菲特本人观点**」。他没表过态的问题，直接说没表过态。

## 什么时候用

- 「巴菲特怎么看黄金 / 银行 / 苹果」——先查原话，再看持仓
- 「他说长期持有，可实际持有多久」——他有 154 笔决策，中位 2 年
- 「他到底有没有言行一致」——三级分类：明确冲突 / 需要语境 / 行为漂移
- 「按他的框架，这个投资问题他会怎么想」

## 什么时候别用

- 要他"点评"某只票的买卖点——他从不给建议，我们也不给
- 美股之外的个股分析——13F 只覆盖美股多头
- 预测涨跌、目标价——框架里没有这个能力

## 命令

```bash
# 语料与索引（首次运行，需联网，约 2 分钟）
python scripts/build_corpus.py --out corpus

# 13F 全历史（需联网，约 10 分钟；已缓存则秒级）
python scripts/fetch_raw.py
python scripts/build_holdings.py --out data
python scripts/build_prices.py          # CUSIP→代码 + 季度 VWAP
python scripts/build_splits.py          # 拆股事件

# 日常查询
python scripts/quote.py "airlines" --limit 5        # 检索原话
python scripts/timeline.py --company AAPL           # 言行时间线
python scripts/holdings.py top --period 2026-06-30  # 某季持仓
python scripts/holdings.py changes --period 2026-06-30
python scripts/returns.py --top 12                  # 每笔决策的事后收益
python scripts/decompose.py --scan                  # 哪些季度真在买卖
python scripts/reconcile.py                         # 言行配对索引
python scripts/answer.py --question "现在怎么看黄金"  # 回答证据包
python scripts/demo.py                             # 离线自检
```

## 视频语料（转写）

年会与访谈可以转写成带时间戳的段落，并入同一套检索，引用能直接跳到秒数。

```bash
# 转写（需 .venv-whisper，模型在 .models/whisper-small）
python scripts/transcribe_video.py --url "<youtube url>" --out data/video/<name>.jsonl

# 入库（按 ~700 字符合并，生成 ?t=秒 深链）
python scripts/build_video_corpus.py --segments data/video/<name>.jsonl     --title "2024 伯克希尔股东大会" --url "<url>" --year 2024

# 数字抽检（ASR 错在数字和专名，必须人工过一遍）
python scripts/validate_transcript.py --segments data/video/<name>.jsonl --tsv out/numbers.tsv
```

实测：small + int8 + VAD 在 14 核 CPU 上约 12 倍实时；转写稿只落盘，不进对话上下文。

## 视频语料：15 场年会 + 提问/回答标注

2011–2025 的伯克希尔股东大会已转写成带时间戳的段落，共 6,239 段。
每段标了 `[巴菲特]` / `[芒格]` / `[提问]`——三人分开，检索时可以直接用标签过滤。

**标注方法与置信度**：纯声纹聚类在这批素材上不可靠（两人都是老年男声、单段只有 2–4 秒，
实测把主持人开场和巴菲特回答混在一起）。所以改成「高精度、低召回」的规则：
巴菲特点名芒格后的短回答、芒格口头禅（I have nothing to add / I agree / That's right）
才标 `[芒格]`，其余默认 `[巴菲特]`。**没标到的芒格发言会留在巴菲特名下，宁漏不错。**

```bash
# 转写（长音频自动切块，避免内存溢出）
python scripts/transcribe_video.py --url "<youtube url>" --out data/video/2024-meeting.jsonl

# 标注提问/回答 + 分人（巴菲特/芒格/其他）
python scripts/label_speakers.py --segments data/video/2024-meeting.jsonl --inplace
python scripts/label_who.py --segments data/video/2024-meeting.jsonl --inplace
# 2020（芒格缺席）与 2024 起（已去世）加 --no-munger

# 入库（按说话人切段，带 ?t=秒 深链）
python scripts/build_video_corpus.py --segments data/video/2024-meeting.jsonl \
    --title "2024 伯克希尔股东大会" --url "<url>" --year 2024
```

**边界**：这是文本启发式，只能分「提问/回答」，**分不出巴菲特和芒格**。
真正的说话人分离需要声纹（pyannote 需 GPU 与 HF token），本机未做。
引用时如果要点名「这是巴菲特说的」，仍需人工确认上下文。

## A 股场景：用他的尺子量

他对 A 股公司几乎没有公开表态（658 篇语料里，沪深300 前十大零命中），
所以这不是"他怎么看"，而是**用他的尺子量**——输出必须标「推演」。

```bash
# 在线：东方财富数据中心（只走 HTTPS，代理环境可用）
python scripts/ashare_fit.py --codes 600519,300750,600036

# 离线：本地 10 年财报（仅覆盖 4 家）
python scripts/ashare_fit.py --codes 600519 --local
```

指标映射：R2 护城河 → 十年 ROE 均值与最低值、毛利率；R3 安全边际 → PE_TTM；
R7 资本配置 → 股息率；R1 能力圈 → 行业（按代码映射，不按公司名）。

**必须说明的三点**：银行没有毛利率口径；他没有 A 股框架（汇率、治理、政策不在模型里）；
"能力圈内"不等于"该买"，估值不便宜时要直接说。

## 输入契约

| 需要 | 说明 |
|---|---|
| 问题或公司名 | 中文/英文/代码都行，实体表覆盖 17 家 |
| 联网（仅首次） | 从公开源重建语料/持仓时需要；仓库快照可直接离线 |

## 输出风格：第一人称，像在路演

回答任何投资问题时，**用巴菲特的第一人称讲**，不是复述资料：

- 先说结论一句话，再给数字，再讲道理，最后承认看不清的地方
- 至少 3 个可核对数字（股数、市值、百分比、年数）
- 句长 ≤25 字为主，超过 40 字必须拆
- 不用行话、不用感叹号、不喊口号、不给点位预测
- 引用逐字，附 doc_id；拿不准就转述，不编引号
- 可以有表格，但表格是配角：用来放数字，列名也用他的口吻
- 开头标「推演 · 非巴菲特本人观点」，结尾写明 AI 生成、不构成投资建议

完整语气规范见 `references/voice.md`（含语料统计：平均句长 18.4 词、42.6% 的句子带数字）。

```bash
python scripts/answer.py --question "苹果还值得长期持有吗" --voice
```

## 输出格式

`answer.py` 产出的是**证据包**，不是结论：

```
# 证据包：现在怎么看黄金
- 归类：资产、时机   命中规则：R11 资产分类
## A. 他本人说过什么（逐条可回溯，带 doc_id 与链接）
## B. 他实际怎么做的（带季度与股数）
## C. 回答时必须遵守（标注推演、至少 1 原话 + 1 操作）
## D. 证据不足提示
```

结论由调用它的 Agent 基于证据包写。

## 评测卡

| 项 | 判定标准 |
|---|---|
| 引语可回溯 | 每条引语能通过 `--verify`，带 doc_id 与链接 |
| 操作可核对 | 每条持仓判断带季度与股数，重大变动经过分解 |
| 冲突分级 | 不用"打脸"一词，按三级分类呈现 |
| 推演标注 | 外推结论首行标注「推演」，无表态时明说 |
| 自检 | `demo.py` 全部通过 |

## 已知局限

- **13F 只覆盖美股多头**：不含海外持仓、债券、私募、空头；2013 年前的文本表格已解析，但个别季度存在缺价标的
- **问答部分是二手笔记**：610 条里 390 条标注 Notes（Tilson/Boodell/Bruni 的现场记录），属转述级；且只覆盖 1994–2010，2011 年后的年会没有文字稿
- **语料是英文的**：中文提问会先映射到英文检索词，可能漏检
- **610 条问答是二手整理**（Buffett FAQ），不是逐字稿；年会视频没有公开文字稿
- **13F 有 45 天滞后**，且只报股数不报成本，成本用季度 VWAP 近似
- 17 家实体之外的标的，需要先补 `scripts/entities.py`
