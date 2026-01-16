from src.constants import logging_func
from src.sdk.symbol import OptionSymbol, OptionData
from src.sdk.helper import Helper

from traceback import print_exc
from typing import Any
from toolkit.kokoo import is_time_past


logging = logging_func(__name__)


class Builder:

    def __init__(self, trade_settings: dict, user_settings: dict, symbol_factory: dict):
        self.strategy = trade_settings["strategy"]
        self.start = trade_settings["start"]
        self.stop = trade_settings["stop"]

        resp = merge_settings_and_symbols(
            user_settings=user_settings, symbol_factory=symbol_factory
        )
        self.symbols_to_trade = find_expiry(symbols_to_trade=resp)

        self.is_built = False

    def can_build(self):
        if not self.is_built and is_time_past(self.start):
            return True
        return False

    def find_fno_tokens(self):
        """
        get instrument tokens from broker for each symbol to trade and merge them together
        (Refactored from your original find_instrument_tokens_to_trade)
        """
        try:
            self.is_built = True
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
                ltp_for_underlying = Helper._rest.ltp(exchange, token)
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


def merge_settings_and_symbols(user_settings, symbol_factory) -> dict[str, Any]:
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
                underlying_future = Helper._quote.symbol_info(
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
