"""Browser Recovery - Stage 18: Computer Use Foundation.

Handles recovery from common browser automation failures.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.tools.browser_executor import (
    ActionResult,
    ActionType,
    BrowserAction,
    BrowserActionExecutor,
)
from app.tools.browser_observer import BrowserObserver
from app.tools.browser_planner import PlanStep
from app.tools.browser_state import BrowserSession


class RecoveryStrategy(Enum):
    """Types of recovery strategies."""
    DISMISS_DIALOG = "dismiss_dialog"
    CLOSE_MODAL = "close_modal"
    WAIT_AND_RETRY = "wait_and_retry"
    SCROLL_TO_FIND = "scroll_to_find"
    REFRESH_PAGE = "refresh_page"
    ALTERNATIVE_SELECTOR = "alternative_selector"
    GO_BACK = "go_back"
    RESTART_TASK = "restart_task"
    HUMAN_INTERVENTION = "human_intervention"


@dataclass
class RecoveryAction:
    """A recovery action to attempt."""
    strategy: RecoveryStrategy
    action: BrowserAction
    description: str
    max_attempts: int = 2
    priority: int = 0  # Higher = tried first
    conditions: list[str] = None  # Error patterns that trigger this recovery

    def matches(self, error: str) -> bool:
        """Check if this recovery matches the error."""
        if not self.conditions:
            return True
        error_lower = error.lower()
        return any(cond.lower() in error_lower for cond in self.conditions)


class BrowserRecovery:
    """Manages recovery from browser automation failures."""

    def __init__(self, session: BrowserSession, observer: BrowserObserver, executor: BrowserActionExecutor):
        self.session = session
        self.observer = observer
        self.executor = executor
        self.recovery_strategies: list[RecoveryAction] = []
        self._init_default_strategies()

    def _init_default_strategies(self):
        """Initialize default recovery strategies."""

        # 1. Cookie/Consent dialogs
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.DISMISS_DIALOG,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="button:has-text('Accept'), button:has-text('Allow'), button:has-text('Agree'), button:has-text('I agree'), [id*='accept'], [id*='consent'], [class*='accept'], [class*='consent'], [data-testid*='accept'], button[aria-label*='accept']",
            ),
            description="Dismiss cookie/consent dialog",
            max_attempts=2,
            priority=100,
            conditions=["cookie", "consent", "gdpr", "privacy policy", "accept cookies"]
        ))

        # 2. Modal/Overlay dialogs
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.CLOSE_MODAL,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="[role='dialog'] button:has-text('Close'), [role='dialog'] [aria-label='Close'], [role='dialog'] .close, .modal .close, .popup .close, .overlay .close, button[aria-label='Close'], .modal-close, .popup-close, [data-dismiss='modal']",
            ),
            description="Close modal/overlay dialog",
            max_attempts=2,
            priority=90,
            conditions=["modal", "popup", "overlay", "dialog", "lightbox"]
        ))

        # 3. Newsletter signup popups
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.CLOSE_MODAL,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="button:has-text('No thanks'), button:has-text('Not now'), button:has-text('Maybe later'), [aria-label='Dismiss'], .newsletter-close, .signup-close",
            ),
            description="Dismiss newsletter signup",
            max_attempts=1,
            priority=80,
            conditions=["newsletter", "signup", "subscribe", "email"]
        ))

        # 4. Wait and retry
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.WAIT_AND_RETRY,
            action=BrowserAction(
                action_type=ActionType.WAIT,
                timeout=3000,
            ),
            description="Wait for element to appear",
            max_attempts=3,
            priority=70,
            conditions=["timeout", "not found", "element not found", "waiting"]
        ))

        # 5. Scroll to find element
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.SCROLL_TO_FIND,
            action=BrowserAction(
                action_type=ActionType.SCROLL,
                direction="down",
                amount=500,
            ),
            description="Scroll down to reveal element",
            max_attempts=5,
            priority=60,
            conditions=["not found", "element not found", "not visible", "scroll"]
        ))

        # 6. Scroll up
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.SCROLL_TO_FIND,
            action=BrowserAction(
                action_type=ActionType.SCROLL,
                direction="up",
                amount=500,
            ),
            description="Scroll up to reveal element",
            max_attempts=3,
            priority=50,
            conditions=["not found", "element not found", "header", "navigation"]
        ))

        # 7. Alternative selectors (handled by planner)
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.ALTERNATIVE_SELECTOR,
            action=BrowserAction(
                action_type=ActionType.WAIT,
                timeout=1000,
            ),
            description="Try alternative selector (handled by planner)",
            max_attempts=1,
            priority=40,
            conditions=["not found", "selector", "no such element"]
        ))

        # 8. Refresh page
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.REFRESH_PAGE,
            action=BrowserAction(
                action_type=ActionType.REFRESH,
            ),
            description="Refresh page to recover from stale state",
            max_attempts=2,
            priority=30,
            conditions=["stale", "detached", "navigation", "timeout", "crash"]
        ))

        # 9. Go back
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.GO_BACK,
            action=BrowserAction(
                action_type=ActionType.GO_BACK,
            ),
            description="Go back to previous page",
            max_attempts=1,
            priority=20,
            conditions=["404", "not found", "error page", "dead end"]
        ))

        # 10. Human intervention (last resort)
        self.recovery_strategies.append(RecoveryAction(
            strategy=RecoveryStrategy.HUMAN_INTERVENTION,
            action=BrowserAction(
                action_type=ActionType.SCREENSHOT,
            ),
            description="Request human intervention",
            max_attempts=1,
            priority=1,
            conditions=[]
        ))

        # Sort by priority (highest first)
        self.recovery_strategies.sort(key=lambda x: -x.priority)

    def add_strategy(self, strategy: RecoveryAction):
        """Add a custom recovery strategy."""
        self.recovery_strategies.append(strategy)
        self.recovery_strategies.sort(key=lambda x: -x.priority)

    async def attempt_recovery(self, error: str, failed_step: PlanStep) -> list[ActionResult]:
        """Attempt recovery for a failed step."""
        results = []

        # Find matching strategies
        matching = [s for s in self.recovery_strategies if s.matches(error)]

        if not matching:
            # Try generic recovery
            matching = [s for s in self.recovery_strategies if not s.conditions]

        for strategy in matching:
            for attempt in range(strategy.max_attempts):
                try:
                    # Execute recovery action
                    result = await self.executor.execute(strategy.action)
                    results.append(result)

                    if result.success:
                        # Observe state after recovery
                        tab = self.session.get_active_tab()
                        if tab:
                            await self.observer.observe_tab(tab.tab_id)

                        # If recovery succeeded, return results
                        if strategy.strategy != RecoveryStrategy.HUMAN_INTERVENTION:
                            return results

                except Exception as e:
                    results.append(ActionResult(
                        success=False,
                        action=strategy.action,
                        error=f"Recovery failed: {str(e)}",
                        execution_time=0.0
                    ))

        return results

    def get_recovery_plan(self, error: str) -> list[RecoveryAction]:
        """Get the ordered recovery plan for an error."""
        matching = [s for s in self.recovery_strategies if s.matches(error)]
        if not matching:
            matching = [s for s in self.recovery_strategies if not s.conditions]
        return matching


async def recover_from_error(
    session: BrowserSession,
    observer: BrowserObserver,
    executor: BrowserActionExecutor,
    error: str,
    failed_step: PlanStep
) -> list[ActionResult]:
    """Convenience function to attempt recovery."""
    recovery = BrowserRecovery(session, observer, executor)
    return await recovery.attempt_recovery(error, failed_step)


# Common recovery patterns for specific sites
SITE_SPECIFIC_RECOVERIES = {
    "google.com": [
        RecoveryAction(
            strategy=RecoveryStrategy.DISMISS_DIALOG,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="#L2AGLb, .QS5gu, [aria-label='Accept all']",
            ),
            description="Accept Google cookies",
            priority=100,
            conditions=["cookie", "consent"]
        ),
    ],
    "youtube.com": [
        RecoveryAction(
            strategy=RecoveryStrategy.DISMISS_DIALOG,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="button:has-text('Accept all'), ytd-button-renderer:has-text('Accept')",
            ),
            description="Accept YouTube cookies",
            priority=100,
            conditions=["cookie", "consent"]
        ),
    ],
    "github.com": [
        RecoveryAction(
            strategy=RecoveryStrategy.CLOSE_MODAL,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="[aria-label='Close'], .modal-close, .flash-close",
            ),
            description="Close GitHub modals",
            priority=90,
            conditions=["modal", "flash"]
        ),
    ],
    "amazon.com": [
        RecoveryAction(
            strategy=RecoveryStrategy.DISMISS_DIALOG,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="#sp-cc-accept, #sp-cc-rejectall-link, [data-action-type='DISMISS']",
            ),
            description="Accept Amazon cookies",
            priority=100,
            conditions=["cookie", "consent"]
        ),
    ],
    "linkedin.com": [
        RecoveryAction(
            strategy=RecoveryStrategy.CLOSE_MODAL,
            action=BrowserAction(
                action_type=ActionType.CLICK,
                selector="[aria-label='Dismiss'], .msg-overlay-bubble-header__control, .artdeco-modal__dismiss",
            ),
            description="Close LinkedIn modals",
            priority=90,
            conditions=["modal", "overlay", "signup"]
        ),
    ],
}


def get_site_recoveries(url: str) -> list[RecoveryAction]:
    """Get site-specific recovery strategies."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    for key, recoveries in SITE_SPECIFIC_RECOVERIES.items():
        if key in domain:
            return recoveries
    return []
