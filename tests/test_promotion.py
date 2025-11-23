"""
Tests for Strategy Promotion Workflow

Tests the multi-gate approval process for promoting strategies from paper
trading to live trading, including validation checks, manual approvals, and
approval trail persistence.
"""

import pytest
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path

from strategy.promotion import (
    PromotionWorkflow,
    ApprovalGate,
    ApprovalChecklist,
    ApprovalRecord
)
from strategy.lifecycle import StrategyState, StrategyLifecycle
from strategy.metrics_tracker import PaperMetricsTracker
from strategy.validation import ValidationEnforcer, ValidationCriteria


@pytest.fixture
def temp_db():
    """Temporary database for testing"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def lifecycle(temp_db):
    """StrategyLifecycle instance"""
    return StrategyLifecycle(temp_db)


@pytest.fixture
def tracker(temp_db):
    """PaperMetricsTracker instance"""
    return PaperMetricsTracker(temp_db, "test_strategy", initial_capital=100000.0)


@pytest.fixture
def enforcer():
    """ValidationEnforcer with relaxed criteria for testing"""
    criteria = ValidationCriteria(
        min_days=10,
        min_trades=5,
        min_sharpe_ratio=0.5,
        max_drawdown=0.15,
        min_win_rate=0.50,
        min_profit_factor=1.5,
        max_consecutive_losses=5
    )
    return ValidationEnforcer(criteria)


@pytest.fixture
def workflow(temp_db, enforcer):
    """PromotionWorkflow instance"""
    return PromotionWorkflow(temp_db, enforcer)


def setup_passing_validation(tracker):
    """Helper to set up tracker with passing validation data"""
    # Set start date 15 days ago
    tracker.start_date = date.today() - timedelta(days=15)
    
    # Record 10 winning trades
    entry_time = datetime.now()
    exit_time = entry_time + timedelta(hours=1)
    
    for i in range(10):
        tracker.record_trade(
            symbol=f"WIN{i}",
            side="BUY",
            quantity=100,
            entry_price=100.0,
            exit_price=107.0,
            entry_time=entry_time,
            exit_time=exit_time,
            commission=2.0
        )
    
    # Record daily snapshots with positive returns
    for i in range(15):
        snapshot_date = date.today() - timedelta(days=14-i)
        portfolio_value = 100000 + (i * 400)
        tracker.record_daily_snapshot(
            snapshot_date=snapshot_date,
            portfolio_value=portfolio_value,
            cash=50000,
            positions_value=portfolio_value - 50000,
            daily_pnl=400,
            trade_count=0,
            realized_pnl=0.0,
            unrealized_pnl=0.0
        )


def manual_set_state(lifecycle, strategy_name, state):
    """Manually set strategy state (bypassing validation)"""
    import sqlite3
    conn = sqlite3.connect(lifecycle.db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE strategy_state SET current_state = ? WHERE strategy_name = ?",
        (state.value, strategy_name)
    )
    conn.commit()
    conn.close()


class TestPromotionWorkflowInitialization:
    """Test workflow initialization and database setup"""
    
    def test_initialization(self, temp_db):
        """Test workflow initializes correctly"""
        workflow = PromotionWorkflow(temp_db)
        
        assert workflow.db_path == Path(temp_db)
        assert workflow.lifecycle is not None
        assert workflow.enforcer is not None
    
    def test_database_tables_created(self, workflow, temp_db):
        """Test that required tables are created"""
        import sqlite3
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        # Check approval_history table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='approval_history'
        """)
        assert cursor.fetchone() is not None
        
        # Check checklist_state table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='checklist_state'
        """)
        assert cursor.fetchone() is not None
        
        conn.close()


class TestApprovalChecklist:
    """Test approval checklist functionality"""
    
    def test_empty_checklist_not_complete(self):
        """Test empty checklist is not complete"""
        checklist = ApprovalChecklist()
        
        assert not checklist.is_complete()
        assert len(checklist.get_incomplete_items()) == 7
    
    def test_partial_checklist_not_complete(self):
        """Test partially filled checklist is not complete"""
        checklist = ApprovalChecklist(
            strategy_code_reviewed=True,
            risk_parameters_verified=True
        )
        
        assert not checklist.is_complete()
        incomplete = checklist.get_incomplete_items()
        assert len(incomplete) == 5
        assert "strategy_code_reviewed" not in incomplete
        assert "position_sizing_confirmed" in incomplete
    
    def test_complete_checklist(self):
        """Test fully filled checklist is complete"""
        checklist = ApprovalChecklist(
            strategy_code_reviewed=True,
            risk_parameters_verified=True,
            position_sizing_confirmed=True,
            emergency_procedures_tested=True,
            monitoring_alerts_configured=True,
            historical_performance_reviewed=True,
            market_conditions_assessed=True
        )
        
        assert checklist.is_complete()
        assert len(checklist.get_incomplete_items()) == 0
    
    def test_checklist_to_dict(self):
        """Test checklist conversion to dictionary"""
        checklist = ApprovalChecklist(strategy_code_reviewed=True)
        data = checklist.to_dict()
        
        assert isinstance(data, dict)
        assert data['strategy_code_reviewed'] is True
        assert data['risk_parameters_verified'] is False
    
    def test_checklist_from_dict(self):
        """Test checklist creation from dictionary"""
        data = {
            'strategy_code_reviewed': True,
            'risk_parameters_verified': False,
            'position_sizing_confirmed': True,
            'emergency_procedures_tested': False,
            'monitoring_alerts_configured': False,
            'historical_performance_reviewed': True,
            'market_conditions_assessed': False
        }
        
        checklist = ApprovalChecklist.from_dict(data)
        
        assert checklist.strategy_code_reviewed is True
        assert checklist.risk_parameters_verified is False
        assert checklist.position_sizing_confirmed is True


class TestGate1Validation:
    """Test Gate 1 (PAPER → VALIDATED) approval process"""
    
    def test_gate1_fails_without_sufficient_data(self, workflow, tracker):
        """Test Gate 1 fails without meeting validation criteria"""
        can_pass, reason, report = workflow.can_pass_gate1(tracker)
        
        assert not can_pass
        assert "Validation failed" in reason
        assert report is not None
        assert not report.overall_passed
    
    def test_gate1_passes_with_valid_data(self, workflow, tracker, lifecycle):
        """Test Gate 1 passes with valid paper trading performance"""
        # Set up strategy in PAPER state
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.PAPER)
        
        # Set up passing validation data
        setup_passing_validation(tracker)
        
        can_pass, reason, report = workflow.can_pass_gate1(tracker)
        
        assert can_pass
        assert "Automated validation passed" in reason
        assert report.overall_passed
    
    def test_gate1_requires_manual_when_flag_set(self, workflow, tracker):
        """Test Gate 1 can require manual approval even when automated checks pass"""
        # Set up passing validation
        setup_passing_validation(tracker)
        
        can_pass, reason, report = workflow.can_pass_gate1(tracker, require_manual=True)
        
        assert not can_pass
        assert "Manual review required" in reason
        assert report.overall_passed  # Automated checks passed
    
    def test_approve_gate1_transitions_to_validated(self, workflow, tracker, lifecycle):
        """Test approve_gate1 transitions strategy to VALIDATED state"""
        # Set up strategy in PAPER state
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.PAPER)
        
        # Set up passing validation
        setup_passing_validation(tracker)
        
        success = workflow.approve_gate1(
            tracker=tracker,
            approved_by="test_user",
            notes="Automated validation passed"
        )
        
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.VALIDATED
    
    def test_approve_gate1_records_approval_history(self, workflow, tracker, lifecycle):
        """Test approve_gate1 records approval in history"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.PAPER)
        
        # Set up passing validation
        setup_passing_validation(tracker)
        
        workflow.approve_gate1(tracker=tracker, approved_by="test_user")
        
        history = workflow.get_approval_history("test_strategy")
        
        assert len(history) == 1
        assert history[0].gate == ApprovalGate.GATE_1_VALIDATION
        assert history[0].approved_by == "test_user"
        assert history[0].validation_report is not None


