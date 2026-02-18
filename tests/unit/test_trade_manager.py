def test_trade_manager_initialization(tm):
    """Verifies that TM starts in an idle state with correct attributes."""
    assert tm.position.state == "idle"
    assert tm.position.slippage == 2
    assert tm._trade_template.quantity == 15


def test_complete_entry_flow(tm, mock_broker):
    """Tests the transition from IDLE to ENTRY_PENDING."""
    price = 100.0
    order_id = tm.complete_entry(price=price)

    # Verify order placement
    assert order_id == "ORD_12345"
    assert tm.position.state == "entry_pending"

    # Verify slippage math: price + slippage
    mock_broker.order_place.assert_called_once()
    assert tm.position.entry.price == 102.0


def test_pending_exit_success(tm, mock_broker):
    """Tests placing a stop-loss order once the entry is filled."""
    # 1. Setup an existing entry
    tm.position.entry = tm._trade_template
    tm.position.entry.order_id = "BUY_001"

    # 2. Simulate orders list from broker showing entry is filled
    orders = [{"order_id": "BUY_001", "fill_price": "105.0"}]

    # 3. Execute pending_exit
    exit_order = tm.pending_exit(stop=100.0, orders=orders, last_price=106.0)

    # 4. Assertions
    assert exit_order.side == "S"
    assert tm.position.stop_price == 100.0
    assert tm.position.average_price == 105.0
    # Price for SL-LMT is stop - slippage
    assert exit_order.price == 98.0


def test_is_trade_exited_stop_hit(tm):
    """Verifies state detection when a stop loss is hit via order matching."""
    tm.position.exit = tm._trade_template
    tm.position.exit.order_id = "SELL_001"

    # Simulate broker orders showing the exit order exists (meaning it was hit/filled)
    orders = [{"order_id": "SELL_001"}]

    status = tm.is_trade_exited(last_price=105.0, orders=orders)

    assert status == 1  # Stop hit code


def test_is_trade_exited_market_kill(tm, mock_broker):
    """Verifies that TM kills the trade if price drops below stop (Market Exit)."""
    tm.stop(stop_price=100.0)
    tm.position.exit = tm._trade_template
    tm.position.exit.order_id = "SELL_001"

    # Current price (95) is less than stop (100)
    status = tm.is_trade_exited(last_price=95.0, orders=[])

    assert status == 1
    mock_broker.order_modify.assert_called_once()


def test_run_loop_transitions(tm, mock_broker):
    """Verifies the state machine 'run' loop logic."""
    # Setup state to entry_pending
    tm.position.state = "entry_pending"
    tm.position.entry = tm._trade_template
    tm.position.entry.order_id = "BUY_001"
    tm.position.stop_price = 90.0

    # Simulate entry not filled yet
    tm.run(orders=[], last_price=100.0)

    # Should attempt to modify the entry to chase the price
    mock_broker.order_modify.assert_called_once()
