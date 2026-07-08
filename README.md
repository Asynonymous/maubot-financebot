a simple maubot module that responds with financial data about stock price or cryptocurrency exchange rate.

To install, please see the [standard maubot plugin installation instructions](https://github.com/maubot/maubot/wiki/Usage#adding-a-plugin)

## Supported Backends

This bot supports multiple financial data backends with automatic fallback:

- **[RapidAPI Yahoo Finance](https://rapidapi.com/apidojo/api/yh-finance/)** - Free tier available, supports stocks
- **[Alpha Vantage](https://www.alphavantage.co/support/#api-key)** - Free tier available, supports stocks and cryptocurrency
- **[Financial Modeling Prep (FMP)](https://site.financialmodelingprep.com/developer/docs)** - Free tier available, supports stocks

### Backend Fallback Logic

The bot will automatically:
- Skip any backends with empty or missing API keys
- Try backends sequentially until one returns valid data
- Use the first successful response
- If no backends are configured, inform the user to set up at least one API key
- If all configured backends fail, return an error message

This allows you to use multiple backends as fallback options, which is especially useful if one backend has rate limits or temporary issues.

## Setup

Configure at least one API backend in the config file (either before packaging in the base-config, or directly in the maubot interface after loading):

- **RapidAPI Yahoo Finance**: Set `rapidapiKey` to your RapidAPI key and `rapidapiHost` to the Yahoo Finance API hostname. This is tried first for stock quotes.
- **Alpha Vantage**: Set `alphavantageKey` to your API key from [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
- **Financial Modeling Prep**: Set `fmpKey` to your API key from [Financial Modeling Prep](https://site.financialmodelingprep.com/developer/docs)

You can configure both backends for redundancy, or just one if you prefer. The bot will automatically use whichever backend(s) you have configured.

update the commands you want to use, by default stock data is returned with the `!stonks` command, and crypto data is returned with `!hodl` command. for example:

`!stonks ibm`

would return something like this:

```markdown
**Current data for International Business Machines (https://finance.yahoo.com/quote/IBM) (IBM):**
**Price:** $277.22, ▼-1.36% from previous close @ $281.03
**Open:** $278.20 | **Day:** $278.00-$279.00
**52W:** $162.58-$283.06
```

and

`!hodl btc usd`

would return something like this:

```markdown
**BTC/USD** - 2025-06-15

Current: 105467.27 USD
24h Change: +1.85 (+0.00%) ↑
24h Volume: 34.77 BTC
24h High: 105553.75 USD
24h Low: 105396.90 USD
30d Change: +1967.24 (+1.90%) ↑
6m Change: -669.72 (-0.63%) ↓
```
