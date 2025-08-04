from os import path
from traceback import print_exc
from pprint import pprint
from toolkit.logger import Logger
from toolkit.fileutils import Fileutils

O_FUTL = Fileutils()
S_DATA = "data/"
S_LOG = S_DATA + "log.txt"
S_RUNFILE = S_DATA + "run.txt"

def refresh_files(filename):
    if not O_FUTL.is_file_exists(filename):
        """
        description:
            create data dir and log file
            if did not if file did not exists
        input:
            file name with full path
        """
        print("creating data dir")
        O_FUTL.add_path(filename)
    elif O_FUTL.is_file_not_2day(filename):
        O_FUTL.nuke_file(filename)

filenames = [S_LOG, S_RUNFILE]
for filename in filenames:
    refresh_files(filename)


def yml_to_obj(arg=None):
    """
    description:
        creates empty yml file for credentials
        and also copies project specific settings
        to data folder
    """
    if not arg:
        # return the parent folder name
        parent = path.dirname(path.abspath(__file__))
        print(f"{parent=}")
        grand_parent_path = path.dirname(parent)
        print(f"{grand_parent_path=}")
        folder = path.basename(grand_parent_path)
        """
        folder = path.basename(parent)
        """
        # reverse the words seperated by -
        lst = folder.split("-")
        file = "_".join(reversed(lst))
        file = "../" + file + ".yml"
    else:
        file = S_DATA + arg

    flag = O_FUTL.is_file_exists(file)

    if not flag and arg:
        print(f"using default {file=}")
        O_FUTL.copy_file("factory/", "data/", "settings.yml")
    elif not flag and arg is None:
        print(f"fill the {file=} file and try again")
        __import__("sys").exit(1)

    return O_FUTL.get_lst_fm_yml(file)


def read_yml():
    try:
        O_CNFG = yml_to_obj()
        O_SETG = yml_to_obj("settings.yml")
    except Exception as e:
        print(e)
        print_exc()
        __import__("sys").exit(1)
    else:
        return O_CNFG, O_SETG




O_CNFG, O_SETG = read_yml()
print("broker credentials" + "\n" + "*****************")
pprint(O_CNFG)

print("settings " + "\n" + "*****************")
pprint(O_SETG)

def load_state():
    try:
        with open(S_RUNFILE) as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_state(setting_file):
    with open(S_RUNFILE, "a") as f:
        f.write(setting_file + "\n")

def get_current_set():
    # read available strategy settings file for trading from data directory
    all_from_dir = O_FUTL.get_files_with_extn(extn="yml", diry=S_DATA)
    all_from_dir:list = [set for set in all_from_dir if set!='settings.yml']

    # read state file for strategies that is already run today
    sets_from_file: set = load_state()

    yet_to_run = [settings for settings in all_from_dir if settings not in sets_from_file]

    yet_to_run.sort(reverse=True)
    return yet_to_run.pop() if yet_to_run else None

def get_current_trade_settings():
    curr_set = get_current_set()
    if curr_set:
        save_state(curr_set)
        trade_settings = O_FUTL.get_lst_fm_yml(S_DATA + curr_set)
        print("trade settings" + "\n" + "*****************")
        pprint(trade_settings)
        return trade_settings
    else:
        print("no strategy to trade")
        __import__("sys").exit(1)

O_TRADESET = get_current_trade_settings()


def get_symbol_fm_factory():
    fpath = "./factory/symbols.yaml"
    dct_sym = O_FUTL.read_file(fpath)
    print(dct_sym)
    return dct_sym


dct_sym = get_symbol_fm_factory()


def set_logger():
    """
    description:
        set custom logger's log level
        display or write to file
        based on user choice from settings
    """
    level = O_SETG["log_level"]
    if O_SETG["log_show"]:
        return Logger(level)
    return Logger(level, S_LOG)


logging = set_logger()
