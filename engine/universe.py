"""
The universe of markets Agora can pull.

Companies are grouped by sector. Each one has a default benchmark, the index a
strategy's return is compared against. The indices are listed separately because
an index is its own benchmark. Add or remove rows here and the data layer follows.

Coding done with the help of AI, because coding is not the author's strong area.
"""

# (yahoo symbol, friendly name, sector, default benchmark index)
SECURITIES = [
    # Technology
    ("MSFT",  "Microsoft",        "Technology", "^IXIC"),
    ("AAPL",  "Apple",            "Technology", "^IXIC"),
    ("NVDA",  "Nvidia",           "Technology", "^IXIC"),
    ("AMZN",  "Amazon",           "Technology", "^IXIC"),
    ("GOOGL", "Alphabet",         "Technology", "^IXIC"),
    ("META",  "Meta",             "Technology", "^IXIC"),
    ("TSLA",  "Tesla",            "Technology", "^IXIC"),
    # Finance
    ("JPM",   "JPMorgan",         "Finance",    "^GSPC"),
    ("GS",    "Goldman Sachs",    "Finance",    "^GSPC"),
    ("BAC",   "Bank of America",  "Finance",    "^GSPC"),
    ("V",     "Visa",             "Finance",    "^GSPC"),
    ("BRK-B", "Berkshire Hathaway","Finance",   "^GSPC"),
    # Consumer
    ("WMT",   "Walmart",          "Consumer",   "^GSPC"),
    ("KO",    "Coca-Cola",        "Consumer",   "^GSPC"),
    ("MCD",   "McDonald's",       "Consumer",   "^GSPC"),
    ("PG",    "Procter & Gamble", "Consumer",   "^GSPC"),
    ("NKE",   "Nike",             "Consumer",   "^GSPC"),
    ("COST",  "Costco",           "Consumer",   "^GSPC"),
    # Industrial
    ("BA",    "Boeing",           "Industrial", "^GSPC"),
    ("CAT",   "Caterpillar",      "Industrial", "^GSPC"),
    ("GE",    "GE Aerospace",     "Industrial", "^GSPC"),
    ("HON",   "Honeywell",        "Industrial", "^GSPC"),
    # Energy
    ("XOM",   "ExxonMobil",       "Energy",     "^GSPC"),
    ("CVX",   "Chevron",          "Energy",     "^GSPC"),
    # Healthcare
    ("JNJ",   "Johnson & Johnson","Healthcare", "^GSPC"),
    ("UNH",   "UnitedHealth",     "Healthcare", "^GSPC"),
    ("PFE",   "Pfizer",           "Healthcare", "^GSPC"),
    # Crypto
    ("BTC-USD","Bitcoin",         "Crypto",     "^GSPC"),
    ("ETH-USD","Ethereum",        "Crypto",     "^GSPC"),
]

# (yahoo symbol, friendly name)
INDICES = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "Nasdaq Composite"),
    ("^DJI",  "Dow Jones"),
    ("^FTSE", "FTSE 100"),
    ("^RUT",  "Russell 2000"),
    # The indices above are PRICE indices, they leave dividends out. This one puts
    # them back in, so it is the fair yardstick for a strategy that collects dividends.
    ("^SP500TR", "S&P 500 Total Return"),
]

# A small demo of intraday data. Free intraday history is short, so this is only
# the last few days at 1 minute and the last couple of months at 1 hour, for a
# handful of busy names. It shows the same bars in the same shape, just faster.
INTRADAY_DEMO = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "BTC-USD"]

def safe_name(symbol):
    """A filesystem safe name for a symbol, e.g. ^GSPC -> GSPC, BRK-B -> BRK-B."""
    return symbol.replace("^", "").replace("=", "_")
