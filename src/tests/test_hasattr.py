

class xyz:
    _property_name = False 

    def is_property_set(self):
        if self._property_name:
            print("does not have property set")
        else:
            # set property if it does not exist
            self._property_name = True
            print("property exists")


if __name__ == "__main__":
    try:
        inst = xyz()
        while True:
            inst.is_property_set()
            __import__("time").sleep(1)
    except KeyboardInterrupt as k:
        __import__("sys").exit()

