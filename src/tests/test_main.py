# is in strategies folder
class Pivot:

    def __init__(self, dummy):
        self.dummy = dummy
        self.fn = self.do_first

    def do_first(self):
        print("first")
        self.fn = self.do_second

    def do_second(self):
        print("second")
        # is stop hit
        # is ltp below entry price
        self.fn = self.do_first

    def run(self):
        getattr(self, "fn")()


# main.py
def main():
    # initialse api
    # get symbols to trade
    # get tokens
    # subscribe to websocket for ltp
    pivot = Pivot("harinath")
    while True:
        pivot.run()
        __import__("time").sleep(1)


if __name__ == "__main__":
    main()
