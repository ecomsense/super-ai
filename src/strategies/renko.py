from renkodf import RenkoWS
from datetime import datetime as dt
import pandas as pd
from constants import logging
from traceback import print_exc
from time_manager import TimeManager
from trade import Trade
import pendulum as pdlm
from helper import df_to_csv

MAGIC = 15
GFX = False
MIN_CANDLES_REQUIRED = 1

if GFX:
    import mplfinance as mpf
    import matplotlib.pyplot as plt


class Renko:
    _candle_count = 1
    _df_renko = pd.DataFrame()
    _orders = []
    _removable = False
    _target = None
    _trade_manager = None

    def __init__(self, prefix, user_settings: dict, symbol_info: dict) -> None:
        now = dt.now().timestamp()
        self._brick_size = user_settings["brick_size"]
        self._df_ticks = pd.DataFrame(
            columns=["timestamp", "Symbol", "close"],
            data=[[now, symbol_info["symbol"], symbol_info["ltp"]]],
        )
        self._highest = symbol_info["ltp"]
        self._prefix = prefix
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        self.r = RenkoWS(now, symbol_info["ltp"], brick_size=self._brick_size)
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        if GFX:
            _ = self._initialize_plot()
        self._fn = "enter_on_buy_signal"

    def _is_buy_signal(self):
        try:
            return self.trade.last_price > self._highest
        except Exception as e:
            print(f"{e} error in is_buy_signal")

    def enter_on_buy_signal(self):
        try:
            stoploss = self._highest
            if self._time_mgr.can_trade and self._is_buy_signal():
                self.trade.side = "B"
                self.trade.price = self.trade.last_price + 2
                self.trade.disclosed_quantity = None
                self.trade.trigger_price = 0.0
                self.trade.order_type = "LMT"
                self.trade.tag = "entry"
                buy_order = self._trade_manager.complete_entry(self.trade)
                if buy_order.order_id is not None:
                    self.trade.side = "S"
                    self.trade.disclosed_quantity = 0
                    self.trade.price = stoploss - 2
                    self.trade.trigger_price = stoploss
                    self.trade.order_type = "SL-LMT"
                    self.trade.tag = "stoploss"
                    sell_order = self._trade_manager.pending_exit(self.trade)
                    if sell_order.order_id is not None:
                        self._fn = "exit_on_sell_signal"
                        df_to_csv(
                            df=self._df_renko,
                            csv_file=f"entry_{dt.now().timestamp()}.csv",
                        )
                    else:
                        raise Exception("sell order is not found")
                else:
                    logging.warning(
                        f"ignoring buy signal for {self.trade.symbol} because unable to place order"
                    )
                    print_exc()
        except Exception as e:
            logging.error(f"{e} exiting")
            __import__("sys").exit(1)

    def _is_sell_signal(self):
        return self.trade.last_price < self._highest

    def _modify_to_exit(self):
        kwargs = dict(
            trigger_price=0.0,
            order_type="LMT",
            tag=None,
            last_price=self.trade.last_price,
        )
        if self._trade_manager.complete_exit(**kwargs):
            return True
        return False

    def exit_on_sell_signal(self):
        in_position = True

        order = self._trade_manager.find_order_if_exists(
            self._trade_manager.position.exit.order_id, self._orders
        )
        if isinstance(order, dict):
            in_position = False
        elif self._is_sell_signal():
            if self._modify_to_exit():
                in_position = False

        if not in_position:
            self._time_mgr.set_last_trade_time(pdlm.now("Asia/Kolkata"))
            self._fn = "enter_on_buy_signal"
            df_to_csv(
                df=self._df_renko,
                csv_file=f"exit_{dt.now().timestamp()}.csv",
            )

    def _initialize_plot(self):

        self.fig, self.ax = mpf.plot(
            self.r.initial_df,
            returnfig=True,
            volume=False,
            figsize=(11, 8),
            panel_ratios=(1,),
            type="candle",
            style="charles",
        )
        self.ax1 = self.ax[0]

    def common_func(self):
        try:
            now = dt.now().timestamp()
            self._df_ticks.loc[len(self._df_ticks)] = {
                "timestamp": now,
                "Symbol": self.trade.symbol,
                "close": self.trade.last_price,
            }
            self.r.add_prices(now, self.trade.last_price)
            return self.r.renko_animate("normal", max_len=MAGIC, keep=MAGIC - 1)
        except Exception as e:
            logging.error(f"{e} while common_func")
            print(e)
            return pd.DataFrame()

    def run(self, orders, ltps, prefixes: list):
        try:
            self._orders = orders

            ltp = ltps.get(self.trade.symbol, None)
            if ltp is not None:
                self.trade.last_price = float(ltp)

            self._df_renko = self.common_func()

            print(self._df_renko.tail(5))

            if self._df_renko is None or self._df_renko.empty:
                print("No data to plot.")
                return
            elif len(self._df_renko) < MIN_CANDLES_REQUIRED:
                print(f"candles are less than {MIN_CANDLES_REQUIRED}")
                return

            if GFX:
                self.ax1.clear()
                mpf.plot(
                    self._df_renko,
                    type="candle",
                    ax=self.ax1,
                    axtitle=self.trade.symbol,
                )
                self.fig.canvas.draw()
                self.fig.canvas.flush_events
                plt.pause(0.001)  # 👈 required to allow the GUI event loop to update

            method_returned = getattr(self, self._fn)()

            if len(self._df_renko) > self._candle_count:
                self._highest = self._df_renko.iloc[-1]["high"]
                logging.debug("new candle detected")
            logging.debug(f"highest:{self._highest} ltp:{self.trade.last_price}")
            return method_returned
        except Exception as e:
            logging.error(f"{e} in run")
            print_exc()
