from toolkit.fileutils import Fileutils


def flatten_no_rename(d, result=None):
    if result is None:
        result = {}

    for k, v in d.items():
        if isinstance(v, dict):
            # Recurse into the dictionary
            flatten_no_rename(v, result)
        else:
            # Assign the value to the flat result
            result[k] = v
    return result


class Factory:
    data = {}

    @classmethod
    def settings(cls, strategy_name):
        settings = cls.data.get(strategy_name, None)
        if not settings:
            cls.data["strategy"] = flatten_no_rename(
                Fileutils().read_file("./factory/" + strategy_name + ".yml")
            )
            settings = cls.data["strategy"]
        return settings
