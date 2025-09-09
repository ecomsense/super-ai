from sys import exit
from os import path
from pprint import pprint
from toolkit.logger import Logger
from toolkit.fileutils import Fileutils
from typing import Any, Optional

S_DATA = "./data/"
S_FACT = "./factory/"
S_SETG = "settings.yml"
S_SYM = "symbols.yml"
S_RUNFILE = "run.txt"
S_LOG = S_DATA + "log.txt"


def refresh_files(filename: str) -> None:
    """
    description:
        create data dir and log file
        if did not if file did not exists
    input:
        file name with full path
    """
    if not Fileutils().is_file_exists(filename):
        print("creating data dir")
        Fileutils().add_path(filename)
    elif Fileutils().is_file_not_2day(filename):
        Fileutils().nuke_file(filename)


def yml_to_obj(arg=None):
    """
    description:
        creates empty yml file for credentials
        and also copies project specific settings
        to data folder
    """
    futl = Fileutils()
    if not arg:
        # return the parent folder name
        parent = path.dirname(path.abspath(__file__))
        print(f"{parent=}")
        grand_parent_path = path.dirname(parent)
        print(f"{grand_parent_path=}")
        folder = path.basename(grand_parent_path)
        # reverse the words seperated by -
        lst = folder.split("-")
        file = "_".join(reversed(lst))
        file = "../" + file + ".yml"
    else:
        file = S_DATA + arg

    flag = futl.is_file_exists(file)
    if not flag and arg:
        print(f"using default {file=}")
        futl.copy_file(S_FACT, S_DATA, S_SETG)
    elif not flag and arg is None:
        print(f"fill the {file=} file and try again")
        exit(1)

    return futl.get_lst_fm_yml(file)


def set_logger():
    """
    description:
        set custom logger's log level
        display or write to file
        based on user choice from settings
    """
    refresh_files(S_LOG)

    O_SETG = yml_to_obj(S_SETG)
    if isinstance(O_SETG, dict):
        level = O_SETG.get("log_level", 10)
        if O_SETG.get("log_show", True):
            return Logger(level)
        return Logger(level, S_LOG)
    else:
        return Logger()


logging = set_logger()


class TradeSet:
    """
    Manages the retrieval and state of strategy trade settings.
    consumed by main
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(TradeSet, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, data_dir=S_DATA, run_file=S_RUNFILE):
        self.data_dir = data_dir
        self.run_filepath = path.join(data_dir, run_file)
        refresh_files(self.run_filepath)
        if hasattr(self, "initialized"):
            return
        self.initialized = True

    def _get_run_state(self) -> set[str]:
        """Reads the state file and returns a set of run strategies."""
        try:
            with open(self.run_filepath, "r") as f:
                return {line.strip() for line in f}
        except FileNotFoundError:
            return set()

    def _find_next_strategy(self) -> Optional[str]:
        """
        Finds the most recent strategy setting file that has not been run today.
        This is now a private helper method.
        """
        all_from_dir = Fileutils().get_files_with_extn(extn="yml", diry=self.data_dir)
        all_from_dir = [f for f in all_from_dir if f != "settings.yml"]

        sets_from_file = self._get_run_state()
        yet_to_run = [s for s in all_from_dir if s not in sets_from_file]

        yet_to_run.sort(reverse=True)
        return yet_to_run.pop() if yet_to_run else None

    def _save_state(self, setting_file: str) -> None:
        """Appends the given setting file name to the run file."""
        with open(self.run_filepath, "a") as f:
            f.write(setting_file + "\n")

    def read(self) -> Optional[dict[str, Any]]:
        """
        Orchestrates the process of reading a trade setting. It's much simpler now.
        """
        curr_set = self._find_next_strategy()

        if curr_set:
            self._save_state(curr_set)
            trade_settings = Fileutils().get_lst_fm_yml(
                path.join(self.data_dir, curr_set)
            )
            print("\n*** settings ***")
            pprint(trade_settings)
            return trade_settings
        else:
            print("no strategy to trade")
            exit(1)


def get_symbol_fm_factory():
    """
    Reads the symbols configuration from the factory directory.
    consumed by strategy builder

    Returns:
        dict: A dictionary containing the symbol configurations.
    """
    # Define the file path for the symbols configuration
    fpath = path.join(S_FACT, S_SYM)

    # Read the file and store the contents in a dictionary
    dct_sym = Fileutils().read_file(fpath)

    # Return the dictionary with the symbol configurations
    return dct_sym
