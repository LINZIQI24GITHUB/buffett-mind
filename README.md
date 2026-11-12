# Buffett Mind · 巴菲特思路

[![demo](https://img.shields.io/badge/demo-6%2F6%20passing-brightgreen)](scripts/demo.py)
[![video](https://img.shields.io/badge/年会视频-15%20场%20·%206%2C769%20段-red)](corpus/)
[![13F](https://img.shields.io/badge/13F-111%20quarters-blue)](data/holdings.csv)
[![letters](https://img.shields.io/badge/shareholder%20letters-48-orange)](corpus/)
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

**用他自己的原话和真实持仓，反推决策框架；每一句都能查，每一个仓位都能对。**

[English](README_EN.md) · [快速开始](#快速开始) · [视频语料](#最值钱的部分20112025-年会视频语料) · [数据](#数据与分级)

**Homepage** · <https://finansi.work/skills/buffett-mind>
**Install** · 复制本目录到 `.agents/skills/buffett-mind`，clone 后即可离线跑 `python scripts/demo.py`

![第一人称回答](assets/answer-demo.png)

## 这是什么

不是又一本语录集。它做三件事：

1. **摆证据**——他对同类问题说过什么（年份、doc_id、原文链接、视频时间点），他实际怎么做的（季度、股数、成本）
2. **给框架**——11 条从言行里归纳的规则，每条都挂着出处；没有出处的参数进不了代码（CI 会拦）
3. **标推演**——他没表过态的问题，直说没表过态

## 最值钱的部分：2011–2025 年会视频语料

2011 年之后，伯克希尔不再发布年会文字稿。公开世界能拿到的只有视频。

我们把 **15 场年会（2011–2025）** 的完整录音转写下来，按发言人切开，逐段打时间戳：

| 项目 | 数量 |
|---|---:|
| 年会 | **15 场**（2011–2025） |
| 转写片段 | **6,769 段** |
| 其中巴菲特 | **5,280 段** |
| 芒格 | 103 段（只标可确证的） |
| 现场提问 | 1,385 段 |
| 时间戳 | 每段带 `?t=秒`，可跳回原视频 |

**为什么它比文字稿值钱：**

1. **2011 年后没有官方文字稿**——这段历史只存在于视频里
2. **问答是即时的**——能看出他临场怎么想，而不是事后怎么写进信里
3. **能和 13F 对齐**——同一季度他说了什么、买了什么，放在一起看言行是否一致

真实检索输出（`scripts/quote.py`）：

```bash
$ python scripts/quote.py "gravity" --limit 3
[问 1753] 2013 · 2013 伯克希尔股东大会 67:27
    …interest rates are to asset prices, sort of like 【gravity】 is to the apple…
    https://www.youtube.com/watch?v=b1-QzoQmprM?t=4047
[问 5601] 2021 · 2021 伯克希尔股东大会 86:17
    …interest rates basically are to the value of assets, what 【gravity】 is to matter…
[问 5603] 2021 · 2021 伯克希尔股东大会 88:43
    …if I could reduce 【gravity】, it's pulled by about 80%… I'd be in the Tokyo Olympics jumping…
```

他 2013 年说「利率之于资产价格，就像重力之于苹果」，2021 年又说了一遍，还补了一句「如果重力减少 80%，我能在东京奥运会跳远」。这种临场的比喻，只有视频里有。

> 转写是机器做的，个别词会有错；引用前请回看原视频时间点。芒格只标高置信段，其余默认归巴菲特。

## 三条硬规则

违反任何一条，输出作废：

1. **原话必须校验**——引语要过 `quote.py --verify`，不过的一律不得作为依据
2. **市值变化必须分解**——13F 报的是季末市值，跌了不等于减仓
3. **推演必须标注**——他没表过态的问题，直接说没表过态

第 1 条不是形式主义：中文世界流传最广的两句「巴菲特名言」——「不想持有十年就不要持有十分钟」和
「别人恐惧我贪婪」——**都是真的**。但引用的人常忽略：他 154 笔决策的**持有期中位数只有 2.3 年**。

真话被断章取义，比假话更难识破。

## 13F 里挖出来的三个反常识结论

对 1998Q4–2026Q2 的 111 个季度、267 个持仓做统计（`scripts/behavior.py`、`behavior_tiers.py`）：

**1. 他并不是「永远持有」。** 237 个窗口内建仓的持仓，持有期**中位 9 个季度**，28% 不到一年，只有 10% 超过十年。

**2. 大仓位是另一个物种。**

| 仓位分位 | 权重区间 | 中位持有 | 中位收益 | 持有 >20 季 |
|---|---|---:|---:|---:|
| 最小 20% | 0–0.1% | **2 季** | +9% | 6% |
| 最大 20% | 1.6–51% | **28 季** | **+114%** | 61% |

苹果 42 季 +1073%，美国运通 111 季 +1526%；反例是卡夫亨氏 44 季 −45%。

**3. 「危机才加仓」是误读。** 组合市值大跌的季度，94% 有加仓；大涨的季度，98% 也有加仓——加仓是常态，不是信号。

## 他能回答什么

| 问题 | 命令 |
|---|---|
| 他对某家公司说过什么？（含视频时间点） | `quote.py` / `answer.py` |
| 他什么时候买的、买了多少、后来怎么处理？ | `timeline.py` / `holdings.py` |
| 他说长期持有，实际持有多久？ | `returns.py` / `behavior.py` |
| 这季度市值跌了，是股价跌还是减仓？ | `decompose.py` |
| 他到底有没有言行一致？ | `reconcile.py` |
| 「看得懂」「生意稳」到底指什么？ | `references/understand.md`、`stable-business.md` |
| 他怎么判断增长率？ | `references/growth.md` |
| 这笔生意按他的折现率值多少？ | `valuation.py`（10% 折现 + 两阶段） |
| 他在这类生意上买过什么？ | `judge_cases.py`（判例库，74 条） |
| 按他的框架，这只票贵不贵？ | `valuation.py` + `judge_cases.py`（推演） |

## 为什么不一样

| | 纯提示词包 | 信件合集 | **本仓库** |
|---|---|---|---|
| 股东信全文 + 检索 | 摘录 | ✅ | ✅ 48 封 |
| **2011–2025 年会视频转写** | ❌ | ❌ | ✅ **15 场 / 6,769 段** |
| **按发言人切分（巴菲特/芒格/提问）** | ❌ | ❌ | ✅ |
| 13F 全历史持仓 | ❌ | ❌ | ✅ 111 季度 |
| 建仓成本（VWAP、拆股） | ❌ | ❌ | ✅ |
| 引语校验（拒绝假引语） | ❌ | ❌ | ✅ |
| 言行对账 | ❌ | ❌ | ✅ 133 组 |
| 行为模式统计（核心 vs 边缘） | ❌ | ❌ | ✅ |
| 参数出处审计（CI 强制） | ❌ | ❌ | ✅ |
| 语气量化 | ❌ | ❌ | ✅ 18,568 句 |
| A 股适配 | ❌ | ❌ | ✅ |

![自检输出](assets/demo-output.png)

## 快速开始

```bash
pip install -r requirements.txt
python scripts/demo.py          # 仓库自带快照，6/6

# 自己重建全量语料（联网约 15 分钟）
python scripts/build_corpus.py --out corpus     # 48 封信 + 610 条问答
python scripts/fetch_raw.py                     # 13F 原始文件
python scripts/build_holdings.py --out data     # 逐季持仓
python scripts/build_prices.py                  # CUSIP→代码 + 季度 VWAP
python scripts/build_splits.py                  # 拆股事件

# 视频语料（需 yt-dlp + faster-whisper，本机跑）
python scripts/build_video_corpus.py --years 2011-2025
```

## 估值：用他的折现率，不用我的偏好

```bash
python scripts/valuation.py --code 600519 --growth 6 --two-stage
```

- 折现率 **10%**：1991 年股东信他自己的例子（doc 15）；2003 年他说不会因为国债收益率低就降门槛（doc 159）
- 增长 **前 3 年外推 + 之后永续 3%**：两阶段
- 安全边际 30% 是可调参数，不是他的原话——所以它被写在帮助里，不是藏在代码里

工具只把「你的增长判断」翻译成价格，判断本身由你下。

## 参数出处审计

```bash
python scripts/audit_params.py
```

检查两件事：每条框架规则是否至少有一个 doc 引用；筛选脚本里是否有无出处阈值。
**CI 里强制跑**，没有出处的参数过不了构建。

## 数据与分级

| 级别 | 来源 | 数量 | 性质 |
|---|---|---|---|
| 一级 | 股东信 1977–2024 | 48 封 | 原文，可逐字引用 |
| 二级 | 年会/演讲问答 1994–2010 | 610 条 | 与会者笔记（390 条标注 Notes），属转述 |
| 三级 | 年会视频转写 2011–2025 | 6,769 段 | **机器转写**，按发言人切分，带时间戳 |

二级只标「据年会笔记」，不当逐字原话；三级标「视频转写」，引用前回看时间点。

## 目录

```
SKILL.md              技能入口（给 Agent 读的运行说明）
references/           framework / voice / understand / stable-business / growth / parameter-audit
scripts/              51 个脚本：语料、持仓、检索、估值、行为统计、A 股
corpus/               index.sqlite（7,427 条）+ 股东信原文
data/                 holdings.csv（111 季 14,060 行）、vwap、splits、cusip-map、cases.jsonl
examples/             第一人称回答、播客脚本、A 股样例
assets/               演示图
tests/                pytest
```

## 局限

- **视频转写有错词**：机器识别 + 说话人分离，引用前回看时间点；芒格只标高置信段（约 100 段），其余默认归巴菲特
- **覆盖 2011–2025**：2026 年年会由 Greg Abel 主持，未纳入
- 13F 只覆盖美股多头（不含海外、债券、私募、空头），有 45 天滞后
- 成本用季度 VWAP 近似，不是真实成交价
- 13F 结构化数据自 2013 年起；更早为文本表格，已解析但个别季度缺价
- 实体表覆盖 17 家公司，扩展需改 `scripts/entities.py`

## License

MIT。引用原文请注明 Berkshire Hathaway 出处；问答汇编与视频转写仅本地使用、不随仓库分发。
