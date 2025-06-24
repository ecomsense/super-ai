from src.constants import logging, O_SETG
from src.helper import Helper
from src.trade_manager import TradeManager
from src.symbols import Symbols, dct_sym
from traceback import print_exc
from typing import Any, Literal
from importlib import import_module


class Builder:
    def __init__(self, user_settings: dict[str, Any]):
        self.user_settings = user_settings
        self.strategy_name = user_settings["trade"]["strategy"]
        self.symbols_to_trade = self.merge_settings_and_symbols()
        self.tokens_for_all_trading_symbols = self.find_fno_tokens()

    def merge_settings_and_symbols(self) -> dict[str, Any]:
        """
        Retrieves tokens for all trading symbols.
        """
        try:
            black_list = ["log", "trade"]
            symbols_to_trade = {
                k: settings for k, settings in O_SETG.items() if k not in black_list
            }
            for k, settings in symbols_to_trade.items():
                symbol_item = dct_sym[k]
                token = symbol_item.get("token", None)
                if not token:
                    symbol_item["index"] = k + settings["future_expiry"]
                    symbol_item["exchange"] = settings["option_exchange"]
                    underlying_future = Helper._quote.symbol_info(
                        symbol_item["exchange"], symbol_item["index"]
                    )
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
                sym = Symbols(
                    option_exchange=symbol_info["option_exchange"],
                    base=symbol_info["base"],
                    expiry=symbol_info["expiry"],
                )
                sym.get_exchange_token_map_finvasia()
                exchange = symbol_info["exchange"]
                token = symbol_info["token"]
                ltp_for_underlying = Helper._rest.ltp(exchange, token)
                atm = sym.get_atm(ltp_for_underlying)
                logging.info(f"atm {atm} for underlying {k} from {ltp_for_underlying}")
                tokens_of_all_trading_symbols.update(sym.get_tokens(atm))
                self.symbols_to_trade[k]["atm"] = atm
            return tokens_of_all_trading_symbols
        except Exception as e:
            logging.error(f"{e} while finding instrument to trade in StrategyBuilder")
            print_exc()
            return {}

    def _find_tradingsymbol_by_atm(
        self, ce_or_pe: Literal["C", "P"], user_settings
    ) -> dict[str, Any]:
        """
        (Refactored from your original find_tradingsymbol_by_low)
        output:
            {'symbol': 'NIFTY26JUN25C24750', 'key': 'NFO|62385', 'low': 297.7, 'ltp': 274.85}
        """
        try:
            sym = Symbols(
                option_exchange=user_settings["option_exchange"],
                base=user_settings["base"],
                expiry=user_settings["expiry"],
            )
            """
            exchange = dct_sym[keyword]["exchange"]
            token = dct_sym[keyword]["token"]
            low = history(
                Helper._api,
                user_settings["exchange"],
                user_settings["token"],
                loc=-2,
                key="intl",
            )
            atm = sym.get_atm(float(low))
            logging.info(f"atm {atm} from {low}")
            """
            atm = user_settings["atm"]
            result = sym.find_option_by_distance(
                atm=atm,
                distance=user_settings["moneyness"],
                c_or_p=ce_or_pe,
                dct_symbols=self.tokens_for_all_trading_symbols,
            )
            symbol_info: dict[str, Any] = Helper._quote.symbol_info(
                user_settings["option_exchange"], result["symbol"]
            )
            return symbol_info
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
            strategies = []
            for prefix, user_settings in self.symbols_to_trade.items():
                print("user setting", user_settings)
                lst_of_option_type = ["C", "P"]
                for option_type in lst_of_option_type:
                    # Prepare common arguments for strategy __init__
                    common_init_kwargs = {
                        "prefix": prefix,
                        "symbol_info": self._find_tradingsymbol_by_atm(
                            option_type, user_settings
                        ),
                        "user_settings": user_settings,
                    }
                    # Add strategy-specific arguments for __init__
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
                    else:
                        common_init_kwargs["pivot_grids"] = None  # Or handle as needed

                    strgy = Strategy(**common_init_kwargs)
                    strgy._trade_manager = TradeManager(Helper._api)
                    strategies.append(strgy)
            return strategies
        except Exception as e:
            logging.error(f"{e} while creating the strategies in StrategyBuilder")
            print_exc()
            return []

    def get_run_arguments(self, strategy_instance) -> tuple:
        """
        Dynamically determine and return arguments for strategy.run()
        based on the strategy name.
        """
        trades = Helper._rest.trades()
        quotes = Helper._quote.get_quotes()

        if self.strategy_name == "openingbalance":
            # For 'openingbalance', sequence_info and strgy_to_be_removed are managed in main loop
            # and passed directly.
            # This method can return base args, and main can add the specific ones.
            return (trades, quotes)
        elif self.strategy_name == "pivot":
            underlying_ltp = Helper._rest.ltp(
                dct_sym[strategy_instance._prefix]["exchange"],
                dct_sym[strategy_instance._prefix]["token"],
            )
            return (trades, quotes, underlying_ltp)
        # Add more elif blocks for other strategies as they are developed
        else:
            # Default arguments if no specific handling is defined
            return (trades, quotes)


if __name__ == "__main__":
    from src.constants import O_SETG
    from pprint import pprint

    Helper.api()
    bldr = Builder(O_SETG)
    sgys = bldr.create_strategies()
    for sgy in sgys:
        resp = bldr.get_run_arguments(sgy)
        pprint(resp)
