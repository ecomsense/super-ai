import sys
from os import path
from traceback import print_exc
from pprint import pprint
from toolkit.logger import Logger
from toolkit.fileutils import Fileutils
from typing import Any, Optional

O_FUTL = Fileutils()
S_DATA = "data/"
S_LOG = S_DATA + "log.txt"
S_RUNFILE = S_DATA + "run.txt"

def refresh_files(filename: str) -> None:
    """
    description:
        create data dir and log file
        if did not if file did not exists
    input:
        file name with full path
    """
    if not O_FUTL.is_file_exists(filename):
        print("creating data dir")
        O_FUTL.add_path(filename)
    elif O_FUTL.is_file_not_2day(filename):
        O_FUTL.nuke_file(filename)


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


def read_yml() -> tuple[dict[str, Any], dict[str, Any]]:
    """Read YML files."""
    try:
        O_CNFG = yml_to_obj()
        O_SETG = yml_to_obj("settings.yml")
    except Exception as e:  # pylint: disable=broad-except
        print(e, file=sys.stderr)
        print_exc()
        sys.exit(1)  
    else:
        return O_CNFG, O_SETG



def load_state():
    """
    Reads the state file and returns a set of strategy setting files that have
    already been run today.

    Returns:
        set: A set of strategy setting files that have already been run today.
    """
    try:
        with open(S_RUNFILE) as f:
            return set(line.strip() for line in f)
    except FileNotFoundError:
        return set()

def save_state(setting_file):
    """
    Appends the given setting file name to the run file.

    Args:
        setting_file (str): The name of the setting file to save.
    """
    with open(S_RUNFILE, "a") as f:
        # Write the setting file name followed by a newline character
        f.write(setting_file + "\n")

def get_current_set() -> Optional[str]:
    """
    Retrieves the most recent strategy setting file that has not been run today.

    Returns:
        str: The name of the most recent strategy setting file that has not been run today.
        None: If all strategy setting files have been run today.
    """
    # read available strategy settings file for trading from data directory
    all_from_dir = O_FUTL.get_files_with_extn(extn="yml", diry=S_DATA)
    all_from_dir = [set for set in all_from_dir if set != 'settings.yml']

    # read state file for strategies that is already run today
    sets_from_file = load_state()

    # find the settings that have not been run today
    yet_to_run = [settings for settings in all_from_dir if settings not in sets_from_file]

    # sort the settings in descending order
    yet_to_run.sort(reverse=True)

    # return the most recent settings
    return yet_to_run.pop() if yet_to_run else None

def get_current_trade_settings():
    """
    Retrieves the current trade settings from the state file.
    If a new trade settings file is found, it saves the state and returns the new settings.
    If no new settings are found, it prints a message and exits the program.

    Returns:
        dict: The current trade settings.
    """
    curr_set = get_current_set()
    if curr_set:
        # save the state
        save_state(curr_set)

        # read the new settings
        trade_settings = O_FUTL.get_lst_fm_yml(S_DATA + curr_set)
        return trade_settings
    else:
        print("no strategy to trade")
        sys.exit(1)


def get_symbol_fm_factory():
    """
    Reads the symbols configuration from the factory directory.

    Returns:
        dict: A dictionary containing the symbol configurations.
    """
    # Define the file path for the symbols configuration
    fpath = "./factory/symbols.yaml"
    
    # Read the file and store the contents in a dictionary
    dct_sym = O_FUTL.read_file(fpath)
    
    # Return the dictionary with the symbol configurations
    return dct_sym


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

filenames = [S_LOG, S_RUNFILE]
for filename in filenames:
    refresh_files(filename)


O_CNFG, O_SETG = read_yml()
O_TRADESET = get_current_trade_settings()
dct_sym = get_symbol_fm_factory()
logging = set_logger()

print("*** broker credentials ***")
pprint(O_CNFG)

print("\n*** settings ***")
pprint(O_SETG)

print("\n*** trade settings ***")
pprint(O_TRADESET)


