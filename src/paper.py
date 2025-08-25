from src.constants import O_CNFG, S_DATA, logging
from src.utils import generate_unique_id
from src.helper import get_broker
from toolkit.fileutils import Fileutils
import pandas as pd
import pendulum as plum
from traceback import print_exc

ORDER_CSV = S_DATA + "orders.csv"


class Paper(get_broker()):
    cols = [
        "order_id",
        "broker_timestamp",
        "side",
        "filled_quantity",
        "symbol",
        "remarks",
        "status",
        "fill_price",
        "last_price",
    ]
    _orders = pd.DataFrame()

    def can_move_order_to_trade(self, order_id, ltp) -> bool:
        # TODO
        # move order_id to tradebook
        # if order trigger price is below ltp
        Flag = False
        orders = self.orders
        for order in orders:
            if order["order_id"] == order_id and ltp < order["fill_price"]:
                Flag = True
                break

        if Flag:
            self._orders.loc[
                self._orders["order_id"] == order["order_id"], "status"
            ] = "COMPLETE"

        return Flag

    @property
    def trades(self):
        """returns order book with status COMPLETE"""
        if not self._orders.empty:
            filtered_df = self._orders[self._orders["status"] == "COMPLETE"]
            return filtered_df.to_dict(orient="records")
        else:
            return [{}]

    def __init__(self, user_id, password, pin, vendor_code, app_key, imei, broker=""):
        super().__init__(user_id, password, pin, vendor_code, app_key, imei, broker)
        if Fileutils().is_file_not_2day(ORDER_CSV):
            Fileutils().nuke_file(ORDER_CSV)

    @property
    def orders(self):
        try:
            list_of_orders = self._orders
            pd.DataFrame(list_of_orders).to_csv(ORDER_CSV, index=False)
            return list_of_orders.to_dict(orient="records")
        except Exception as e:
            logging.error(f"{e} while returning trades")

    def order_place(self, **position_dict):
        try:
            if not position_dict.get("order_id", None):
                order_id = generate_unique_id()
                ops = "PLACE"
            else:
                order_id = position_dict["order_id"]
                ops = "MODIFY"

            UPPER = position_dict["order_type"][0].upper()
            is_trade = UPPER == "M" or UPPER == "L"
            fill_price = (
                position_dict["last_price"]
                if is_trade
                else position_dict["trigger_price"]
            )
            status = "COMPLETE" if is_trade else "TRIGGER PENDING"
            args = dict(
                order_id=order_id,
                broker_timestamp=plum.now().format("YYYY-MM-DD HH:mm:ss"),
                side=position_dict["side"],
                filled_quantity=int(position_dict["quantity"]),
                symbol=position_dict["symbol"],
                remarks=position_dict["tag"],
                fill_price=fill_price,
                status=status,
                last_price=position_dict["last_price"],
            )
            logging.info(f"{ops} order {args}")
            df = pd.DataFrame(columns=self.cols, data=[args])

            if not self._orders.empty:
                df = pd.concat([self._orders, df], ignore_index=True)
            self._orders = df
            _ = self.orders

            return order_id
        except Exception as e:
            logging.error(f"{e} exception while placing order")
            print_exc()

    def order_modify(self, **args):
        try:
            if not args.get("order_type", None):
                args["order_type"] = "MARKET"

            UPPER = args["order_type"][0].upper()
            if UPPER == "M" or UPPER == "L":
                # drop row whose order_id matches
                self._orders = self._orders[
                    self._orders["order_id"] != args["order_id"]
                ]
                print("*************************", args)
                order_id = self.order_place(**args)
                return order_id
            else:
                logging.warning(
                    "order modify for other order types not implemented for paper trading"
                )
        except Exception as e:
            logging.error(f"{e} order modify")
            print_exc()

    def calculate_realized_profit(self, df):
        # Separate buy and sell transactions
        buy_df = df[df["side"].str[0].str.upper() == "B"]
        sell_df = df[df["side"].str[0].str.upper() == "S"]

        # Group by symbol and sum quantities and prices
        buy_grouped = (
            buy_df.groupby("symbol")
            .agg({"filled_quantity": "sum", "fill_price": "sum", "last_price": "last"})
            .reset_index()
        )
        sell_grouped = (
            sell_df.groupby("symbol")
            .agg({"filled_quantity": "sum", "fill_price": "sum"})
            .reset_index()
        )

        # Merge buy and sell data
        result_df = pd.merge(
            buy_grouped,
            sell_grouped,
            on="symbol",
            suffixes=("_buy", "_sell"),
            how="outer",
        ).fillna(0)

        # Calculate average buy and sell prices
        result_df["avg_buy_price"] = (
            result_df["fill_price_buy"] / result_df["filled_quantity_buy"]
        )
        result_df["avg_sell_price"] = (
            result_df["fill_price_sell"] / result_df["filled_quantity_sell"]
        )

        # Avoid division errors (set NaN to 0 where needed)
        result_df.fillna(0, inplace=True)

        # Compute total traded quantity using vectorized min()
        result_df["total_traded_quantity"] = result_df[
            ["filled_quantity_buy", "filled_quantity_sell"]
        ].min(axis=1)

        # Calculate the net filled quantity by subtracting 'Sell' side quantity from 'Buy' side quantity
        result_df["quantity"] = (
            result_df["filled_quantity_buy"] - result_df["filled_quantity_sell"]
        )

        # Calculate realized profit (rpnl)
        result_df["rpnl"] = result_df["total_traded_quantity"] * (
            result_df["avg_sell_price"] - result_df["avg_buy_price"]
        )

        # Calculate the unrealized mark-to-market (urmtom) value
        result_df["urmtom"] = result_df.apply(
            lambda row: (
                (row["last_price"] - row["avg_buy_price"]) * row["quantity"]
                if row["quantity"] > 0
                else (row["avg_sell_price"] - row["last_price"]) * abs(row["quantity"])
            ),
            axis=1,
        )

        # Drop unnecessary columns
        result_df.drop(
            columns=[
                "filled_quantity_buy",
                "filled_quantity_sell",
                "fill_price_buy",
                "fill_price_sell",
            ],
            inplace=True,
        )
        return result_df

    @property
    def positions(self):
        try:
            lst = []
            resp = self.trades
            if resp and any(resp):
                df = pd.DataFrame(resp)
                print(df)
                df = self.calculate_realized_profit(df)
                lst = df.to_dict(orient="records")
        except Exception as e:
            logging.debug(f"paper positions error: {e}")
        finally:
            return lst


