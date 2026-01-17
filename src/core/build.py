from pandas.core.frame import concat_compat
from src.constants import logging_func
from src.sdk.symbol import OptionSymbol, OptionData

from traceback import print_exc
from typing import Any
from toolkit.kokoo import is_time_past

from typing import Any, Literal
from src.sdk.symbol import OptionSymbol, OptionData

logging = logging_func(__name__)


def merge_settings_and_symbols(user_settings, symbol_factory, quote) -> dict[str, Any]:
    """
    Retrieves tokens for all trading symbols.
    """
    try:
        blacklist = ["trade"]
        symbols_to_trade = {
            k: settings for k, settings in user_settings.items() if k not in blacklist
        }
        for k, settings in symbols_to_trade.items():
            # find a matching symbol based on the user settings trade key
            # example settings["NIFTY"]
            assert isinstance(symbol_factory, dict), "symbol_factory is not a dict"
            assert symbol_factory.get(k), f"symbol {k} not found in symbol_factory"

            symbol_item = symbol_factory[k]
            assert isinstance(symbol_item, dict), "symbol_item is not a dict"

            # avoid duplication of base key
            symbol_item["base"] = k

            # use base key as default for symbol
            symbol_item["symbol"] = settings.get("symbol", k)

            # if token not found in case of mcx future expiry
            token = symbol_item.get("token", None)

            if not token:
                symbol_item["index"] = k + settings["future_expiry"]
                symbol_item["exchange"] = settings["option_exchange"]
                underlying_future = quote.symbol_info(
                    symbol_item["exchange"], symbol_item["index"]
                )
                assert isinstance(
                    underlying_future, dict
                ), "underlying_future is not a dict"
                symbol_item["token"] = underlying_future["key"].split("|")[1]
            symbols_to_trade[k] = settings | symbol_item
        return symbols_to_trade
    except Exception as e:
        logging.error(f"{e} while getting symbols to trade in StrategyBuilder")
        return {}


def find_expiry(symbols_to_trade: dict):
    try:
        for k, symbol_info in symbols_to_trade.items():
            data = OptionData(
                exchange=symbol_info["option_exchange"],
                base=symbol_info["base"],
                symbol=symbol_info["symbol"],
                diff=symbol_info["diff"],
                depth=symbol_info["depth"],
                expiry=symbol_info.get("expiry", None),
            )
            sym = OptionSymbol(data)
            if not sym._data.expiry:
                expiry = sym._find_expiry()
                symbols_to_trade[k]["expiry"] = expiry

        return symbols_to_trade
    except Exception as e:
        logging.error(f"{e} while finding expiry")
        print_exc()


def merge(user_settings: dict, symbol_factory: dict, quote):
    resp = merge_settings_and_symbols(
        user_settings=user_settings, symbol_factory=symbol_factory, quote=quote
    )
    return find_expiry(symbols_to_trade=resp)


"""
 moved from strategy
"""


