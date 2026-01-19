from src.constants import logging_func

from traceback import print_exc
from toolkit.kokoo import is_time_past

from typing import Any, Literal
from src.sdk.symbol import OptionSymbol, OptionData
from copy import deepcopy

logging = logging_func(__name__)


class Builder:
    def __init__(self, trade_settings: dict, user_settings: dict, quote, rest):
        self._data = user_settings
        self._meta = trade_settings
        meta = {"quote": quote, "rest": rest}
        self._meta.update(meta)

    def merge_settings_and_symbols(self, symbol_factory):
        """
        Retrieves tokens for all trading symbols.
        """
        try:
            # explode k = NIFTY, v = {settings}
            for k, settings in self._data.items():
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

                # MCX only
                if not token:
                    symbol_item["index"] = k + settings["future_expiry"]
                    symbol_item["exchange"] = settings["option_exchange"]
                    underlying_future = self._meta["quote"].symbol_info(
                        symbol_item["exchange"], symbol_item["index"]
                    )
                    assert isinstance(
                        underlying_future, dict
                    ), "underlying_future is not a dict"
                    symbol_item["token"] = underlying_future["key"].split("|")[1]

                # overwrite symbol item on settings
                self._data[k] = settings | symbol_item
            return self
        except Exception as e:
            logging.error(f"{e} while merging symbol and settings")

    def find_expiry(self):
        try:
            for k, symbol_info in self._data.items():
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
                    self._data[k]["expiry"] = expiry

            return self
        except Exception as e:
            logging.error(f"{e} while finding expiry")
            print_exc()

    def can_build(self):
        if is_time_past(self._meta["start_time"]):
            return True
        return False


"""
    related to getting options symbols 
"""


def find_atm_fm_ltp(symbol_info, ltp_for_underlying):
    """
    get instrument tokens from broker for each symbol to trade and merge them together
    """
    try:
        data = OptionData(
            exchange=symbol_info["option_exchange"],
            base=symbol_info["base"],
            symbol=symbol_info["symbol"],
            diff=symbol_info["diff"],
            depth=symbol_info["depth"],
            expiry=symbol_info["expiry"],
        )
        sym = OptionSymbol(data)

        return sym.get_atm(ltp_for_underlying)
    except Exception as e:
        logging.error(f"{e} while finding ltp and atm in builder")
        print_exc()


def find_tokens_from_atm(symbol_info, atm):
    """
    get instrument tokens from broker for each symbol to trade and merge them together
    """
    try:
        data = OptionData(
            exchange=symbol_info["option_exchange"],
            base=symbol_info["base"],
            symbol=symbol_info["symbol"],
            diff=symbol_info["diff"],
            depth=symbol_info["depth"],
            expiry=symbol_info["expiry"],
        )
        sym = OptionSymbol(data)

        # get tokens for the option
        return sym.get_tokens(atm)
    except Exception as e:
        logging.error(f"{e} while finding fno tokens in builder")
        print_exc()


def find_tradingsymbols_by_moneyness(
    ce_or_pe: Literal["CE", "PE"], param, quote
) -> dict[str, Any]:
    """
    (Refactored from your original find_tradingsymbol_by_low)
    output:
        {'symbol': 'NIFTY26JUN25C24750', 'key': 'NFO|62385', 'token': 12345, 'ltp': 274.85}
    """
    try:
        data = OptionData(
            exchange=param["option_exchange"],
            base=param["base"],
            symbol=param["symbol"],
            diff=param["diff"],
            depth=param["depth"],
            expiry=param["expiry"],
        )
        atm = param["atm"]
        logging.info(f"find option by distance with {data} for user settings atm:{atm}")
        sym = OptionSymbol(data)

        # find option based on distance
        result = sym.find_option_by_distance(
            atm=atm,
            distance=param["moneyness"],
            c_or_p=ce_or_pe,
        )
        logging.info(f"find option by distance returned {result}")

        symbol_info_by_distance = quote.symbol_info(
            param["option_exchange"],
            result["TradingSymbol"],
            result["Token"],
        )
        symbol_info_by_distance["option_type"] = ce_or_pe
        logging.info(f"{symbol_info_by_distance=}")

        return symbol_info_by_distance
    except Exception as e:
        logging.error(f"{e} while finding the trading symbol")
        print_exc()
        return {}


