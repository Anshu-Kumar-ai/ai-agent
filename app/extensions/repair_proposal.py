"""
Repair Proposal Generator - Stage 32 Phase 10
Integrates failure analysis with the existing ChangeProposal system for test-guided repair.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import uuid
import os

from app.extensions.failure_analyzer import FailureAnalysisResult, ConfidenceLevel
from app.extensions.change_proposal import (
    ChangeProposal, FileChange, ChangeType, ProposalStatus, RiskLevel,
    ValidationStep, validate_workspace_path, compute_file_hash,
    read_file_content, write_file_atomic, backup_file, is_command_allowed,
    VALIDATION_COMMAND_ALLOWLIST
)
from app.extensions.validation_tools import ValidationResult, ValidationStatus


class RepairRiskLevel(Enum):
    """Risk levels specific to repair proposals."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RepairProposalRequest:
    """Request for generating a repair proposal."""
    request_id: str
    task_id: str
    workspace_root: str
    failure_analysis: FailureAnalysisResult
    validation_result: ValidationResult
    target_files: List[str]  # Files to potentially modify
    max_changes: int = 5  # Maximum number of files to modify in a single repair
    max_content_size: int = 1000  # Maximum size of content changes
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class RepairProposal:
    """A repair proposal ready for submission to the ChangeManager."""
    proposal_id: str
    request_id: str
    task_id: str
    workspace_root: str
    changes: List[FileChange]
    rationale: str
    risk_level: RepairRiskLevel
    validation_plan: List[ValidationStep] = field(default_factory=list)
    observed_failure: Optional[ValidationResult] = None
    failure_analysis: Optional[FailureAnalysisResult] = None
    expected_success_criteria: List[str] = field(default_factory=list)
    rollback_strategy: str = "standard"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = self.created_at

    def compute_proposal_hash(self) -> str:
        """Compute a deterministic hash of the proposal content (excluding mutable fields)."""
        import json
        # Create a stable representation
        data = {
            "proposal_id": self.proposal_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "workspace_root": self.workspace_root,
            "changes": [
                {
                    "target_path": c.target_path,
                    "change_type": c.change_type.value,
                    "content": c.content,
                    "expected_pre_hash": c.expected_pre_hash,
                    "expected_post_hash": c.expected_post_hash,
                }
                for c in self.changes
            ],
            "rationale": self.rationale,
            "risk_level": self.risk_level.value,
            "validation_plan": [
                {
                    "name": v.name,
                    "command": v.command,
                    "description": v.description,
                    "required": v.required,
                    "timeout_seconds": v.timeout_seconds,
                    "working_directory": v.working_directory,
                }
                for v in self.validation_plan
            ],
            "observed_failure": {
                "validation_id": self.observed_failure.validation_id if self.observed_failure else None,
                "status": self.observed_failure.status.value if self.observed_failure else None,
            } if self.observed_failure else None,
            "expected_success_criteria": self.expected_success_criteria,
            "rollback_strategy": self.rollback_strategy,
        }
        # Sort keys for deterministic hashing
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode('utf-8')).hexdigest()

    def get_target_paths(self) -> List[str]:
        """Get all target file paths (relative to workspace)."""
        return [c.target_path for c in self.changes]

    def is_approved(self) -> bool:
        """Check if proposal is approved and approval is still valid.
        Note: This mirrors the ChangeProposal.is_approved() method but we don't have approval fields here.
        In practice, this would be checked by the ChangeManager when the proposal is submitted.
        """
        # RepairProposal doesn't have approval fields - approval is handled by ChangeManager
        # This method exists for interface consistency but always returns False
        # Actual approval checking happens in ChangeManager.request_approval()
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "proposal_id": self.proposal_id,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "workspace_root": self.workspace_root,
            "changes": [
                {
                    "target_path": c.target_path,
                    "change_type": c.change_type.value,
                    "content": c.content,
                    "expected_pre_hash": c.expected_pre_hash,
                    "expected_post_hash": c.expected_post_hash,
                }
                for c in self.changes
            ],
            "rationale": self.rationale,
            "risk_level": self.risk_level.value,
            "validation_plan": [
                {
                    "name": v.name,
                    "command": v.command,
                    "description": v.description,
                    "required": v.required,
                    "timeout_seconds": v.timeout_seconds,
                    "working_directory": v.working_directory,
                }
                for v in self.validation_plan
            ],
            "observed_failure": {
                "validation_id": self.observed_failure.validation_id if self.observed_failure else None,
                "task_id": self.observed_failure.task_id if self.observed_failure else None,
                "status": self.observed_failure.status.value if self.observed_failure else None,
                "exit_code": self.observed_failure.exit_code,
                "duration_seconds": self.observed_failure.duration_seconds,
                "stdout": self.observed_failure.stdout,
                "stderr": self.observed_failure.stderr,
                "structured_failures": self.observed_failure.structured_failures,
                "test_counts": self.observed_failure.test_counts,
                "truncated": self.observed_failure.truncated,
                "sanitized_diagnostics": self.observed_failure.sanitized_diagnostics
            } if self.observed_failure else None,
            "failure_analysis": {
                "analysis_id": self.failure_analysis.analysis_id if self.failure_analysis else None,
                "task_id": self.failure_analysis.task_id if self.failure_analysis else None,
                "failure_summary": self.failure_analysis.failure_summary,
                "evidence": self.failure_analysis.evidence,
                "affected_files": self.failure_analysis.affected_files,
                "likely_cause": self.failure_analysis.likely_cause,
                "hypotheses": self.failure_analysis.hypotheses,
                "confidence_level": self.failure_analysis.confidence_level.value if self.failure_analysis else None,
                "suggested_next_step": self.failure_analysis.suggested_next_step,
                "code_change_justified": self.failure_analysis.code_change_justified
            } if self.failure_analysis else None,
            "expected_success_criteria": self.expected_success_criteria,
            "rollback_strategy": self.rollback_strategy,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RepairProposal':
        """Create from dictionary."""
        changes = [
            FileChange(
                target_path=c["target_path"],
                change_type=ChangeType(c["change_type"]),
                content=c["content"],
                expected_pre_hash=c.get("expected_pre_hash"),
                expected_post_hash=c.get("expected_post_hash"),
            )
            for c in data.get("changes", [])
        ]
        
        validation_plan = [
            ValidationStep(
                name=v["name"],
                command=v["command"],
                description=v["description"],
                required=v.get("required", True),
                timeout_seconds=v.get("timeout_seconds", 30),
                working_directory=v.get("working_directory")
            )
            for v in data.get("validation_plan", [])
        ]
        
        observed_failure = None
        if data.get("observed_failure"):
            obs_data = data["observed_failure"]
            observed_failure = ValidationResult(
                validation_id=obs_data.get("validation_id"),
                task_id=obs_data.get("task_id"),
                status=ValidationStatus(obs_data.get("status")) if obs_data.get("status") else ValidationStatus.ERROR,
                exit_code=obs_data.get("exit_code"),
                duration_seconds=obs_data.get("duration_seconds", 0.0),
                stdout=obs_data.get("stdout", ""),
                stderr=obs_data.get("stderr", ""),
                structured_failures=obs_data.get("structured_failures", []),
                test_counts=obs_data.get("test_counts", {}),
                truncated=obs_data.get("truncated", False),
                sanitized_diagnostics=obs_data.get("sanitized_diagnostics", "")
            )
        
        failure_analysis = None
        if data.get("failure_analysis"):
            fa_data = data["failure_analysis"]
            failure_analysis = FailureAnalysisResult(
                analysis_id=fa_data.get("analysis_id"),
                task_id=fa_data.get("task_id"),
                evidence=fa_data.get("evidence", []),
                affected_files=fa_data.get("affected_files", []),
                likely_cause=fa_data.get("likely_cause"),
                hypotheses=fa_data.get("hypotheses", []),
                confidence_level=ConfidenceLevel(fa_data.get("confidence_level")) if fa_data.get("confidence_level") else ConfidenceLevel.LOW,
                suggested_next_step=fa_data.get("suggested_next_step"),
                code_change_justified=fa_data.get("code_change_justified", False)
            )
        
        return cls(
            proposal_id=data["proposal_id"],
            request_id=data["request_id"],
            workspace_root=data["workspace_root"],
            changes=changes,
            rationale=data["rationale"],
            risk_level=RepairRiskLevel(data["risk_level"]),
            validation_plan=validation_plan,
            observed_failure=observed_failure,
            failure_analysis=failure_analysis,
            expected_success_criteria=data.get("expected_success_criteria", []),
            rollback_strategy=data.get("rollback_strategy", "standard"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        )


class RepairProposalGenerator:
    """
    Generates repair proposals based on failure analysis results.
    Integrates with the existing ChangeProposal system.
    """

    def __init__(self):
        pass

    def generate_repair_proposal(self, request: RepairProposalRequest) -> RepairProposal:
        """Generate a repair proposal based on failure analysis."""
        # Generate a unique proposal ID
        proposal_id = str(uuid.uuid4())[:8]
        
        # Determine what changes to make based on failure analysis
        changes = self._determine_changes(request)
        
        # Generate rationale
        rationale = self._generate_rationale(request)
        
        # Determine risk level
        risk_level = self._determine_risk_level(request, changes)
        
        # Create validation plan
        validation_plan = self._create_validation_plan(request)
        
        # Create the repair proposal
        proposal = RepairProposal(
            proposal_id=proposal_id,
            request_id=request.request_id,
            task_id=request.task_id,
            workspace_root=request.workspace_root,
            changes=changes,
            rationale=rationale,
            risk_level=risk_level,
            validation_plan=validation_plan,
            observed_failure=request.validation_result,
            failure_analysis=request.failure_analysis,
            expected_success_criteria=self._generate_success_criteria(request),
            rollback_strategy="standard"
        )
        
        return proposal

    def _determine_changes(self, request: RepairProposalRequest) -> List[FileChange]:
        """Determine what file changes to make based on failure analysis."""
        changes = []
        
        # If we don't have a justified code change, return empty changes
        if not request.failure_analysis.code_change_justified:
            return changes
        
        # Get the likely cause and suggested next step
        likely_cause = request.failure_analysis.likely_cause or ""
        suggested_next = request.failure_analysis.suggested_next_step or ""
        
        # For now, we'll create a simple placeholder change that demonstrates the mechanism
        # In a full implementation, this would involve sophisticated code analysis and generation
        
        # Look at affected files and see if we can make a simple fix
        for file_path in request.target_files[:request.max_changes]:  # Limit number of files
            full_path = os.path.join(request.workspace_root, file_path)
            
            # Check if file exists and is readable
            if os.path.exists(full_path) and os.path.isfile(full_path):
                try:
                    # Read the file content
                    with open(full_path, 'r', encoding='utf-8') as f:
                        original_content = f.read()
                    
                    # Bound the content size to prevent excessive processing
                    if len(original_content) > request.max_content_size * 10:  # Allow 10x for processing
                        continue  # Skip overly large files
                    
                    # For demonstration purposes, we'll create a simple fix
                    # In reality, this would involve AST parsing, pattern matching, etc.
                    
                    # Example: If the failure analysis suggests a syntax error like missing colon
                    if "missing colon" in likely_cause.lower() or "invalid syntax" in likely_cause.lower():
                        # Try to find common syntax issues and fix them
                        fixed_content = self._attempt_syntax_fix(original_content, likely_cause)
                        if fixed_content != original_content:
                            # Create the file change
                            expected_pre_hash = compute_file_hash(full_path)
                            file_change = FileChange(
                                target_path=file_path,
                                change_type=ChangeType.MODIFY,
                                content=fixed_content,
                                expected_pre_hash=expected_pre_hash
                            )
                            changes.append(file_change)
                            # Only make one change for demonstration
                            break
                    
                    # Example: If it's an assertion error, we might adjust the assertion
                    elif "assertion" in likely_cause.lower():
                        # For demonstration, we'll just note that we identified the issue
                        # In a real implementation, we would modify the assertion or the code it tests
                        pass
                        
                except (UnicodeDecodeError, OSError):
                    # Skip files we can't read as text
                    continue
        
        return changes

    def _attempt_syntax_fix(self, content: str, likely_cause: str) -> str:
        """Attempt to fix common syntax issues (demonstration implementation)."""
        lines = content.split('\n')
        fixed_lines = []
        
        # Simple heuristic: if we see lines that might be missing colons
        for line in lines:
            stripped = line.strip()
            # Look for common Python constructs that should end with :
            if (stripped.startswith(('if ', 'elif ', 'else', 'for ', 'while ', 'def ', 'class ', 'try ', 'except ', 'finally ', 'with ')) 
                and not stripped.endswith(':') 
                and not stripped.endswith('\\')  # Not a line continuation
                and ':' not in stripped.split('#')[0] if '#' in stripped else stripped):  # Not already containing a colon in code part
                # Add colon if it looks like it's missing
                fixed_lines.append(line + ':')
            else:
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)

    def _generate_rationale(self, request: RepairProposalRequest) -> str:
        """Generate a human-readable rationale for the repair."""
        failure_summary = request.failure_analysis.failure_summary
        likely_cause = request.failure_analysis.likely_cause or "unspecified issue"
        confidence = request.failure_analysis.confidence_level.value
        
        rationale = f"Automated repair proposal based on failure analysis. "
        rationale += f"Failure: {failure_summary}. "
        rationale += f"Likely cause: {likely_cause}. "
        rationale += f"Confidence: {confidence}. "
        
        if request.failure_analysis.code_change_justified:
            rationale += "Code change is justified based on analysis."
        else:
            rationale += "No code change justified - issue may be environmental or require manual intervention."
        
        return rationale

    def _determine_risk_level(self, request: RepairProposalRequest, changes: List[FileChange]) -> RepairRiskLevel:
        """Determine the risk level of the repair proposal."""
        if not changes:
            return RepairRiskLevel.LOW  # No changes = low risk
        
        # Base risk on confidence and justification
        confidence = request.failure_analysis.confidence_level
        justified = request.failure_analysis.code_change_justified
        
        if confidence == ConfidenceLevel.VERY_HIGH and justified:
            return RepairRiskLevel.LOW
        elif confidence == ConfidenceLevel.HIGH and justified:
            return RepairRiskLevel.LOW
        elif confidence == ConfidenceLevel.MEDIUM and justified:
            return RepairRiskLevel.MEDIUM
        else:
            return RepairRiskLevel.HIGH  # Low confidence or not justified = higher risk

    def _create_validation_plan(self, request: RepairProposalRequest) -> List[ValidationStep]:
        """Create a validation plan for the repair proposal."""
        validation_steps = []
        
        # Add the original validation command if it was a test
        if request.validation_result.status in [ValidationStatus.PASSED, ValidationStatus.FAILED]:
            # We would ideally extract the original command from the validation request
            # For now, we'll add a generic syntax check and the original test if we can infer it
            
            # Add Python syntax check as a safe first step
            validation_steps.append(ValidationStep(
                name="python syntax check",
                command="python -m py_compile",
                description="Check Python syntax of modified files",
                required=True,
                timeout_seconds=10
            ))
            
            # If we know what test failed, we could add it back
            # For demonstration, we'll add a generic test command if the original looked like a test
            if "test" in request.validation_result.stdout.lower() or "test" in request.validation_result.stderr.lower():
                validation_steps.append(ValidationStep(
                    name="original test validation",
                    command="python -m pytest",  # This would be more specific in a real implementation
                    description="Run the test that originally failed",
                    required=True,
                    timeout_seconds=30
                ))
        
        # Always add a syntax check as a safety measure
        if not any(step.name == "python syntax check" for step in validation_steps):
            validation_steps.insert(0, ValidationStep(
                name="python syntax check",
                command="python -m py_compile",
                description="Check Python syntax of modified files",
                required=True,
                timeout_seconds=10
            ))
        
        return validation_steps

    def _generate_success_criteria(self, request: RepairProposalRequest) -> List[str]:
        """Generate expected success criteria for the repair."""
        criteria = []
        
        # The primary success criterion is that the original validation should pass
        if request.validation_result.status == ValidationStatus.FAILED:
            criteria.append(f"Validation should pass (originally failed with status: {request.validation_result.status.value})")
        elif request.validation_result.status == ValidationStatus.PASSED:
            criteria.append("Validation should continue to pass (regression check)")
        
        # Add specific criteria based on failure type
        if request.failure_analysis.likely_cause:
            criteria.append(f"Issue described in likely cause should be resolved: {request.failure_analysis.likely_cause}")
        
        # Add that no new failures should be introduced
        criteria.append("No new test failures or validation errors should be introduced")
        
        return criteria


def create_repair_proposal_generator() -> RepairProposalGenerator:
    """Factory function to create a repair proposal generator instance."""
    return RepairProposalGenerator()


# Example usage function (would be called from a skill or workflow)
def create_repair_proposal_from_analysis(
    request_id: str,
    task_id: str,
    workspace_root: str,
    failure_analysis: FailureAnalysisResult,
    validation_result: ValidationResult,
    target_files: List[str]
) -> RepairProposal:
    """Convenience function to create a repair proposal from analysis results."""
    generator = RepairProposalGenerator()
    request = RepairProposalRequest(
        request_id=request_id,
        task_id=task_id,
        workspace_root=workspace_root,
        failure_analysis=failure_analysis,
        validation_result=validation_result,
        target_files=target_files
    )
    return generator.generate_repair_proposal(request)