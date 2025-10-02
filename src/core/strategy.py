from src.constants import logging

from src.sdk.symbol import OptionSymbol, OptionData
from src.sdk.helper import Helper

from traceback import print_exc
from typing import Any, Literal
from importlib import import_module
from toolkit.kokoo import is_time_past, kill_tmux

"""
def unsubscribe_tokens_not_in_strategies(strategies: list[Any]):
    try:
        subscribed_tokens = [
            f"{strategy.trade.exchange}|{strategy._token}" for strategy in strategies
        ]
        quotes = Helper._quote.get_quotes()
        tokens_to_unsubscribe = [
            token for token in quotes.keys() if token not in subscribed_tokens
        ]
        print(tokens_to_unsubscribe)
        Helper._quote._ws.unsubscribe(tokens_to_unsubscribe)
    except Exception as e:
        logging.error(f"{e} while unsubscribing tokens not in strategies")
        print_exc()

"""


class StrategyMaker:

    def __init__(
        self,
        tokens_for_all_trading_symbols,
        symbols_to_trade,
    ) -> None:
        self.tokens_for_all_trading_symbols = tokens_for_all_trading_symbols
        self.symbols_to_trade = symbols_to_trade

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
            atm = user_settings["atm"]
            sym = OptionSymbol(data)

            result = sym.find_option_by_distance(
                atm=atm,
                distance=user_settings["moneyness"],
                c_or_p=ce_or_pe,
            )
            logging.info(f"find option by distance returned {result}")
            symbol_info_by_distance: dict[str, Any] = Helper._quote.symbol_info(
                user_settings["option_exchange"],
                result["TradingSymbol"],
                result["Token"],
            )
            logging.info(f"{symbol_info_by_distance=}")
            symbol_info_by_distance["option_type"] = ce_or_pe
            _ = Helper._quote.symbol_info(
                user_settings["exchange"],
                user_settings["index"],
                user_settings["token"],
            )

            # find the tradingsymbol which is closest to the premium
            if user_settings.get("premium", 0) > 0:
                logging.info("premiums is going to checked")

                # subscribe to symbols
                for key, symbol in self.tokens_for_all_trading_symbols.items():
                    token = key.split("|")[1]
                    _ = Helper._quote.symbol_info(
                        user_settings["option_exchange"], symbol, token
                    )

                quotes = Helper._quote.get_quotes()
                logging.info(
                    f"premium {user_settings['premium']} to be check agains quotes for closeness ]"
                )
                symbol_with_closest_premium = sym.find_closest_premium(
                    quotes=quotes, premium=user_settings["premium"], contains=ce_or_pe
                )

                logging.info(f"found {symbol_with_closest_premium=}")
                symbol_info_by_premium = Helper._quote.symbol_info(
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

    def create(self, strategy_name) -> list:
        """
        Creates a list of strategies based on the provided symbols_to_trade.
        """
        try:
            module_path = f"src.strategies.{strategy_name}"
            strategy_module = import_module(module_path)
            Strategy = getattr(strategy_module, strategy_name.capitalize())
            logging.info(f"creating strategy: {strategy_name}")
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
                        "rest": Helper._rest,
                    }
                    logging.info(f"common init: {common_init_kwargs}")
                    # create strategy object
                    logging.info(f"building {strategy_name} for {option_type}")
                    if strategy_name == "pivotindex":
                        if all(k in user_settings for k in ["intl", "inth", "intc"]):
                            logging.info(f"HLC: found in {user_settings} from settings")
                            common_init_kwargs["pivot_grids"] = (
                                import_module("src.providers.grid")
                                .Grid()
                                .set(
                                    prefix=prefix,
                                    symbol_constant=user_settings,
                                )
                            )
                        else:
                            common_init_kwargs["pivot_grids"] = (
                                import_module("src.providers.grid")
                                .Grid()
                                .get(
                                    rst=Helper._rest,
                                    exchange=user_settings["exchange"],
                                    tradingsymbol=user_settings["index"],
                                    token=user_settings["token"],
                                )
                            )
                    elif strategy_name == "pivot":
                        common_init_kwargs["pivot_grids"] = (
                            import_module("src.providers.grid")
                            .Grid()
                            .get(
                                rst=Helper._rest,
                                exchange=user_settings["option_exchange"],
                                tradingsymbol=common_init_kwargs["symbol_info"][
                                    "symbol"
                                ],
                                token=common_init_kwargs["symbol_info"]["token"],
                            )
                        )
                    print(common_init_kwargs)
                    strgy = Strategy(**common_init_kwargs)
                    strategies.append(strgy)

            # unsubscribe_tokens_not_in_strategies(strategies=strategies)
            return strategies
        except Exception as e:
            logging.error(f"{e} while creating the strategies in StrategyBuilder")
            print_exc()
            __import__("sys").exit(1)


class Engine:

    def __init__(self, strategies, trade_stop):
        self.strategies = strategies
        self.stop = trade_stop

    def run(self, strategy_name):
        try:
            strgy_to_be_removed = []
            while self.strategies and not is_time_past(self.stop):
                for strgy in self.strategies:
                    # Get the run arguments dynamically from the builder
                    trades = Helper._rest.trades()
                    quotes = Helper._quote.get_quotes()
                    run_args = trades, quotes
                    # Add strategy-specific run arguments that depend on loop state
                    if strategy_name == "openingbalance":
                        resp = strgy.run(
                            *run_args,
                            strgy_to_be_removed,
                        )
                        if resp == strgy._prefix:
                            strgy_to_be_removed.append(resp)
                    else:
                        resp = strgy.run(
                            *run_args
                        )  # Pass the dynamically generated args

                    # logging.info(f"main: {strgy._fn}")

                self.strategies = [
                    strgy for strgy in self.strategies if not strgy._removable
                ]
            else:
                logging.info(
                    f"main: exit initialized because we are past trade stop time {self.stop}"
                )
                orders = Helper._rest.orders()
                for item in orders:
                    if (item["status"] == "OPEN") or (
                        item["status"] == "TRIGGER_PENDING"
                    ):
                        order_id = item.get("order_id", None)
                        logging.info(f"cancelling open order {order_id}")
                        Helper._rest.order_cancel(order_id)

                Helper._rest.close_positions()

            logging.info(
                f"main: killing tmux because we started after stop time {self.stop}"
            )
            kill_tmux()
        except KeyboardInterrupt:
            __import__("sys").exit()
        except Exception as e:
            print_exc()
            logging.error(f"{e} Engine: run while init")