def find_tradingsymbol_by_atm(
    ce_or_pe: Literal["CE", "PE"], user_settings, tokens_for_all_trading_symbols, quote
) -> dict[str, Any]:
    """
    (Refactored from your original find_tradingsymbol_by_low)
    output:
        {'symbol': 'NIFTY26JUN25C24750', 'key': 'NFO|62385', 'token': 12345, 'ltp': 274.85}
    """
    try:
        data = OptionData(
            exchange=user_settings["option_exchange"],
            base=user_settings["base"],
            symbol=user_settings["symbol"],
            diff=user_settings["diff"],
            depth=user_settings["depth"],
            expiry=user_settings["expiry"],
        )
        atm = user_settings["atm"]

        logging.info(f"find option by distance with {data} for user settings atm:{atm}")
        sym = OptionSymbol(data)

        result = sym.find_option_by_distance(
            atm=atm,
            distance=user_settings["moneyness"],
            c_or_p=ce_or_pe,
        )
        logging.info(f"find option by distance returned {result}")
        symbol_info_by_distance: dict[str, Any] = quote.symbol_info(
            user_settings["option_exchange"],
            result["TradingSymbol"],
            result["Token"],
        )
        logging.info(f"{symbol_info_by_distance=}")
        symbol_info_by_distance["option_type"] = ce_or_pe
        _ = quote.symbol_info(
            user_settings["exchange"],
            user_settings["index"],
            user_settings["token"],
        )

        # find the tradingsymbol which is closest to the premium
        if user_settings.get("premium", 0) > 0:
            logging.info("premiums is going to checked")

            # subscribe to symbols
            for key, symbol in tokens_for_all_trading_symbols.items():
                token = key.split("|")[1]
                _ = quote.symbol_info(user_settings["option_exchange"], symbol, token)

            logging.info(
                f"premium {user_settings['premium']} to be check agains quotes for closeness ]"
            )
            symbol_with_closest_premium = sym.find_closest_premium(
                quotes=quote.get_quotes(),
                premium=user_settings["premium"],
                contains=ce_or_pe,
            )

            logging.info(f"found {symbol_with_closest_premium=}")
            symbol_info_by_premium = quote.symbol_info(
                user_settings["option_exchange"], symbol_with_closest_premium
            )
            logging.info(f"getting {symbol_info_by_premium=}")
            assert isinstance(
                symbol_info_by_premium, dict
            ), "symbol_info_by_premium is empty"
            symbol_info_by_premium["option_type"] = ce_or_pe

            # use any one result
            symbol_info = (
                symbol_info_by_premium
                if symbol_info_by_premium["ltp"] > symbol_info_by_distance["ltp"]
                else symbol_info_by_distance
            )
            return symbol_info
        return symbol_info_by_distance
    except Exception as e:
        logging.error(f"{e} while finding the trading symbol in StrategyBuilder")
        print_exc()
        return {}


class Builder:
    def __init__(self, trade_settings: dict):
        self.strategy = trade_settings["strategy"]
        self.start = trade_settings["start"]
        self.stop = trade_settings["stop"]

    def can_build(self):
        if is_time_past(self.start):
            return True
        return False

    def set_symbols_to_trade(self, symbols_to_trade: dict):
        self.symbols_to_trade = symbols_to_trade

    def find_fno_tokens(self, rest):
        """
        get instrument tokens from broker for each symbol to trade and merge them together
        """
        try:
            tokens_of_all_trading_symbols = {}
            for k, symbol_info in self.symbols_to_trade.items():
                data = OptionData(
                    exchange=symbol_info["option_exchange"],
                    base=symbol_info["base"],
                    symbol=symbol_info["symbol"],
                    diff=symbol_info["diff"],
                    depth=symbol_info["depth"],
                    expiry=symbol_info["expiry"],
                )
                sym = OptionSymbol(data)

                # get atm for the underlying
                exchange = symbol_info["exchange"]
                token = symbol_info["token"]

                ltp_for_underlying = rest.ltp(exchange, token)
                assert ltp_for_underlying is not None, "ltp_for_underlying is None"
                atm = sym.get_atm(ltp_for_underlying)

                # set atm for later use
                self.symbols_to_trade[k]["atm"] = atm
                self.symbols_to_trade[k]["underlying_ltp"] = ltp_for_underlying
                logging.info(f"atm {atm} for underlying {k} from {ltp_for_underlying}")

                # get tokens for the option
                tokens_of_all_trading_symbols.update(sym.get_tokens(atm))
            return tokens_of_all_trading_symbols
        except Exception as e:
            logging.error(f"{e} while finding instrument to trade in StrategyBuilder")
            print_exc()

    def create(self, strategy_name, stop_time, quote):
        """
        Creates a list of strategies based on the provided symbols_to_trade.
        """
        try:
            #TODO
            common_init_kwargs = {}
            for prefix, user_settings in self.symbols_to_trade.items():
                # Prepare common arguments for strategy __init__
                common_init_kwargs.update(
                    f"{strategy_name}": {
                        "stop_time": stop_time,
                        "prefix": prefix,
                        "user_settings": user_settings,
                    })
                lst_of_option_type = ["PE", "CE"]
                for option_type in lst_of_option_type:
                    common_init_kwargs[f"{strategy_name}"][option_type] = {
                        "symbol_info": find_expiry_tradingsymbol_by_atm(
                            ce_or_pe=option_type,
                            user_settings=user_settings,
                            tokens_for_all_trading_symbols=self.tokens_for_all_trading_symbols,
                            quote=quote,
                        )
                    }
            return common_init_kwargs
        except Exception as e:
            logging.error(f"{e} while creating the strategies in StrategyBuilder")
            print_exc()
            __import__("sys").exit(1)
