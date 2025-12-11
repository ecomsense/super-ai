from src.constants import S_DATA
import random
import string
from functools import wraps
from traceback import print_exc
import pendulum as plum
from toolkit.fileutils import Fileutils


def dict_from_yml(key_to_search, value_to_match):
    try:
        dct = {}
        sym_from_yml = Fileutils().get_lst_fm_yml(S_DATA + "symbols.yml")
        for _, dct in sym_from_yml.items():
            if isinstance(dct, dict) and dct[key_to_search] == value_to_match:
                return dct
        print(f"{dct=}")
        return dct
    except Exception as e:
        print(f"dict from yml error: {e}")
        print_exc()


def retry_until_not_none(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = None
        while result is None:
            result = func(*args, **kwargs)
            if result is None:
                print("WAITING FOR LTP")
        return result

    return wrapper


def generate_unique_id():
    # Get the current timestamp
    timestamp = plum.now().format("YYYYMMDDHHmmssSSS")

    # Generate a random string of 6 characters
    random_str = "".join(random.choices(string.ascii_letters + string.digits, k=6))

    # Combine the timestamp with the random string to form the unique ID
    unique_id = f"{timestamp}_{random_str}"
    return unique_id


def round_down_to_tick(last_price, tick_size=0.05, percentage_reduction=0.02):
    # 1. Calculate 2% less than last_price
    reduced_price = last_price * (1 - percentage_reduction)

    # 3. Round to the nearest 0.05 tick
    final_price = round(reduced_price / tick_size) * tick_size

    return final_price
