from src.constants import logging
from src.sdk.symbol import OptionSymbol, OptionData
from src.sdk.helper import Helper

from traceback import print_exc
from typing import Any


class Builder:
    def __init__(self, user_settings: dict[str, Any], dct_sym):
        self.user_settings = user_settings
        self.symbols_to_trade = self.merge_settings_and_symbols(dct_sym)
        self.tokens_for_all_trading_symbols = self.find_fno_tokens()

    def merge_settings_and_symbols(self, dct_sym) -> dict[str, Any]:
        """
        Retrieves tokens for all trading symbols.
        """
        try:
            blacklist = ["trade"]
            symbols_to_trade = {
                k: settings
                for k, settings in self.user_settings.items()
                if k not in blacklist
            }
            for k, settings in symbols_to_trade.items():
                # find a matching symbol based on the user settings trade key
                # example settings["NIFTY"]
                assert isinstance(dct_sym, dict), "dct_sym is not a dict"
                assert dct_sym.get(k), f"symbol {k} not found in dct_sym"

                symbol_item = dct_sym[k]
                assert isinstance(symbol_item, dict), "symbol_item is not a dict"

                # avoid duplication of base key
                symbol_item["base"] = k

                # use base key as default for symbol
                symbol_item["symbol"] = symbol_item.pop("symbol", k)

                # if token not found in case of mcx future expiry
                token = symbol_item.get("token", None)

                if not token and settings["exchange"] == "MCX":
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

    def find_fno_tokens(self) -> dict[str, Any]:
        """
        get instrument tokens from broker for each symbol to trade and merge them together
        (Refactored from your original find_instrument_tokens_to_trade)
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
                sym = OptionSymbol(OptionData=data)

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
            return {}
