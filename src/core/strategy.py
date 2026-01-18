from src.constants import logging_func

from traceback import print_exc
from importlib import import_module
from pprint import pprint

logging = logging_func(__name__)

"""
def unsubscribe_tokens_not_in_strategies(strategies: list[Any]):
    try:
        subscribed_tokens = [
            f"{strategy.trade.exchange}|{strategy._token}" for strategy in strategies
        ]
        quotes = quote.get_quotes()
        tokens_to_unsubscribe = [ ff
            token for token in quotes.keys() if token not in subscribed_tokens
        ]
        print(tokens_to_unsubscribe)
        quote._ws.unsubscribe(tokens_to_unsubscribe)
    except Exception as e:
        logging.error(f"{e} while unsubscribing tokens not in strategies")
        print_exc()

"""


def create(data, meta):
    """
    Creates a list of strategies based on the provided symbols_to_trade.
    """
    try:
        strategies = []
        strategy_name = meta["strategy"]
        module_path = f"src.strategies.{strategy_name}"
        strategy_module = import_module(module_path)
        Strategy = getattr(strategy_module, strategy_name.capitalize())
        logging.info(f"creating strategy: {strategy_name}")
        for prefix, settings in data.items():
            pprint(settings)
            lst_of_option_type = ["PE", "CE"]
            for option_type in lst_of_option_type:
                # create strategy object
                common_init_kwargs = {
                    "prefix": prefix,
                    "option_type": option_type,
                    "settings": settings,
                    "meta": meta,
                }
                strgy = Strategy(**common_init_kwargs)
                """
                strgy.name = strategy_name
                strgy.stop_time = stop_time
                """
                strategies.append(strgy)

        # unsubscribe_tokens_not_in_strategies(strategies=strategies)
        return strategies
    except Exception as e:
        logging.error(f"{e} while creating the strategies in StrategyBuilder")
        print_exc()
        __import__("sys").exit(1)