class TestGate2LiveApproval:
    """Test Gate 2 (VALIDATED → LIVE_APPROVED) approval process"""
    
    def test_gate2_fails_without_complete_checklist(self, workflow, lifecycle):
        """Test Gate 2 fails without completed checklist"""
        lifecycle.register_strategy("test_strategy")
        
        can_pass, reason, checklist = workflow.can_pass_gate2("test_strategy")
        
        assert not can_pass
        assert "Checklist incomplete" in reason
        assert not checklist.is_complete()
    
    def test_gate2_passes_with_complete_checklist(self, workflow, lifecycle):
        """Test Gate 2 passes with completed checklist"""
        lifecycle.register_strategy("test_strategy")
        
        # Complete all checklist items
        workflow.update_checklist(
            "test_strategy",
            strategy_code_reviewed=True,
            risk_parameters_verified=True,
            position_sizing_confirmed=True,
            emergency_procedures_tested=True,
            monitoring_alerts_configured=True,
            historical_performance_reviewed=True,
            market_conditions_assessed=True
        )
        
        can_pass, reason, checklist = workflow.can_pass_gate2("test_strategy")
        
        assert can_pass
        assert "Checklist complete" in reason
        assert checklist.is_complete()
    
    def test_update_checklist_partial(self, workflow, lifecycle):
        """Test updating checklist items individually"""
        lifecycle.register_strategy("test_strategy")
        
        # Update first item
        workflow.update_checklist("test_strategy", strategy_code_reviewed=True)
        checklist = workflow.get_checklist("test_strategy")
        assert checklist.strategy_code_reviewed is True
        assert checklist.risk_parameters_verified is False
        
        # Update second item
        workflow.update_checklist("test_strategy", risk_parameters_verified=True)
        checklist = workflow.get_checklist("test_strategy")
        assert checklist.strategy_code_reviewed is True
        assert checklist.risk_parameters_verified is True
    
    def test_approve_gate2_transitions_to_live_approved(self, workflow, lifecycle):
        """Test approve_gate2 transitions strategy to LIVE_APPROVED"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.VALIDATED)
        
        # Complete checklist
        workflow.update_checklist(
            "test_strategy",
            strategy_code_reviewed=True,
            risk_parameters_verified=True,
            position_sizing_confirmed=True,
            emergency_procedures_tested=True,
            monitoring_alerts_configured=True,
            historical_performance_reviewed=True,
            market_conditions_assessed=True
        )
        
        success = workflow.approve_gate2(
            strategy_name="test_strategy",
            approved_by="manager",
            notes="All checks passed"
        )
        
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.LIVE_APPROVED
    
    def test_approve_gate2_fails_without_checklist(self, workflow, lifecycle):
        """Test approve_gate2 fails without completed checklist"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.VALIDATED)
        
        success = workflow.approve_gate2(
            strategy_name="test_strategy",
            approved_by="manager"
        )
        
        assert not success
        assert lifecycle.get_state("test_strategy") == StrategyState.VALIDATED


