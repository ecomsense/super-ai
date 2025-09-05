from src.constants import logging, get_symbol_fm_factory
from src.symbol import OptionSymbol, OptionData
from traceback import print_exc
from typing import Any, Literal
from importlib import import_module
from toolkit.kokoo import is_time_past, timer
from src.helper import Helper, history

def unsubscribe_tokens_not_in_strategies(strategies: list[Any]):
    try:
        subscribed_tokens = [f"{strategy.trade.exchange}|{strategy._token}" for strategy in strategies]
        quotes = Helper._quote.get_quotes()
        tokens_to_unsubscribe = [token for token in quotes.keys() if token not in subscribed_tokens]
        print(tokens_to_unsubscribe)
        Helper._quote._ws.unsubscribe(tokens_to_unsubscribe)
    except Exception as e:
        logging.error(f"{e} while unsubscribing tokens not in strategies")
        print_exc()

class Builder:
    def __init__(self, user_settings: dict[str, Any], strategy_name: str):
        self.user_settings = user_settings
        self.strategy_name = strategy_name
        self.symbols_to_trade = self.merge_settings_and_symbols()
        self.tokens_for_all_trading_symbols = self.find_fno_tokens()

    def merge_settings_and_symbols(self) -> dict[str, Any]:
        """
        Retrieves tokens for all trading symbols.
        """
        try:
            dct_sym = get_symbol_fm_factory()
            blacklist = ["trade"]
            symbols_to_trade = {
                k: settings for k, settings in self.user_settings.items() if k not in blacklist
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
                    assert isinstance(underlying_future, dict), "underlying_future is not a dict"
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

    def _find_tradingsymbol_by_atm(
        self, ce_or_pe: Literal["CE", "PE"], user_settings
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
            sym = OptionSymbol(data)

            atm = user_settings["atm"]
            result = sym.find_option_by_distance(
                atm=atm,
                distance=user_settings["moneyness"],
                c_or_p=ce_or_pe,
            )
            logging.info(f"find option by distance returned {result}")
            symbol_info_by_distance: dict[str, Any] = Helper._quote.symbol_info(
                user_settings["option_exchange"], result["TradingSymbol"], result["Token"]
            )
            logging.info(f"{symbol_info_by_distance=}")
            symbol_info_by_distance["option_type"] = ce_or_pe
            _ = Helper._quote.symbol_info(
                user_settings["exchange"], user_settings["index"], user_settings["token"]
            )

            # find the tradingsymbol which is closest to the premium
            if user_settings.get("premium", 0) > 0:
                logging.info("premiums is going to checked")

                # subscribe to symbols
                for key, symbol in self.tokens_for_all_trading_symbols.items():
                    token = key.split("|")[1]
                    _ = Helper._quote.symbol_info(user_settings["option_exchange"], symbol, token)

                quotes = Helper._quote.get_quotes()
                logging.info(f"premium {user_settings['premium']} to be check agains quotes for closeness ]")
                symbol_with_closest_premium = sym.find_closest_premium(quotes=quotes, premium=user_settings["premium"], contains=ce_or_pe)

                logging.info(f"found {symbol_with_closest_premium=}")
                symbol_info_by_premium = Helper._quote.symbol_info(user_settings["option_exchange"], symbol_with_closest_premium)
                logging.info(f"getting {symbol_info_by_premium=}")
                assert isinstance(symbol_info_by_premium, dict), "symbol_info_by_premium is empty"
                symbol_info_by_premium["option_type"] = ce_or_pe

                # use any one result
                symbol_info = symbol_info_by_premium if symbol_info_by_premium["ltp"] > symbol_info_by_distance["ltp"] else symbol_info_by_distance
                return symbol_info
            return symbol_info_by_distance
        except Exception as e:
            logging.error(f"{e} while finding the trading symbol in StrategyBuilder")
            print_exc()
            return {}

    def create_strategies(self) -> list:
        """
        Creates a list of strategies based on the provided symbols_to_trade.
        """
        try:
            module_path = f"src.strategies.{self.strategy_name}"
            strategy_module = import_module(module_path)
            Strategy = getattr(strategy_module, self.strategy_name.capitalize())
            logging.info(f"creating strategy: {self.strategy_name}")
            strategies = []
            for prefix, user_settings in self.symbols_to_trade.items():
                lst_of_option_type = ["PE", "CE"]
                for option_type in lst_of_option_type:
                    # Prepare common arguments for strategy __init__
                    common_init_kwargs = {
                        "prefix": prefix,
                        "symbol_info": self._find_tradingsymbol_by_atm(
                            option_type, user_settings
                        ),
                        "user_settings": user_settings,
                    }
                    logging.info(f"common init: {common_init_kwargs}")
                    # create strategy object
                    logging.info(f"building {self.strategy_name} for {option_type}")
                    if self.strategy_name == "pivot":
                        common_init_kwargs["pivot_grids"] = (
                            import_module("src.strategies.pivot")
                            .Grid()
                            .run(
                                api=Helper.api(),
                                prefix=prefix,
                                symbol_constant=user_settings,
                            )
                        )
                    print(common_init_kwargs)
                    strgy = Strategy(**common_init_kwargs)
                    strategies.append(strgy)
            
            #unsubscribe_tokens_not_in_strategies(strategies=strategies)
            return strategies
        except Exception as e:
            logging.error(f"{e} while creating the strategies in StrategyBuilder")
            print_exc()
            __import__("sys").exit(1)

    def get_run_arguments(self, strategy_instance) -> tuple:
        """
        Dynamically determine and return arguments for strategy.run()
        based on the strategy name.
        """
        trades = Helper._rest.trades()
        quotes = Helper._quote.get_quotes()
        return (trades, quotes)

if __name__ == "__main__":
    from src.constants import O_TRADESET
    from pprint import pprint

    Helper.api()
    bldr = Builder(user_settings=O_TRADESET, strategy_name="openingbalance")
    sgys = bldr.create_strategies()
    for sgy in sgys:
        resp = bldr.get_run_arguments(sgy)
        pprint(resp)
