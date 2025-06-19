from src.constants import logging, O_SETG
from src.helper import Helper, history
from src.trade_manager import TradeManager
from src.strategies.pivot import Grid
from src.symbols import Symbols, dct_sym
from toolkit.kokoo import is_time_past, timer
from traceback import print_exc
from typing import Any, Literal
from importlib import import_module


def get_symbols_to_trade() -> dict[str, Any]:
    """
    Retrieves tokens for all trading symbols.

    This function filters trading symbols based on a blacklist and retrieves tokens
    for each symbol using the `Symbols` class. It calculates the at-the-money (ATM)
    strike price based on the latest traded price (LTP) of the underlying asset and
    fetches the corresponding tokens.

    Returns:
        A dictionary where keys are trading symbols (str), and values contain
        symbol-specific configuration details from user settings.

    Raises:
        Exception: If an error occurs during token retrieval.
    """
    try:
        black_list = ["log", "trade", "target", "MCX"]
        symbols_to_trade = {
            k: user_settings
            for k, user_settings in O_SETG.items()
            if k not in black_list
        }
        # find instrument token for underlying if it is no thter in Smbols
        for k, user_settings in symbols_to_trade.items():
            token = dct_sym[k].get("token", None)
            if not token:
                symbol = k + user_settings["future_expiry"]
                exchange = user_settings["option_exchange"]
                underlying_future = Helper._quote.symbol_info(exchange, symbol)
                dct_sym[k]["token"] = underlying_future["key"].split("|")[1]
        return symbols_to_trade
    except Exception as e:
        logging.error(f"{e} while get symbols to trade")
        return {}


def find_instrument_tokens_to_trade(symbols_to_trade) -> dict[str, Any]:
    """
    get instrument tokens from broker for each symbol to trade and merge them together
    """
    try:
        tokens_of_all_trading_symbols = {}
        for k, user_settings in symbols_to_trade.items():
            sym = Symbols(
                option_exchange=user_settings["option_exchange"],
                base=user_settings["base"],
                expiry=user_settings["expiry"],
            )
            sym.get_exchange_token_map_finvasia()
            # find ltp for underlying
            exchange = dct_sym[k]["exchange"]
            token = dct_sym[k]["token"]
            ltp_for_underlying = Helper._rest.ltp(exchange, token)
            # find from ltp
            atm = sym.get_atm(ltp_for_underlying)
            # find tokens from ltp
            logging.info(f"atm {atm} for underlying {k} from {ltp_for_underlying}")
            tokens_of_all_trading_symbols.update(sym.get_tokens(atm))
        return tokens_of_all_trading_symbols
    except Exception as e:
        logging.error(f"{e} while find instrument to trade")
        print_exc()
        return {}


def not_used_for_this_project(
    ce_or_pe: Literal["C", "P"], symbol_item: dict[str, Any]
) -> dict[str, Any]:
    """
    find trading symbol to trade based on the atm giuser_settingsen the
    symbol item

    Args:
        ce_or_pe (Literal["C", "P"]): A string that denotes Call or Put
        symbol_item (dict[str, Any]): symbol item selected to find trading symbol

    Returns:
        symbol_info: trading symbol

    Raises:
        Exception: If there is any error

    """
    try:
        for keyword, user_settings in symbol_item.items():
            sym = Symbols(
                option_exchange=user_settings["option_exchange"],
                base=user_settings["base"],
                expiry=user_settings["expiry"],
            )
            exchange = dct_sym[keyword]["exchange"]
            # TODO will be missing in futures
            token = dct_sym[keyword]["token"]
            i, ltp_for_underlying = 1, None
            while not ltp_for_underlying:
                logging.debug(f"try #{i} to find ltp for {user_settings['base']}")
                ltp_for_underlying = Helper._rest.ltp(exchange, token)
                logging.debug(f"found None and sleeping for {i} second(s)")
                timer(i)
                i += 1
            # find from ltp
            atm = sym.get_atm(ltp_for_underlying)
            logging.info(
                f"atm {atm} for underlying {keyword} from {ltp_for_underlying=}"
            )
            result = sym.find_option_by_distance(
                atm=atm,
                distance=user_settings["moneyness"],
                c_or_p=ce_or_pe,
                dct_symbols=Helper.tokens_for_all_trading_symbols,
            )
            symbol_info: dict[str, Any] = Helper._quote.symbol_info(
                user_settings["option_exchange"], result["symbol"]
            )
            return symbol_info
    except Exception as e:
        logging.error(f"{e} while finding the trading symbol")
        print_exc()
        return {}


