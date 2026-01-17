from src.constants import logging_func

from traceback import print_exc
from importlib import import_module


logging = logging_func(__name__)

"""
def unsubscribe_tokens_not_in_strategies(strategies: list[Any]):
    try:
        subscribed_tokens = [
            f"{strategy.trade.exchange}|{strategy._token}" for strategy in strategies
        ]
        quotes = quote.get_quotes()
        tokens_to_unsubscribe = [
            token for token in quotes.keys() if token not in subscribed_tokens
        ]
        print(tokens_to_unsubscribe)
        quote._ws.unsubscribe(tokens_to_unsubscribe)
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

    def create(self, strategy_name, stop_time, quote, rest):
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
                        "symbol_info": find_tradingsymbol_by_atm(
                            ce_or_pe=option_type,
                            user_settings=user_settings,
                            tokens_for_all_trading_symbols=self.tokens_for_all_trading_symbols,
                            quote=quote,
                        ),
                        "user_settings": user_settings,
                        "rest": rest,
                    }
                    logging.info(f"common init: {common_init_kwargs}")
                    # create strategy object
                    logging.info(f"making {strategy_name} for {option_type}")
                    strgy = Strategy(**common_init_kwargs)
                    strgy.name = strategy_name
                    strgy.stop_time = stop_time
                    strategies.append(strgy)

            # unsubscribe_tokens_not_in_strategies(strategies=strategies)
            return strategies
        except Exception as e:
            logging.error(f"{e} while creating the strategies in StrategyBuilder")
            print_exc()
            __import__("sys").exit(1)
