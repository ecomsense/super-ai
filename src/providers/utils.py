from tabulate import tabulate


def table(cls_obj):
    items = [
        [k, v]
        for k, v in cls_obj.__dict__.items()
        if isinstance(v, float) or isinstance(v, int) or isinstance(v, str)
    ]
    print(tabulate(items, tablefmt="fancy_grid"))
