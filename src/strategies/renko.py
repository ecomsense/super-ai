from renkodf import RenkoWS
from datetime import datetime as dt
import pandas as pd
from constants import logging
from traceback import print_exc
from time_manager import TimeManager
from trade import Trade
import pendulum as pdlm

MAGIC = 15
GFX = False
MIN_CANDLES_REQUIRED = 3

if GFX:
    import mplfinance as mpf
    import matplotlib.pyplot as plt


class Renko:
    _orders = []
    _target = None
    _removable = False
    _trade_manager = None
    _df_renko = pd.DataFrame()

    def __init__(self, prefix, user_settings: dict, symbol_info: dict) -> None:
        self._prefix = prefix
        self.trade = Trade(
            symbol=symbol_info["symbol"],
            last_price=symbol_info["ltp"],
            exchange=user_settings["option_exchange"],
            quantity=user_settings["quantity"],
        )
        self._brick_size = user_settings["brick_size"]
        self._highest = symbol_info["ltp"]
        self._time_mgr = TimeManager(rest_min=user_settings["rest_min"])
        now = dt.now().timestamp()
        self._df_ticks = pd.DataFrame(
            columns=["timestamp", "Symbol", "close"],
            data=[[now, self.trade.symbol, self.trade.last_price]],
        )
        self.r = RenkoWS(now, self.trade.last_price, brick_size=self._brick_size)
        if GFX:
            _ = self._initialize_plot()
        self._fn = "enter_on_buy_signal"

    def _is_buy_signal(self):
        try:
            return (
                self.trade.last_price >= self._highest
                and self._df_renko.iloc[-2]["close"] > self._df_renko.iloc[-2]["open"]
            )
        except Exception as e:
            print(f"{e} error in is_buy_signal")

    def enter_on_buy_signal(self):
        try:
            stoploss = self._df_renko.iloc[-3]["low"]
            if self._time_mgr.can_trade and self._is_buy_signal():
                self.trade.side = "B"
                self.trade.price = self.trade.last_price + 2
                self.trade.trigger_price = None
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
                    else:
                        raise Exception("sell order is not found")
                else:
                    logging.warning(
                        f"ignoring buy signal for {self.trade.symbol} because unable to place order"
                    )
        except Exception as e:
            logging.error(f"{e} exiting")
            __import__("sys").exit(1)

    def _is_sell_signal(self):
        if self._df_renko.iloc[-2]["close"] < self._df_renko.iloc[-2]["open"]:
            return True
        return False

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

            self._highest = (
                self.trade.last_price
                if self.trade.last_price > self._highest
                else self._highest
            )
            return method_returned
        except Exception as e:
            logging.error(f"{e} in run")
            print_exc()