def find_tradingsymbol_by_low(
    ce_or_pe: Literal["C", "P"], symbol_item: dict[str, Any]
) -> dict[str, Any]:
    """
    note used
    find trading symbol to trade based on the atm giuser_settingsen the
    symbol item

    Args:
        ce_or_pe (Literal["C", "P"]): A string that denotes Call or Put
        symbol_item (dict[str, Any]): symbol item selected to find trading symbol

    Returns:
        symbol_info: trading symbol

    Raises:
        Exception: If there is any error

    """
    try:
        for keyword, user_settings in symbol_item.items():
            sym = Symbols(
                option_exchange=user_settings["option_exchange"],
                base=user_settings["base"],
                expiry=user_settings["expiry"],
            )
            exchange = dct_sym[keyword]["exchange"]
            # TODO will be missing in futures
            token = dct_sym[keyword]["token"]
            low = history(Helper._api, exchange, token, loc=-2, key="intl")
            atm = sym.get_atm(float(low))
            logging.info(f"atm {atm} for underlying {keyword} from {low}")
            result = sym.find_option_by_distance(
                atm=atm,
                distance=user_settings["moneyness"],
                c_or_p=ce_or_pe,
                dct_symbols=Helper.tokens_for_all_trading_symbols,
            )
            symbol_info: dict[str, Any] = Helper._quote.symbol_info(
                user_settings["option_exchange"], result["symbol"]
            )
            return symbol_info
        return {}
    except Exception as e:
        logging.error(f"{e} while finding the trading symbol")
        print_exc()
        return {}


def create_strategies(symbols_to_trade: dict[str, Any], strategy_name) -> list:
    """
    Creates a list of strategies based on the provided symbols_to_trade.

    Args:
        symbols_to_trade (dict[str, Any]): A dictionary containing all symbols information to trade

    Returns:
        strategies: A list of Enterandexit objects

    Raises:
        Exception: If there is any error
    """
    try:
        module_path = f"src.strategies.{strategy_name}"
        strategy_module = import_module(module_path)
        Strategy = getattr(strategy_module, strategy_name.capitalize())
        strategies = []
        for prefix, user_settings in symbols_to_trade.items():
            lst_of_option_type = ["C", "P"]
            for option_type in lst_of_option_type:
                strgy = Strategy(
                    prefix=prefix,
                    symbol_info=find_tradingsymbol_by_low(
                        option_type, {prefix: user_settings}
                    ),
                    user_settings=user_settings,
                    pivot_grids=(
                        Grid().run(
                            api=Helper.api(), prefix=prefix, symbol_constant=dct_sym
                        )
                        if strategy_name == "pivot"
                        else None
                    ),
                )
                strgy._trade_manager = TradeManager(Helper._api)
                strategies.append(strgy)
        return strategies
    except Exception as e:
        logging.error(f"{e} while creating the strategies")
        print_exc()
        return []


def main():
    try:
        # login to broker api
        Helper.api()

        # get user selected symbols to trade
        symbols_to_trade = get_symbols_to_trade()

        while not is_time_past(O_SETG["trade"]["start"]):
            print(f"waiting till {O_SETG['trade']['start']}")

        # get all the tokens we will be trading
        Helper.tokens_for_all_trading_symbols = find_instrument_tokens_to_trade(
            symbols_to_trade
        )
        # make strategy oject for each symbol selected
        strategy_name = O_SETG["trade"]["strategy"]
        strategies: list = create_strategies(symbols_to_trade, strategy_name)

        strgy_to_be_removed = []
        sequence_info = {}
        while not is_time_past(O_SETG["trade"]["stop"]):
            for strgy in strategies:
                msg = f"{strgy.trade.symbol} ltp:{strgy.trade.last_price} {strgy._fn}"
                prefix = strgy._prefix
                if strategy_name == "openingbalance":
                    sequence_info[strgy._id] = dict(
                        _prefix=prefix,
                        _reduced_target_sequence=strgy._reduced_target_sequence,
                    )
                    resp = strgy.run(
                        Helper._rest.trades(),
                        Helper._quote.get_quotes(),
                        strgy_to_be_removed,
                        sequence_info,
                    )
                    if isinstance(resp, str):
                        strgy_to_be_removed.append(resp)
                elif strategy_name == "pivot":
                    resp = strgy.run(
                        Helper._rest.trades(),
                        Helper._quote.get_quotes(),
                        underlying_ltp=Helper._rest.ltp(
                            dct_sym[prefix]["exchange"], dct_sym[prefix]["token"]
                        ),
                    )
                logging.info(f"{msg} returned {resp}")
            strategies = [strgy for strgy in strategies if not strgy._removable]
    except KeyboardInterrupt:
        __import__("sys").exit()
    except Exception as e:
        print_exc()
        logging.error(f"{e} while init")


if __name__ == "__main__":
    main()
