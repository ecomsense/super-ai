"""Tests for RiskManager, specifically the status() method."""
import pytest
from unittest.mock import Mock, MagicMock
from src.providers.risk_manager import RiskManager
from src.config.interface import Position


@pytest.fixture
def mock_broker():
    """Create a mock broker."""
    broker = Mock()
    broker.order_place.return_value = "ORD_12345"
    broker.positions = []
    return broker


@pytest.fixture
def rm(mock_broker):
    """Create a RiskManager instance."""
    return RiskManager(mock_broker)


class TestRiskManagerPositions:
    """Tests for positions property - dict vs Position object handling."""

    def test_positions_accepts_position_objects(self, rm):
        """RiskManager should accept Position objects directly."""
        pos = Position(symbol="NIFTY", quantity=10)
        rm.positions = [pos]
        
        assert len(rm.positions) == 1
        assert rm.positions[0].symbol == "NIFTY"

    def test_positions_converts_dicts_to_position_objects(self, rm):
        """RiskManager should convert dict-based positions to Position objects."""
        # This is what the broker API returns - a list of dicts
        position_book = [
            {"symbol": "NIFTY", "quantity": 10, "id": 123456},
            {"symbol": "BANKNIFTY", "quantity": 5, "id": 789012}
        ]
        rm.positions = position_book
        
        assert len(rm.positions) == 2
        assert rm.positions[0].symbol == "NIFTY"
        assert rm.positions[0].quantity == 10
        assert rm.positions[1].symbol == "BANKNIFTY"
        assert rm.positions[1].quantity == 5

    def test_positions_preserves_id_from_dict(self, rm):
        """RiskManager should preserve the id when converting from dict."""
        position_book = [{"symbol": "NIFTY", "quantity": 10, "id": 123456}]
        rm.positions = position_book
        
        assert rm.positions[0].id == 123456


class TestRiskManagerStatus:
    """Tests for the status() method."""

    def test_status_with_position_objects(self, rm, mock_broker):
        """status() should work when positions are Position objects."""
        # Setup: Create a position as a Position object
        pos = Position(symbol="NIFTY", quantity=10)
        pos.id = 123456
        rm.positions = [pos]
        
        # Setup mock to return positive quantity (simulating open position)
        mock_broker.positions = [{"symbol": "NIFTY", "quantity": 10, "exchange": "NFO"}]
        
        # Call status with a valid pos_id
        result = rm.status(pos_id=123456, last_price=100.0)
        
        # Verify: Should return 0 if order placed successfully, or positive qty
        assert result >= 0  # Either placed order (0) or has qty to sell (positive)

    def test_status_with_dict_based_positions(self, rm, mock_broker):
        """status() should work when positions are dicts (from broker API).
        
        This is the critical test that catches the bug where positions
        are received as dicts from the broker but the code expects Position objects.
        """
        # Setup: Create positions as dicts (like the broker returns)
        position_book = [{"symbol": "NIFTY", "quantity": 10, "id": 123456}]
        rm.positions = position_book
        
        # Setup mock to return positive quantity
        mock_broker.positions = [{"symbol": "NIFTY", "quantity": 10, "exchange": "NFO"}]
        
        # Call status - this should NOT raise an exception
        result = rm.status(pos_id=123456, last_price=100.0)
        
        # Verify: Should work without exceptions
        assert result >= 0

    def test_status_with_invalid_pos_id(self, rm, mock_broker):
        """status() should return -1 when pos_id is not found."""
        rm.positions = []  # No positions
        
        result = rm.status(pos_id=999999, last_price=100.0)
        
        assert result == -1

    def test_status_error_handler_does_not_crash(self, rm, mock_broker):
        """Error handler should not crash even when symbol is referenced before assignment.
        
        This test catches the bug where the exception handler tries to log
        '{symbol}' but symbol was never assigned due to an earlier exception.
        """
        # Setup: Create a position that will cause an error
        # Using a mock that will cause p.symbol to fail
        rm.positions = ["invalid_position"]  # String instead of dict or Position
        
        # This should not raise "local variable 'symbol' referenced before assignment"
        # It should handle the error gracefully
        result = rm.status(pos_id=123456, last_price=100.0)
        
        # Should return -1 on error
        assert result == -1

    def test_status_with_empty_positions(self, rm, mock_broker):
        """status() should return -1 when there are no positions."""
        rm.positions = []
        
        result = rm.status(pos_id=123456, last_price=100.0)
        
        assert result == -1


class TestRiskManagerNew:
    """Tests for the new() method."""

    def test_new_creates_position(self, rm, mock_broker):
        """new() should create a position and return pos_id."""
        result = rm.new(
            symbol="NIFTY",
            exchange="NFO",
            quantity=10,
            entry_price=100.0,
            stop_loss=90.0,
            target=110.0,
        )
        
        assert result is not None
        assert len(rm.positions) == 1
        assert rm.positions[0].symbol == "NIFTY"

    def test_new_with_dict_broker_response(self, rm, mock_broker):
        """new() should work when broker returns dicts for positions."""
        # Setup: Broker returns dict (like real API)
        mock_broker.positions = [{"symbol": "NIFTY", "quantity": 10}]
        
        result = rm.new(
            symbol="NIFTY",
            exchange="NFO",
            quantity=10,
            entry_price=100.0,
            stop_loss=90.0,
            target=110.0,
        )
        
        assert result is not None
        assert len(rm.positions) == 1