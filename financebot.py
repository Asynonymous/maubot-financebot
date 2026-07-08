from typing import Optional, Type, List
from urllib.parse import quote

from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import Plugin, MessageEvent
from maubot.handlers import command

# not necessary, as it's imported by maubot already
#import asyncio
#import aiohttp

class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("alphavantageKey")
        helper.copy("fmpKey")
        helper.copy("fmpFreeTier")
        helper.copy("rapidapiKey")
        helper.copy("rapidapiHost")
        helper.copy("stocktrigger")
        helper.copy("cryptotrigger")

class FinanceBot(Plugin):
    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    def _get_available_backends(self) -> List[str]:
        """Get list of available backends that have API keys configured."""
        backends = []
        rapidapi_key = self.config.get("rapidapiKey", "")
        if rapidapi_key and isinstance(rapidapi_key, str) and rapidapi_key.strip():
            backends.append("rapidapi")
        av_key = self.config.get("alphavantageKey", "")
        if av_key and isinstance(av_key, str) and av_key.strip():
            backends.append("alphavantage")
        fmp_key = self.config.get("fmpKey", "")
        if fmp_key and isinstance(fmp_key, str) and fmp_key.strip():
            backends.append("fmp")
        return backends

    async def _get_json(
            self, backend: str, label: str, url: str,
            headers: Optional[dict] = None) -> Optional[object]:
        """Fetch JSON from a provider and handle HTTP/non-JSON failures."""
        try:
            async with self.http.get(url, headers=headers) as response:
                body = await response.text()
                if response.status != 200:
                    self.log.warning(
                        f"{backend} {label} returned HTTP {response.status}: {body[:300]}"
                    )
                    return None
                try:
                    return await response.json(content_type=None)
                except ValueError:
                    self.log.warning(f"{backend} {label} returned non-JSON response: {body[:300]}")
                    return None
        except Exception as e:
            self.log.exception(f"{backend} {label} request failed: {e}")
            return None

    async def _fetch_rapidapi_data(self, ticker: str) -> Optional[dict]:
        """Fetch stock data from RapidAPI's Yahoo Finance endpoint."""
        try:
            api_key = self.config["rapidapiKey"]
            api_host = self.config.get("rapidapiHost", "yh-finance.p.rapidapi.com")
            url = f"https://{api_host}/market/v2/get-quotes?symbols={quote(ticker, safe='')}"
            headers = {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": api_host,
            }

            data = await self._get_json("RapidAPI Yahoo", "quote", url, headers=headers)
            if not isinstance(data, dict):
                return None

            results = data.get("quoteResponse", {}).get("result", [])
            if not results:
                self.log.warning("RapidAPI Yahoo quote data empty or invalid")
                return None

            quote_data = results[0]
            current_price = float(quote_data.get("regularMarketPrice", 0))
            if current_price == 0:
                self.log.warning("RapidAPI Yahoo returned zero price")
                return None

            previous_close = float(quote_data.get("regularMarketPreviousClose", current_price))
            open_price = float(quote_data.get("regularMarketOpen", current_price))
            change = float(quote_data.get("regularMarketChange", current_price - previous_close))
            change_percent_value = quote_data.get("regularMarketChangePercent")
            if change_percent_value is None:
                change_percent = f"{(change / previous_close * 100):.2f}%" if previous_close > 0 else "0.00%"
            else:
                change_percent = f"{float(change_percent_value):.2f}%"

            return {
                "current_price": current_price,
                "open_price": open_price,
                "previous_close": previous_close,
                "change": change,
                "change_percent": change_percent,
                "company_name": quote_data.get("longName") or quote_data.get("shortName") or ticker,
                "day_high": float(quote_data.get("regularMarketDayHigh") or 0),
                "day_low": float(quote_data.get("regularMarketDayLow") or 0),
                "high_52w": float(quote_data.get("fiftyTwoWeekHigh") or 0),
                "low_52w": float(quote_data.get("fiftyTwoWeekLow") or 0),
            }
        except Exception as e:
            self.log.exception(f"RapidAPI Yahoo exception: {e}")
            return None

    async def _fetch_alphavantage_data(self, ticker: str) -> Optional[dict]:
        """Fetch stock data from Alpha Vantage API."""
        try:
            api_key = self.config["alphavantageKey"]
            quote_url = f'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol={ticker}&apikey={api_key}'

            quote_json = await self._get_json("Alpha Vantage", "quote", quote_url)
            if not isinstance(quote_json, dict):
                return None

            if "Error Message" in quote_json:
                self.log.warning(f"Alpha Vantage error: {quote_json['Error Message']}")
                return None

            if "Information" in quote_json:
                info = quote_json["Information"]
                # Strip out API key if present
                api_key = self.config['alphavantageKey']
                if api_key in info:
                    info = info.replace(api_key, "[API KEY]")
                self.log.warning(f"Alpha Vantage info: {info}")
                return None

            if 'Global Quote' not in quote_json:
                return None

            quote = quote_json['Global Quote']
            return {
                'current_price': float(quote['05. price']),
                'open_price': float(quote['02. open']),
                'previous_close': float(quote['08. previous close']),
                'change': float(quote['09. change']),
                'change_percent': f"{float(quote['10. change percent'].rstrip('%')):.2f}%",
                'company_name': ticker,
                'day_high': float(quote['03. high']),
                'day_low': float(quote['04. low']),
                'high_52w': 0,
                'low_52w': 0
            }
        except Exception as e:
            self.log.exception(f"Alpha Vantage exception: {e}")
            return None

    async def _fetch_fmp_data(self, ticker: str) -> Optional[dict]:
        """Fetch stock data from Financial Modeling Prep API."""
        try:
            api_key = self.config["fmpKey"]
            fmp_endpoint = "profile" if self.config.get("fmpFreeTier", True) else "quote"
            quote_url = f'https://financialmodelingprep.com/stable/{fmp_endpoint}?symbol={ticker}&apikey={api_key}'

            quote_data = await self._get_json("FMP", fmp_endpoint, quote_url)
            if not quote_data or not isinstance(quote_data, list) or len(quote_data) == 0:
                self.log.warning("FMP quote data empty or invalid")
                return None
            use_profile = fmp_endpoint == "profile"

            quote = quote_data[0]

            # Check for error messages
            if isinstance(quote, dict) and 'Error' in quote:
                self.log.warning(f"FMP error in quote response: {quote.get('Error')}")
                return None

            # Extract quote data
            current_price = float(quote.get('price', 0))
            if current_price == 0:
                self.log.warning("FMP returned zero price")
                return None

            change = float(quote.get('change', 0)) if use_profile else 0
            previous_close = current_price - change if use_profile else float(quote.get('previousClose', current_price))
            if not use_profile:
                change = current_price - previous_close
            change_percent_value = quote.get('changePercentage')
            if change_percent_value is None:
                change_percent = f"{(change / previous_close * 100):.2f}%" if previous_close > 0 else "0.00%"
            else:
                change_percent = f"{float(change_percent_value):.2f}%"

            high_52w = 0
            low_52w = 0
            if quote.get('range'):
                try:
                    range_parts = str(quote['range']).split('-')
                    if len(range_parts) == 2:
                        low_52w = float(range_parts[0])
                        high_52w = float(range_parts[1])
                except (ValueError, IndexError):
                    pass

            return {
                'current_price': current_price,
                'open_price': 0 if use_profile else float(quote.get('open', current_price)),
                'previous_close': previous_close,
                'change': change,
                'change_percent': change_percent,
                'company_name': quote.get('companyName') or quote.get('name') or ticker,
                'day_high': 0 if use_profile else float(quote.get('dayHigh') or 0),
                'day_low': 0 if use_profile else float(quote.get('dayLow') or 0),
                'high_52w': high_52w if use_profile else float(quote.get('yearHigh') or 0),
                'low_52w': low_52w if use_profile else float(quote.get('yearLow') or 0)
            }
        except Exception as e:
            self.log.exception(f"FMP exception: {e}")
            return None

    def _format_stock_response(self, data: dict, ticker: str) -> str:
        """Format stock data into a pretty message."""
        change = data['change']
        if change < 0:
            color = "red"
            arrow = "\U000025BC"
        else:
            color = "green"
            arrow = "\U000025B2"

        lines = [
            f"<b>Current data for <a href=\"https://finance.yahoo.com/quote/{ticker}\">{data['company_name']}</a> ({ticker}):</b>",
            f"<b>Price:</b> <font color=\"{color}\">${data['current_price']:.2f}, {arrow}{data['change_percent']}</font> from previous close @ ${data['previous_close']:.2f}",
        ]
        if data['open_price'] > 0 and data['day_low'] > 0 and data['day_high'] > 0:
            lines.append(
                f"<b>Open:</b> ${data['open_price']:.2f} | "
                f"<b>Day:</b> ${data['day_low']:.2f}-${data['day_high']:.2f}"
            )
        if data['low_52w'] > 0 and data['high_52w'] > 0:
            lines.append(f"<b>52W:</b> ${data['low_52w']:.2f}-${data['high_52w']:.2f}")
        return "<br />".join(lines)

    @command.new(name=lambda self: self.config["stocktrigger"],
            help="Look up information about a stock by its ticker symbol")
    @command.argument("ticker", pass_raw=True, required=True)
    async def stock_handler(self, evt: MessageEvent, ticker: str) -> None:
        await evt.mark_read()

        if ticker.lower() == "help":
            await evt.mark_read()
            await evt.respond("Look up information about a stock using its ticker symbol, for example: <br />\
                            <code>!" + self.config["stocktrigger"] + " tsla</code>", allow_html=True)
            return None

        tickerUpper = ticker.upper()
        
        # Get available backends
        backends = self._get_available_backends()
        if not backends:
            await evt.respond("No API backends configured. Please configure at least one API key (rapidapiKey, alphavantageKey or fmpKey) in the bot configuration.")
            return None

        # Try each backend sequentially until one succeeds
        stock_data = None
        for backend in backends:
            self.log.debug(f"Trying backend: {backend}")
            if backend == "rapidapi":
                stock_data = await self._fetch_rapidapi_data(tickerUpper)
            elif backend == "alphavantage":
                stock_data = await self._fetch_alphavantage_data(tickerUpper)
            elif backend == "fmp":
                stock_data = await self._fetch_fmp_data(tickerUpper)
            
            if stock_data:
                self.log.debug(f"Successfully fetched data from {backend}")
                break
            else:
                self.log.debug(f"Backend {backend} failed, trying next...")

        if not stock_data:
            await evt.respond("No results, double check that you've chosen a real ticker symbol")
            return None

        # Format and send response
        prettyMessage = self._format_stock_response(stock_data, tickerUpper)
        await evt.respond(prettyMessage, allow_html=True)

    @command.new(name="hodl", help="Look up cryptocurrency price and changes.")
    @command.argument("symbol", pass_raw=True, required=True)
    async def crypto_handler(self, evt: MessageEvent, symbol: str) -> None:
        """Handle crypto price requests."""
        args = symbol.split()
        if not args:
            await evt.respond("Please provide a cryptocurrency symbol (e.g., !hodl BTC)")
            return

        symbol = args[0].upper()
        market = args[1].upper() if len(args) > 1 else "USD"

        try:
            # Get daily data for multiple timeframe analysis
            url = f"https://www.alphavantage.co/query?function=DIGITAL_CURRENCY_DAILY&symbol={symbol}&market={market}&apikey={self.config['alphavantageKey']}"
            async with self.http.get(url) as response:
                if response.status != 200:
                    await evt.respond(f"Error fetching data: HTTP {response.status}")
                    return
                
                data = await response.json()
                self.log.debug(data)
                
                if "Error Message" in data:
                    await evt.respond(f"Error: {data['Error Message']}")
                    return
                
                if "Information" in data:
                    info = data["Information"]
                    # Strip out API key if present
                    api_key = self.config['alphavantageKey']
                    if api_key in info:
                        info = info.replace(api_key, "[API KEY]")
                    await evt.respond(info)
                    return

                if not data or "Meta Data" not in data:
                    await evt.respond(f"No data found for {symbol}/{market}")
                    return

                time_series = data.get("Time Series (Digital Currency Daily)", {})
                if not time_series:
                    await evt.respond(f"No data found for {symbol}/{market}")
                    return

                # Get today's data
                today = list(time_series.items())[0]
                today_date = today[0]
                today_data = today[1]
                
                # Get historical data for different timeframes
                dates = list(time_series.keys())
                if len(dates) < 180:  # Need at least 180 days for 6-month analysis
                    await evt.respond(f"Insufficient historical data for {symbol}/{market}")
                    return

                # Calculate changes for different timeframes
                current_price = float(today_data["4. close"])
                open_price = float(today_data["1. open"])
                day_30_ago_price = float(time_series[dates[30]]["4. close"])
                month_6_ago_price = float(time_series[dates[180]]["4. close"])

                # Calculate price changes and percentages
                day_change = current_price - open_price
                day_change_pct = (day_change / open_price) * 100
                
                month_change = current_price - day_30_ago_price
                month_change_pct = (month_change / day_30_ago_price) * 100
                
                year_half_change = current_price - month_6_ago_price
                year_half_change_pct = (year_half_change / month_6_ago_price) * 100

                # Format the changes with appropriate colors and arrows
                def format_change(change, pct):
                    if change > 0:
                        return f"<font color='green'>+{change:.2f} ({pct:+.2f}%) ↑</font>"
                    elif change < 0:
                        return f"<font color='red'>{change:.2f} ({pct:+.2f}%) ↓</font>"
                    return f"{change:.2f} ({pct:+.2f}%)"

                day_change_str = format_change(day_change, day_change_pct)
                month_change_str = format_change(month_change, month_change_pct)
                year_half_change_str = format_change(year_half_change, year_half_change_pct)

                # Format volume
                volume = float(today_data["5. volume"])
                if volume >= 1_000_000:
                    volume_str = f"{volume/1_000_000:.2f}M"
                elif volume >= 1_000:
                    volume_str = f"{volume/1_000:.2f}K"
                else:
                    volume_str = f"{volume:.2f}"

                # Create the response message
                response = "<br />".join([
                    f"<b>{symbol}/{market}</b> - {today_date}",
                    f"",
                    f"Current: {current_price:.2f} {market}",
                    f"24h Change: {day_change_str}",
                    f"24h Volume: {volume_str} {symbol}",
                    f"24h High: {float(today_data['2. high']):.2f} {market}",
                    f"24h Low: {float(today_data['3. low']):.2f} {market}",
                    f"30d Change: {month_change_str}",
                    f"6m Change: {year_half_change_str}"
                ])

                await evt.respond(response, allow_html=True)

        except Exception as e:
            await evt.respond(f"Error fetching {symbol} data: {str(e)}")