if __name__ == "__main__":
    try:
        from constants import O_CNFG

        paper = Paper(**O_CNFG)
        args = dict(
            symbol="NIFTY",
            exchange="NSE",
            quantity=1,
            side="BUY",
            price=20,
            trigger_price=21,
            product="MIS",
            order_type="MARKET",
            last_price=20,
            tag="entry",
        )
        # buy order
        resp = paper.order_place(**args)
        print(f"order place resp {resp}")
        # sell order
        sargs = args.copy()
        sargs["side"] = "SELL"
        sargs["order_type"] = "SL"
        sargs["tag"] = "stoploss"
        resp = paper.order_place(**sargs)

        # sell modfy
        sargs["order_id"] = resp
        sargs["order_type"] = "Limit"
        sargs["price"] = 0
        sargs["trigger_price"] = 50
        sargs["last_price"] = 51
        sargs["tag"] = "target"
        resp = paper.order_modify(**sargs)
        print(f"order modify resp {resp}")

        # buy order
        resp = paper.order_place(**args)
        print(f"order place resp {resp}")
        print(paper.orders)

        result = paper.positions
        print(result)

        """
        if resp and any(resp):
            total_rpnl = sum(
                item["rpnl"]
                for item in resp
                if item["symbol"].startswith(self._prefix)
            )
            if total_rpnl < 0:
                count = len(
                    [
                        order
                        for order in self._orders
                        if order["symbol"].startswith(self._prefix)
                    ]
                )
                rate_to_be_added = total_rpnl / self._quantity
                rate_to_be_added += count * self._txn / 2
        """
    except Exception as e:
        print(e)