class TestGate3LiveActivation:
    """Test Gate 3 (LIVE_APPROVED → LIVE_ACTIVE) approval process"""
    
    def test_gate3_fails_if_not_live_approved(self, workflow, lifecycle):
        """Test Gate 3 fails if strategy not in LIVE_APPROVED state"""
        lifecycle.register_strategy("test_strategy")
        lifecycle.transition("test_strategy", StrategyState.VALIDATED)
        
        can_pass, reason = workflow.can_pass_gate3("test_strategy")
        
        assert not can_pass
        assert "LIVE_APPROVED state" in reason
    
    def test_gate3_passes_if_live_approved(self, workflow, lifecycle):
        """Test Gate 3 passes if strategy in LIVE_APPROVED state"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.LIVE_APPROVED)
        
        can_pass, reason = workflow.can_pass_gate3("test_strategy")
        
        assert can_pass
        assert "Ready for live activation" in reason
    
    def test_approve_gate3_transitions_to_live_active(self, workflow, lifecycle):
        """Test approve_gate3 transitions strategy to LIVE_ACTIVE"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.LIVE_APPROVED)
        
        success = workflow.approve_gate3(
            strategy_name="test_strategy",
            approved_by="ceo",
            notes="Final approval granted"
        )
        
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.LIVE_ACTIVE
    
    def test_approve_gate3_records_approval(self, workflow, lifecycle):
        """Test approve_gate3 records approval in history"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.LIVE_APPROVED)
        
        workflow.approve_gate3(
            strategy_name="test_strategy",
            approved_by="ceo",
            notes="Go live"
        )
        
        history = workflow.get_approval_history("test_strategy")
        
        # Should have Gate 3 approval (we didn't go through Gate 1 and 2 in this test)
        gate3_approvals = [h for h in history if h.gate == ApprovalGate.GATE_3_LIVE_ACTIVATION]
        assert len(gate3_approvals) == 1
        assert gate3_approvals[0].approved_by == "ceo"


class TestFullWorkflow:
    """Test complete workflow from PAPER to LIVE_ACTIVE"""
    
    def test_complete_promotion_workflow(self, workflow, tracker, lifecycle):
        """Test full workflow through all three gates"""
        # Register and transition to PAPER
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.PAPER)
        
        # Set up passing validation for Gate 1
        setup_passing_validation(tracker)
        
        # Gate 1: PAPER → VALIDATED
        success = workflow.approve_gate1(tracker, approved_by="analyst")
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.VALIDATED
        
        # Gate 2: Complete checklist and approve
        workflow.update_checklist(
            "test_strategy",
            strategy_code_reviewed=True,
            risk_parameters_verified=True,
            position_sizing_confirmed=True,
            emergency_procedures_tested=True,
            monitoring_alerts_configured=True,
            historical_performance_reviewed=True,
            market_conditions_assessed=True
        )
        
        success = workflow.approve_gate2("test_strategy", approved_by="manager")
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.LIVE_APPROVED
        
        # Gate 3: Final confirmation
        success = workflow.approve_gate3("test_strategy", approved_by="ceo")
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.LIVE_ACTIVE
        
        # Verify approval history
        history = workflow.get_approval_history("test_strategy")
        assert len(history) == 3
        assert history[0].gate == ApprovalGate.GATE_1_VALIDATION
        assert history[1].gate == ApprovalGate.GATE_2_LIVE_APPROVAL
        assert history[2].gate == ApprovalGate.GATE_3_LIVE_ACTIVATION


class TestRollback:
    """Test rollback functionality"""
    
    def test_rollback_from_validated(self, workflow, lifecycle):
        """Test rollback from VALIDATED to PAPER"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.VALIDATED)
        
        success = workflow.rollback_to_paper(
            strategy_name="test_strategy",
            reason="Issues found in review",
            approved_by="manager"
        )
        
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.PAPER
    
    def test_rollback_from_live_approved(self, workflow, lifecycle):
        """Test rollback from LIVE_APPROVED to PAPER"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.LIVE_APPROVED)
        
        success = workflow.rollback_to_paper(
            strategy_name="test_strategy",
            reason="Market conditions changed",
            approved_by="ceo"
        )
        
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.PAPER
    
    def test_rollback_from_live_active(self, workflow, lifecycle):
        """Test emergency rollback from LIVE_ACTIVE to PAPER"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.LIVE_ACTIVE)
        
        success = workflow.rollback_to_paper(
            strategy_name="test_strategy",
            reason="EMERGENCY: Critical bug found",
            approved_by="cto"
        )
        
        assert success
        assert lifecycle.get_state("test_strategy") == StrategyState.PAPER
    
    def test_cannot_rollback_from_paper(self, workflow, lifecycle):
        """Test cannot rollback if already in PAPER state"""
        lifecycle.register_strategy("test_strategy")
        lifecycle.transition("test_strategy", StrategyState.PAPER)
        
        success = workflow.rollback_to_paper(
            strategy_name="test_strategy",
            reason="Test rollback",
            approved_by="manager"
        )
        
        assert not success


