from unittest.mock import patch
from src.providers.position_manager import PositionManager, NFOManager


def test_pm_new_creates_entry(mock_broker, global_mocks):
    pm = PositionManager(mock_broker)

    mock_pos_class = global_mocks["pm_position"]
    mock_nfo_class = global_mocks["nfo_manager"]

    # instance
    mock_pos = global_mocks["mock"]

    mock_pos_class.return_value = mock_pos
    mock_nfo_class.return_value = mock_pos.ex

    # FIX 1: You must tell create_entry to hand the position object back
    # Otherwise, pm.new() overwrites `pos` with a blank MagicMock
    mock_pos.ex.create_entry.return_value = mock_pos

    # Pre-fill the values your assertions (and pm.new's if-statement) are looking for
    mock_pos.id = 777
    mock_pos.entry.order_id = "ORD_12345"
    mock_pos.state = "entry_pending"
    # ------------------------

    entry_price = 100
    tag = "hilo_test"

    # FIX 2: Temporarily swap the real NFOManager inside the dictionary with your mock
    with patch.dict(
        "src.providers.position_manager.executors", {"NFO": mock_nfo_class}
    ):
        # Execute
        pos_id = pm.new(
            symbol="BANKNIFTY-OPT",
            exchange="NFO",
            quantity=15,
            tag=tag,
            entry_price=entry_price,
            stop_loss=90.0,
            target=150.0,
        )

    # 1. Verify position was registered correctly
    assert pos_id in pm._positions

    # 2. Verify it delegated the creation to the executor mock
    mock_pos.ex.create_entry.assert_called_once_with(mock_pos, last_price=entry_price)

    # 3. Verify state and broker interactions
    assert mock_pos.state == "entry_pending"
    assert mock_pos.entry.order_id == "ORD_12345"


def test_pm_status_position_unknown(mock_broker):
    pm = PositionManager(mock_broker)
    result = pm.status(pos_id=999, last_price=100.0, orders=[])

    assert result == "position_unknown"


def test_pm_status_entry_into_position(mock_broker):
    # Setup the real Manager with a Mock Broker
    pm = PositionManager(mock_broker)

    # Configure the broker to return a valid Order ID string
    mock_broker.order_place.return_value = "ORD_12345"

    # 1. Trigger 'new'
    # This creates a REAL Position and a REAL NFOManager instance
    pos_id = pm.new(
        symbol="BANKNIFTY-OPT",
        exchange="NFO",
        quantity=15,
        tag="test",
        entry_price=100.0,
        stop_loss=90.0,
        target=150.0,
        trail_percent=None,  # Keep as None to avoid the float conversion logic for this test
    )

    # 2. Simulate the broker filling the entry order
    orders = [{"order_id": "ORD_12345", "fill_price": "100.0"}]

    # 3. Trigger status update
    # This will run: PM.status -> NFO.wait_for_entry -> NFO.create_exit
    pm.status(pos_id=pos_id, last_price=105.0, orders=orders)

    # 4. Fetch the actual position from the registry
    pos = pm._positions[pos_id]

    # --- ASSERTIONS ---
    # Verify the fill was recorded
    assert pos.average_price == 100.0

    # Verify the state progressed immediately to exit_pending
    assert pos.state == "exit_pending"

    # Verify exactly 2 calls: 1 for Entry and 1 for the Stop Loss (Exit)
    assert mock_broker.order_place.call_count == 2

    # Verify the exit order ID was captured correctly
    assert pos.exit.order_id == "ORD_12345"


def test_nfo_manager_create_exit(mock_broker, global_mocks):
    # Isolate NFOManager logic
    pos = global_mocks["mock"]
    pos.stop_price = 90.0
    pos.slippage = 2.0
    pos.symbol = "BANKNIFTY-OPT"
    pos.quantity = 15

    nfo = NFOManager(mock_broker, pos, "test_tag", exit_method="target")

    updated_pos = nfo.create_exit(pos, last_price=100.0)

    assert updated_pos.state == "exit_pending"
    assert updated_pos.exit.order_id == "ORD_12345"
    assert nfo.next_fn == "modify"
    mock_broker.order_place.assert_called_once()


def test_nfo_manager_modify_and_cancel(mock_broker, global_mocks):
    # Setup mock state for modification
    pos = global_mocks["mock"]
    pos.state = "target_pending"
    pos.exit.order_id = "EXT_123"

    nfo = NFOManager(mock_broker, pos, "test_tag", exit_method="target")

    # 1. Test Modification logic
    nfo.modify(pos, last_price=150.0)
    mock_broker.order_modify.assert_called_once_with(
        order_id="EXT_123", order_type="LMT", trigger_price=0.0
    )
    assert nfo.next_fn == "cancel"

    # 2. Test Cancellation logic
    nfo.cancel(pos, last_price=150.0)
    mock_broker.order_cancel.assert_called_once_with(order_id="EXT_123")
    assert nfo.next_fn == "final_exit"


def test_pm_status_cleanup(mock_broker, global_mocks):
    pm = PositionManager(mock_broker)

    # Manually inject a position in 'target_reached' state
    mock_pos = global_mocks["mock"]
    mock_pos.state = "target_reached"
    mock_pos.exit.order_id = "EXIT_999"
    mock_pos.next_fn = "modify"
    mock_pos.ex = global_mocks["mock"]

    pm._positions[1] = mock_pos
    orders = [{"order_id": "EXIT_999"}]

    # Trigger status update
    pm.status(pos_id=1, last_price=150.0, orders=orders)

    # Ensure the position was successfully garbage collected from the dict
    assert 1 not in pm._positions
