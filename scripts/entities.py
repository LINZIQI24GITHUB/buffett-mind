"""把 13F 的发行人、语料里的提法、用户嘴里的中文，指到同一个实体上。

13F 写 "APPLE INC"，股东信写 "Apple"，用户说 "苹果" / "AAPL"。
不做这层映射，"他说了什么"和"他做了什么"永远对不上。

范围：先覆盖 13F 里市值最大的 17 家，够支撑时间线与对账的样例。
新增实体只需在 COMPANIES 里加一行。
"""
from __future__ import annotations

COMPANIES: dict[str, dict] = {
    "AAPL": {"name": "苹果", "aliases": ["APPLE INC", "Apple Inc", "Apple", "苹果", "苹果公司"]},
    "KO": {"name": "可口可乐", "aliases": ["COCA COLA CO", "Coca-Cola", "Coca Cola", "可口可乐"]},
    "AXP": {"name": "美国运通", "aliases": ["AMERICAN EXPRESS CO", "American Express", "美国运通", "运通"]},
    "BAC": {"name": "美国银行", "aliases": ["BANK OF AMER CORP", "Bank of America", "美国银行", "美银"]},
    "WFC": {"name": "富国银行", "aliases": ["WELLS FARGO", "Wells Fargo", "富国银行", "富国"]},
    "KHC": {"name": "卡夫亨氏", "aliases": ["KRAFT HEINZ", "Kraft Heinz", "卡夫亨氏", "卡夫"]},
    "MCO": {"name": "穆迪", "aliases": ["MOODYS CORP", "Moody's", "Moodys", "穆迪"]},
    "MA": {"name": "万事达", "aliases": ["MASTERCARD INC", "Mastercard", "万事达"]},
    "V": {"name": "维萨", "aliases": ["VISA INC", "Visa Inc", "Visa", "维萨"]},
    "COST": {"name": "好市多", "aliases": ["COSTCO WHSL", "Costco", "好市多"]},
    "CVX": {"name": "雪佛龙", "aliases": ["CHEVRON CORPORATION", "Chevron", "雪佛龙"]},
    "OXY": {"name": "西方石油", "aliases": ["OCCIDENTAL PETE CORP", "Occidental", "西方石油"]},
    "AAL": {"name": "美国航空", "aliases": ["AMERICAN AIRLS GROUP", "American Airlines", "美国航空"]},
    "DAL": {"name": "达美航空", "aliases": ["DELTA AIR LINES", "Delta Air Lines", "达美航空", "达美"]},
    "LUV": {"name": "西南航空", "aliases": ["SOUTHWEST AIRLS", "Southwest Airlines", "西南航空"]},
    "UAL": {"name": "联合航空", "aliases": ["UNITED AIRLS", "United Airlines", "联合航空", "美联航"]},
    "IBM": {"name": "IBM", "aliases": ["INTERNATIONAL BUSINESS MACHS", "IBM", "国际商业机器"]},
}


# 行业级检索：有些话他说的是整个行业，不会点公司名。
# 例："airlines" 出现在 2020 年会上，但那句话同时适用于四家航空公司。
INDUSTRIES = {
    "airline": {"terms": ["airlines", "airline industry"],
                "tickers": ["AAL", "DAL", "LUV", "UAL"]},
    "bank": {"terms": ["banks", "banking industry"], "tickers": ["BAC", "WFC"]},
    "tech": {"terms": ["technology companies", "tech companies"], "tickers": ["AAPL", "IBM"]},
}

COMPANY_INDUSTRY = {t: name for name, cfg in INDUSTRIES.items() for t in cfg["tickers"]}


def industry_of(ticker: str) -> dict | None:
    name = COMPANY_INDUSTRY.get(ticker)
    return INDUSTRIES.get(name) if name else None


def resolve(text: str) -> tuple[str, dict] | tuple[None, None]:
    """把用户输入（代码 / 中文名 / 英文名）解析成实体。"""
    s = str(text).strip()
    up = s.upper()
    if up in COMPANIES:
        return up, COMPANIES[up]
    for ticker, info in COMPANIES.items():
        for alias in info["aliases"]:
            if alias.upper() == up or alias.lower() in s.lower():
                return ticker, info
    return None, None


def english_aliases(info: dict) -> list[str]:
    """语料是英文的，只拿英文别名去检索。"""
    return [a for a in info["aliases"] if a.isascii()]


def match_issuer(issuer: str, ticker: str) -> bool:
    """13F 的发行人名是否属于某实体。"""
    info = COMPANIES[ticker]
    up = issuer.upper()
    for alias in info["aliases"]:
        if alias.isascii() and alias.upper() in up:
            return True
    return False
