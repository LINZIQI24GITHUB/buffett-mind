# 巴菲特怎么判断增长率

> 结论先说：**他不预测增长率。他筛选「增长可以被预测」的生意，然后给一个保守的数。**

## 一、增长是价值的一部分，不是独立目标

**1992 年股东信（doc 16）**：

> "Growth is always a component in the calculation of value, constituting a variable whose importance
> can range from negligible to enormous and **whose impact can be negative as well as positive**."

三点：

1. 增长不是「好」或「坏」，是**变量**
2. 重要性可以从「可忽略」到「极大」
3. **可以是负的**——烧钱换来的增长会毁灭价值

## 二、他挑的是「容易判断的案例」，不是「高增长的案例」

**1993 年股东信（doc 17）**：

> "Why… should Charlie and I now think we can predict the future of other **rapidly-evolving businesses**?
> We'll stick instead with **the easy cases**. Why search for a needle buried in a haystack when one is
> sitting in plain sight?"

**2009 年问答（doc 100）**：

> "You might look at McDonald's, because it is **number one and will probably always be number one**.
> They have **share of mind**. What about Oracle? **Too hard.** GM? **Too hard.** You can't predict the
> future for these two companies. **Too many variables.**"

**所以「能判断增长」的前提是：**

- 行业龙头且地位稳固（number one and always will be）
- 有 share of mind（心智份额）
- 变量少（too many variables 是排除理由）

## 三、增长的三个来源，他逐个看

| 来源 | 他的说法 | 出处 |
|---|---|---|
| **价**（提价） | 喜诗销量年增仅 2%，靠定价权让利润大涨 | 2007 信 doc 31、2014 信 doc 38 |
| **量**（销量） | 可乐「二十年后会卖更多份」——但要能保证 | 1998 问答 doc 342 |
| **资本效率** | 增长只需 "minor amounts of incremental investment" 才值钱 | 2014 信 doc 38 |

**最理想的是「价涨、量稳、几乎不投钱」**——喜诗糖果。

**最差的是「量增、价跌、要不断投钱」**——他反复批评的资本密集型增长。

## 四、他实际用的增长率是多少

**1991 年股东信（doc 15）**，他举例算媒体资产：

> "…ownership of a media property could be construed as akin to owning a perpetual annuity **set to grow
> at 6% a year**. Say, next, that a **discount rate of 10%** was used…"

**他举例用的是 6%，不是 15%、20%。**

这和他选股的结果一致：喜诗销量 2%、可乐份数缓慢增长——他真正买到的增长，都是个位数。

## 五、判断流程（从他的原话还原）

```
① 这个生意十年后还在卖同样的东西吗？        → 不是，直接跳过（1993 信）
② 它是行业第一、且有心智份额吗？            → 不是，too hard（2009 问答）
③ 增长来自提价还是烧钱扩张？                → 烧钱扩张，增长是负价值（1992 信）
④ 增长需要多少增量资本？                    → 需要很多，打折（2014 信）
⑤ 给一个保守的 g（他的例子：6%），再打折      → 估值
```

## 六、和估值工具的关系

`scripts/valuation.py` 里的 g **不是预测值，是保守假设**：

| 生意类型 | 合理的 g | 理由 |
|---|---|---|
| 喜诗型（价升量稳、低资本） | 5–6% | 他的原例就是 6% |
| 可乐型（量增、品牌稳） | 5–7% | 全球份数增长 |
| 公用事业（受管制） | 2–4% | 提价受管制约束 |
| 高增长科技 | **不给 g** | too many variables，直接排除 |

**任何超过 10% 的永续 g，都要先证明「凭什么能持续二十年」——他从不做这种假设。**

## 一句话

> 他不问「这家公司能增长多少」，他问「**这家公司的增长，我能不能大致算出来**」。
> 算得出来才给 g，给的时候往保守里给（6% 上下）；算不出来就不买，不管它看起来多能长。
