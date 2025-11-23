"""
Strategy Promotion Workflow

Implements multi-gate approval process for promoting strategies from paper
trading to live trading. Enforces validation criteria, manual approvals,
and maintains complete audit trail.

Workflow Gates:
    Gate 1: PAPER → VALIDATED (automated validation + optional manual review)
    Gate 2: VALIDATED → LIVE_APPROVED (mandatory manual approval + checklist)
    Gate 3: LIVE_APPROVED → LIVE_ACTIVE (final confirmation)
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from enum import Enum

from strategy.lifecycle import StrategyState, StrategyLifecycle
from strategy.validation import ValidationEnforcer, ValidationReport
from strategy.metrics_tracker import PaperMetricsTracker

logger = logging.getLogger(__name__)


class ApprovalGate(Enum):
    """Approval gates in the promotion workflow"""
    
    GATE_1_VALIDATION = "gate_1_validation"     # PAPER → VALIDATED
    GATE_2_LIVE_APPROVAL = "gate_2_live_approval" # VALIDATED → LIVE_APPROVED
    GATE_3_LIVE_ACTIVATION = "gate_3_live_activation" # LIVE_APPROVED → LIVE_ACTIVE
    
    def __str__(self):
        return self.value


@dataclass
class ApprovalChecklist:
    """Checklist for manual approval (Gate 2)"""
    
    strategy_code_reviewed: bool = False
    risk_parameters_verified: bool = False
    position_sizing_confirmed: bool = False
    emergency_procedures_tested: bool = False
    monitoring_alerts_configured: bool = False
    historical_performance_reviewed: bool = False
    market_conditions_assessed: bool = False
    
    def is_complete(self) -> bool:
        """Check if all items are checked"""
        return all([
            self.strategy_code_reviewed,
            self.risk_parameters_verified,
            self.position_sizing_confirmed,
            self.emergency_procedures_tested,
            self.monitoring_alerts_configured,
            self.historical_performance_reviewed,
            self.market_conditions_assessed
        ])
    
    def get_incomplete_items(self) -> List[str]:
        """Get list of incomplete checklist items"""
        incomplete = []
        if not self.strategy_code_reviewed:
            incomplete.append("strategy_code_reviewed")
        if not self.risk_parameters_verified:
            incomplete.append("risk_parameters_verified")
        if not self.position_sizing_confirmed:
            incomplete.append("position_sizing_confirmed")
        if not self.emergency_procedures_tested:
            incomplete.append("emergency_procedures_tested")
        if not self.monitoring_alerts_configured:
            incomplete.append("monitoring_alerts_configured")
        if not self.historical_performance_reviewed:
            incomplete.append("historical_performance_reviewed")
        if not self.market_conditions_assessed:
            incomplete.append("market_conditions_assessed")
        return incomplete
    
    def to_dict(self) -> Dict[str, bool]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, bool]) -> 'ApprovalChecklist':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class ApprovalRecord:
    """Record of a single approval event"""
    
    strategy_name: str
    gate: ApprovalGate
    approved_by: str
    approved_at: datetime
    notes: str = ""
    checklist: Optional[ApprovalChecklist] = None
    validation_report: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = {
            'strategy_name': self.strategy_name,
            'gate': self.gate.value,
            'approved_by': self.approved_by,
            'approved_at': self.approved_at.isoformat(),
            'notes': self.notes
        }
        
        if self.checklist:
            data['checklist'] = self.checklist.to_dict()
        
        if self.validation_report:
            data['validation_report'] = self.validation_report
        
        return data


class PromotionWorkflow:
    """
    Manages strategy promotion workflow with multi-gate approvals.
    
    Provides:
    - Automated validation checks (Gate 1)
    - Manual approval process with checklist (Gate 2)
    - Final confirmation (Gate 3)
    - Complete approval trail
    - Rollback capability
    """
    
    def __init__(
        self, 
        db_path: str | Path,
        enforcer: Optional[ValidationEnforcer] = None
    ):
        """
        Initialize promotion workflow.
        
        Args:
            db_path: Path to SQLite database
            enforcer: ValidationEnforcer instance (creates default if None)
        """
        self.db_path = Path(db_path)
        self.lifecycle = StrategyLifecycle(db_path)
        self.enforcer = enforcer or ValidationEnforcer()
        
        # Create tables
        self._init_database()
        
        logger.info("PromotionWorkflow initialized")
    
    def _init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Approval history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                gate TEXT NOT NULL,
                approved_by TEXT NOT NULL,
                approved_at TEXT NOT NULL,
                notes TEXT,
                checklist_json TEXT,
                validation_report_json TEXT,
                FOREIGN KEY (strategy_name) REFERENCES strategy_state(strategy_name)
            )
        """)
        
        # Checklist state table (tracks current checklist progress)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS checklist_state (
                strategy_name TEXT PRIMARY KEY,
                strategy_code_reviewed INTEGER DEFAULT 0,
                risk_parameters_verified INTEGER DEFAULT 0,
                position_sizing_confirmed INTEGER DEFAULT 0,
                emergency_procedures_tested INTEGER DEFAULT 0,
                monitoring_alerts_configured INTEGER DEFAULT 0,
                historical_performance_reviewed INTEGER DEFAULT 0,
                market_conditions_assessed INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_name) REFERENCES strategy_state(strategy_name)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def can_pass_gate1(
        self, 
        tracker: PaperMetricsTracker,
        require_manual: bool = False
    ) -> tuple[bool, str, Optional[ValidationReport]]:
        """
        Check if strategy can pass Gate 1 (PAPER → VALIDATED).
        
        Args:
            tracker: PaperMetricsTracker for the strategy
            require_manual: If True, requires manual approval even if automated checks pass
        
        Returns:
            (can_pass, reason, validation_report)
        """
        # Run automated validation
        report = self.enforcer.get_validation_report(tracker)
        
        if not report.overall_passed:
            failed = self.enforcer.get_failed_criteria(tracker)
            reason = f"Validation failed: {', '.join(failed)}"
            return False, reason, report
        
        if require_manual:
            return False, "Manual review required", report
        
        return True, "Automated validation passed", report
    
    def can_pass_gate2(
        self, 
        strategy_name: str
    ) -> tuple[bool, str, Optional[ApprovalChecklist]]:
        """
        Check if strategy can pass Gate 2 (VALIDATED → LIVE_APPROVED).
        
        Args:
            strategy_name: Name of the strategy
        
        Returns:
            (can_pass, reason, checklist)
        """
        # Get current checklist state
        checklist = self.get_checklist(strategy_name)
        
        if not checklist.is_complete():
            incomplete = checklist.get_incomplete_items()
            reason = f"Checklist incomplete: {', '.join(incomplete)}"
            return False, reason, checklist
        
        return True, "Checklist complete", checklist
    
    def can_pass_gate3(
        self, 
        strategy_name: str
    ) -> tuple[bool, str]:
        """
        Check if strategy can pass Gate 3 (LIVE_APPROVED → LIVE_ACTIVE).
        
        This is a final confirmation gate - always requires explicit approval.
        
        Args:
            strategy_name: Name of the strategy
        
        Returns:
            (can_pass, reason)
        """
        # Verify strategy is in LIVE_APPROVED state
        state = self.lifecycle.get_state(strategy_name)
        
        if state != StrategyState.LIVE_APPROVED:
            return False, f"Strategy must be in LIVE_APPROVED state (currently {state})"
        
        return True, "Ready for live activation"
    
    def approve_gate1(
        self,
        tracker: PaperMetricsTracker,
        approved_by: str = "automated",
        notes: str = "",
        require_manual: bool = False
    ) -> bool:
        """
        Approve Gate 1 (PAPER → VALIDATED).
        
        Args:
            tracker: PaperMetricsTracker for the strategy
            approved_by: Who approved the transition
            notes: Additional notes
            require_manual: If True, requires manual approval
        
        Returns:
            True if approved and transitioned
        """
        strategy_name = tracker.strategy_name
        
        can_pass, reason, report = self.can_pass_gate1(tracker, require_manual)
        
        if not can_pass:
            logger.warning(f"Gate 1 approval denied for '{strategy_name}': {reason}")
            return False
        
        # Transition to VALIDATED - direct database update since ValidationEnforcer already validated
        # We don't use lifecycle.transition() here because it re-validates with strict criteria
        current_state = self.lifecycle.get_state(strategy_name)
        now = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # Update strategy state
            cursor.execute("""
                UPDATE strategy_state 
                SET current_state = ?, previous_state = ?, updated_at = ?
                WHERE strategy_name = ?
            """, (StrategyState.VALIDATED.value, current_state.value, now, strategy_name))
            
            # Record transition history
            cursor.execute("""
                INSERT INTO state_transitions (
                    strategy_name, from_state, to_state, timestamp, reason, approved_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (strategy_name, current_state.value, StrategyState.VALIDATED.value, now, f"Gate 1: {reason}", approved_by))
            
            conn.commit()
            logger.info(f"Strategy '{strategy_name}' transitioned: {current_state} → {StrategyState.VALIDATED}")
        finally:
            conn.close()
        
        # Record approval
        self._record_approval(
            strategy_name=strategy_name,
            gate=ApprovalGate.GATE_1_VALIDATION,
            approved_by=approved_by,
            notes=notes,
            validation_report=report.to_dict() if report else None
        )
        
        logger.info(f"Gate 1 approved for '{strategy_name}' by {approved_by}")
        return True
    
    def approve_gate2(
        self,
        strategy_name: str,
        approved_by: str,
        notes: str = ""
    ) -> bool:
        """
        Approve Gate 2 (VALIDATED → LIVE_APPROVED).
        
        Requires completed checklist.
        
        Args:
            strategy_name: Name of the strategy
            approved_by: Who approved the transition
            notes: Additional notes
        
        Returns:
            True if approved and transitioned
        """
        can_pass, reason, checklist = self.can_pass_gate2(strategy_name)
        
        if not can_pass:
            logger.warning(f"Gate 2 approval denied for '{strategy_name}': {reason}")
            return False
        
        # Transition to LIVE_APPROVED
        success = self.lifecycle.transition(
            strategy_name=strategy_name,
            to_state=StrategyState.LIVE_APPROVED,
            reason=f"Gate 2: Manual approval completed",
            approved_by=approved_by
        )
        
        if not success:
            logger.error(f"Failed to transition '{strategy_name}' to LIVE_APPROVED")
            return False
        
        # Record approval
        self._record_approval(
            strategy_name=strategy_name,
            gate=ApprovalGate.GATE_2_LIVE_APPROVAL,
            approved_by=approved_by,
            notes=notes,
            checklist=checklist
        )
        
        logger.info(f"Gate 2 approved for '{strategy_name}' by {approved_by}")
        return True
    
    def approve_gate3(
        self,
        strategy_name: str,
        approved_by: str,
        notes: str = ""
    ) -> bool:
        """
        Approve Gate 3 (LIVE_APPROVED → LIVE_ACTIVE).
        
        Final confirmation for live trading activation.
        
        Args:
            strategy_name: Name of the strategy
            approved_by: Who approved the transition
            notes: Additional notes
        
        Returns:
            True if approved and transitioned
        """
        can_pass, reason = self.can_pass_gate3(strategy_name)
        
        if not can_pass:
            logger.warning(f"Gate 3 approval denied for '{strategy_name}': {reason}")
            return False
        
        # Transition to LIVE_ACTIVE
        success = self.lifecycle.transition(
            strategy_name=strategy_name,
            to_state=StrategyState.LIVE_ACTIVE,
            reason=f"Gate 3: Live activation confirmed",
            approved_by=approved_by
        )
        
        if not success:
            logger.error(f"Failed to transition '{strategy_name}' to LIVE_ACTIVE")
            return False
        
        # Record approval
        self._record_approval(
            strategy_name=strategy_name,
            gate=ApprovalGate.GATE_3_LIVE_ACTIVATION,
            approved_by=approved_by,
            notes=notes
        )
        
        logger.info(f"Gate 3 approved for '{strategy_name}' by {approved_by} - NOW LIVE")
        return True
    
    def update_checklist(
        self,
        strategy_name: str,
        **items
    ) -> bool:
        """
        Update checklist items for Gate 2 approval.
        
        Args:
            strategy_name: Name of the strategy
            **items: Checklist items to update (e.g., strategy_code_reviewed=True)
        
        Returns:
            True if updated successfully
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Get current checklist or create new one
            cursor.execute("""
                SELECT * FROM checklist_state
                WHERE strategy_name = ?
            """, (strategy_name,))
            
            existing = cursor.fetchone()
            
            if existing is None:
                # Create new checklist
                cursor.execute("""
                    INSERT INTO checklist_state (
                        strategy_name, updated_at
                    ) VALUES (?, ?)
                """, (strategy_name, datetime.now().isoformat()))
            
            # Update items
            for key, value in items.items():
                if key in ApprovalChecklist.__dataclass_fields__:
                    cursor.execute(f"""
                        UPDATE checklist_state
                        SET {key} = ?, updated_at = ?
                        WHERE strategy_name = ?
                    """, (1 if value else 0, datetime.now().isoformat(), strategy_name))
            
            conn.commit()
            logger.info(f"Checklist updated for '{strategy_name}': {items}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update checklist: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_checklist(self, strategy_name: str) -> ApprovalChecklist:
        """
        Get current checklist state for a strategy.
        
        Args:
            strategy_name: Name of the strategy
        
        Returns:
            ApprovalChecklist (empty if not found)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT strategy_code_reviewed, risk_parameters_verified,
                   position_sizing_confirmed, emergency_procedures_tested,
                   monitoring_alerts_configured, historical_performance_reviewed,
                   market_conditions_assessed
            FROM checklist_state
            WHERE strategy_name = ?
        """, (strategy_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row is None:
            return ApprovalChecklist()
        
        return ApprovalChecklist(
            strategy_code_reviewed=bool(row[0]),
            risk_parameters_verified=bool(row[1]),
            position_sizing_confirmed=bool(row[2]),
            emergency_procedures_tested=bool(row[3]),
            monitoring_alerts_configured=bool(row[4]),
            historical_performance_reviewed=bool(row[5]),
            market_conditions_assessed=bool(row[6])
        )
    
    def get_approval_history(self, strategy_name: str) -> List[ApprovalRecord]:
        """
        Get approval history for a strategy.
        
        Args:
            strategy_name: Name of the strategy
        
        Returns:
            List of approval records
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT gate, approved_by, approved_at, notes, 
                   checklist_json, validation_report_json
            FROM approval_history
            WHERE strategy_name = ?
            ORDER BY approved_at ASC
        """, (strategy_name,))
        
        records = []
        for row in cursor.fetchall():
            import json
            
            gate = ApprovalGate(row[0])
            approved_by = row[1]
            approved_at = datetime.fromisoformat(row[2])
            notes = row[3] or ""
            checklist_json = row[4]
            validation_report_json = row[5]
            
            checklist = None
            if checklist_json:
                checklist = ApprovalChecklist.from_dict(json.loads(checklist_json))
            
            validation_report = None
            if validation_report_json:
                validation_report = json.loads(validation_report_json)
            
            records.append(ApprovalRecord(
                strategy_name=strategy_name,
                gate=gate,
                approved_by=approved_by,
                approved_at=approved_at,
                notes=notes,
                checklist=checklist,
                validation_report=validation_report
            ))
        
        conn.close()
        return records
    
    def rollback_to_paper(
        self,
        strategy_name: str,
        reason: str,
        approved_by: str
    ) -> bool:
        """
        Rollback strategy from any state back to PAPER.
        
        Used for emergency situations or if issues found after approval.
        
        Args:
            strategy_name: Name of the strategy
            reason: Reason for rollback
            approved_by: Who authorized the rollback
        
        Returns:
            True if rollback successful
        """
        current_state = self.lifecycle.get_state(strategy_name)
        
        # Don't rollback if already in PAPER, PAUSED, or RETIRED
        if current_state in [StrategyState.PAPER, StrategyState.PAUSED, StrategyState.RETIRED]:
            logger.warning(f"Cannot rollback '{strategy_name}' from {current_state}")
            return False
        
        # Direct database update for rollback - lifecycle.transition() doesn't allow backward transitions
        now = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # Update strategy state
            cursor.execute("""
                UPDATE strategy_state 
                SET current_state = ?, previous_state = ?, updated_at = ?
                WHERE strategy_name = ?
            """, (StrategyState.PAPER.value, current_state.value, now, strategy_name))
            
            # Record transition history
            cursor.execute("""
                INSERT INTO state_transitions (
                    strategy_name, from_state, to_state, timestamp, reason, approved_by
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (strategy_name, current_state.value, StrategyState.PAPER.value, now, f"ROLLBACK: {reason}", approved_by))
            
            conn.commit()
            logger.warning(f"Strategy '{strategy_name}' rolled back to PAPER by {approved_by}: {reason}")
            return True
        finally:
            conn.close()
    
    def _record_approval(
        self,
        strategy_name: str,
        gate: ApprovalGate,
        approved_by: str,
        notes: str = "",
        checklist: Optional[ApprovalChecklist] = None,
        validation_report: Optional[Dict[str, Any]] = None
    ):
        """Record approval in database"""
        import json
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        checklist_json = None
        if checklist:
            checklist_json = json.dumps(checklist.to_dict())
        
        validation_report_json = None
        if validation_report:
            validation_report_json = json.dumps(validation_report)
        
        cursor.execute("""
            INSERT INTO approval_history (
                strategy_name, gate, approved_by, approved_at, notes,
                checklist_json, validation_report_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            strategy_name,
            gate.value,
            approved_by,
            datetime.now().isoformat(),
            notes,
            checklist_json,
            validation_report_json
        ))
        
        conn.commit()
        conn.close()