def find_tradingsymbols_by_premium(
    ce_or_pe: Literal["CE", "PE"], param, quote
) -> dict[str, Any]:
    """
    (Refactored from your original find_tradingsymbol_by_low)
    output:
        {'symbol': 'NIFTY26JUN25C24750', 'key': 'NFO|62385', 'token': 12345, 'ltp': 274.85}
    """
    try:
        data = OptionData(
            exchange=param["option_exchange"],
            base=param["base"],
            symbol=param["symbol"],
            diff=param["diff"],
            depth=param["depth"],
            expiry=param["expiry"],
        )
        atm = param["atm"]
        logging.info(f"find option by distance with {data} for user settings atm:{atm}")
        sym = OptionSymbol(data)

        _ = quote.symbol_info(
            param["exchange"],
            param["index"],
            param["token"],
        )

        # find the tradingsymbol which is closest to the premium
        tokens_for_all_trading_symbols = param["fno_tokens"]

        # subscribe to symbols
        for key, symbol in tokens_for_all_trading_symbols.items():
            token = key.split("|")[1]
            _ = quote.symbol_info(param["option_exchange"], symbol, token)

        logging.info(
            f"premium {param['premium']} to be check against quotes for closeness ]"
        )
        symbol_with_closest_premium = sym.find_closest_premium(
            quotes=quote.get_quotes(),
            premium=param["premium"],
            contains=ce_or_pe,
        )
        logging.info(f"found {symbol_with_closest_premium=}")

        option_info = quote.symbol_info(
            param["option_exchange"],
            symbol_with_closest_premium,
        )
        return option_info

    except Exception as e:
        logging.error(f"{e} while finding the trading symbol")
        print_exc()
        return {}


def stuff_atm(data, meta):
    try:
        for user_settings in data.values():
            ltp_for_underlying = meta["rest"].ltp(
                user_settings["exchange"], user_settings["token"]
            )
            user_settings["atm"] = find_atm_fm_ltp(user_settings, ltp_for_underlying)
        return data
    except Exception as e:
        logging.error(f"{e} in find atm")
        print_exc()


def stuff_tradingsymbols(data, meta):
    try:
        lst = []

        for copied in data.values():
            moneyness_or_premium = copied.pop("method")
            copied.update(moneyness_or_premium)
            keys_of_user_settings = copied.keys()

            option_types = ("CE", "PE")
            for option_type in option_types:
                user_settings = deepcopy(copied)
                user_settings.update(**meta)
                user_settings["option_type"] = option_type

                if "moneyness" in keys_of_user_settings:
                    option_info = find_tradingsymbols_by_moneyness(
                        ce_or_pe=option_type, param=user_settings, quote=meta["quote"]
                    )

                elif "premium" in keys_of_user_settings:
                    user_settings["fno_tokens"] = find_tokens_from_atm(
                        user_settings, user_settings["atm"]
                    )
                    option_info = find_tradingsymbols_by_premium(
                        ce_or_pe=option_type, param=user_settings, quote=meta["quote"]
                    )

                user_settings["tradingsymbol"] = option_info["symbol"]
                user_settings["ltp"] = option_info["ltp"]
                user_settings["option_token"] = option_info["token"]
                lst.append(user_settings)

        return lst
    except Exception as e:
        logging.error(f"{e} find fno token")
        print_exc()


if __name__ == "__main__":
    try:
        from pprint import pprint
        from src.constants import (
            logging_func,
            TradeSet,
            get_symbol_fm_factory,
        )

        from src.sdk.helper import Helper

        Helper.api()
        quote = Helper._quote
        rest = Helper._rest
        while True:
            O_TRADESET = TradeSet().read()
            if not O_TRADESET or not any(O_TRADESET):
                break
            trade_settings = O_TRADESET.pop("trade")
            builder = (
                Builder(
                    trade_settings=trade_settings,
                    user_settings=O_TRADESET,
                    quote=quote,
                    rest=rest,
                )
                .merge_settings_and_symbols(symbol_factory=get_symbol_fm_factory())
                .find_expiry()
            )

            data = stuff_atm(builder._data, builder._meta)
            print("**************************************************")
            pprint(data)
            lst_of_params = stuff_tradingsymbols(data, builder._meta)
            pprint(lst_of_params)

    except Exception as e:
        print(e)