class TestApprovalHistory:
    """Test approval history tracking"""
    
    def test_empty_history_for_new_strategy(self, workflow, lifecycle):
        """Test empty history for newly registered strategy"""
        lifecycle.register_strategy("test_strategy")
        
        history = workflow.get_approval_history("test_strategy")
        
        assert len(history) == 0
    
    def test_history_includes_all_approvals(self, workflow, tracker, lifecycle):
        """Test history includes all approval events"""
        # Set up and approve through Gate 1
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.PAPER)
        
        # Set up passing validation
        setup_passing_validation(tracker)
        
        workflow.approve_gate1(tracker, approved_by="analyst", notes="Gate 1 notes")
        
        # Approve through Gate 2
        workflow.update_checklist(
            "test_strategy",
            strategy_code_reviewed=True,
            risk_parameters_verified=True,
            position_sizing_confirmed=True,
            emergency_procedures_tested=True,
            monitoring_alerts_configured=True,
            historical_performance_reviewed=True,
            market_conditions_assessed=True
        )
        workflow.approve_gate2("test_strategy", approved_by="manager", notes="Gate 2 notes")
        
        # Approve through Gate 3
        workflow.approve_gate3("test_strategy", approved_by="ceo", notes="Gate 3 notes")
        
        # Check history
        history = workflow.get_approval_history("test_strategy")
        
        assert len(history) == 3
        assert all(isinstance(record, ApprovalRecord) for record in history)
        assert history[0].notes == "Gate 1 notes"
        assert history[1].notes == "Gate 2 notes"
        assert history[2].notes == "Gate 3 notes"
    
    def test_approval_record_includes_checklist(self, workflow, tracker, lifecycle):
        """Test approval record includes checklist for Gate 2"""
        lifecycle.register_strategy("test_strategy")
        manual_set_state(lifecycle, "test_strategy", StrategyState.PAPER)
        
        # Pass Gate 1
        setup_passing_validation(tracker)
        
        workflow.approve_gate1(tracker, approved_by="analyst")
        
        # Pass Gate 2 with checklist
        workflow.update_checklist(
            "test_strategy",
            strategy_code_reviewed=True,
            risk_parameters_verified=True,
            position_sizing_confirmed=True,
            emergency_procedures_tested=True,
            monitoring_alerts_configured=True,
            historical_performance_reviewed=True,
            market_conditions_assessed=True
        )
        workflow.approve_gate2("test_strategy", approved_by="manager")
        
        # Check Gate 2 approval has checklist
        history = workflow.get_approval_history("test_strategy")
        gate2_approval = [h for h in history if h.gate == ApprovalGate.GATE_2_LIVE_APPROVAL][0]
        
        assert gate2_approval.checklist is not None
        assert gate2_approval.checklist.is_complete()
