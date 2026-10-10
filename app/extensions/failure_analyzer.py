"""
Failure Analyzer - Stage 32 Phase 10
Analyzes validation failures to support test-guided repair workflows.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime
import re
import os
import hashlib
from pathlib import Path

from app.extensions.validation_tools import ValidationResult
from app.extensions.change_proposal import ChangeProposal, FileChange
from app.extensions.dynamic_tools import ToolInterface, ToolMetadata, EnhancedToolMetadata, ToolResult, ToolResultStatus
from app.extensions.dynamic_tools import ToolAvailability, ToolLifecycleState


class FailureCategory(Enum):
    """Categories of failures that can be analyzed."""
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    ASSERTION_ERROR = "assertion_error"
    TEST_FAILURE = "test_failure"
    VALIDATION_ERROR = "validation_error"
    PATH_ERROR = "path_error"
    PERMISSION_ERROR = "permission_error"
    RESOURCE_ERROR = "resource_error"
    TIMEOUT_ERROR = "timeout_error"
    UNKNOWN = "unknown"


class ConfidenceLevel(Enum):
    """Confidence levels for failure analysis hypotheses."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass
class FailureAnalysisRequest:
    """Request for failure analysis."""
    analysis_id: str
    task_id: str
    validation_result: ValidationResult
    affected_file_paths: List[str]  # Files that were changed or related to the failure
    test_names: List[str] = field(default_factory=list)  # Specific test names that failed
    source_excerpts: Dict[str, str] = field(default_factory=dict)  # Bounded source code excerpts
    git_diff_info: Optional[str] = None  # Relevant Git diff information
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class FailureAnalysisResult:
    """Result of failure analysis."""
    analysis_id: str
    task_id: str
    failure_summary: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    affected_files: List[str] = field(default_factory=list)
    likely_cause: Optional[str] = None
    hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    confidence_level: ConfidenceLevel = ConfidenceLevel.LOW
    suggested_next_step: Optional[str] = None
    code_change_justified: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if isinstance(self.confidence_level, str):
            try:
                self.confidence_level = ConfidenceLevel(self.confidence_level)
            except ValueError:
                # If string doesn't match any enum, default to LOW
                self.confidence_level = ConfidenceLevel.LOW


class FailureAnalyzerTool(ToolInterface):
    """
    Tool for analyzing validation failures to support repair proposal generation.
    """

    def __init__(self):
        self._metadata = EnhancedToolMetadata(
            name="failure_analyzer",
            description="Analyze validation failures to support test-guided repair workflows",
            capability="failure.analyze",
            arguments={
                "type": "object",
                "properties": {
                    "analysis_request": {
                        "type": "object",
                        "properties": {
                            "analysis_id": {"type": "string"},
                            "task_id": {"type": "string"},
                            "validation_result": {
                                "type": "object",
                                "properties": {
                                    "validation_id": {"type": "string"},
                                    "task_id": {"type": "string"},
                                    "status": {"type": "string"},
                                    "exit_code": {"type": ["integer", "null"]},
                                    "duration_seconds": {"type": "number"},
                                    "stdout": {"type": "string"},
                                    "stderr": {"type": "string"},
                                    "structured_failures": {"type": "array"},
                                    "test_counts": {"type": "object"},
                                    "truncated": {"type": "boolean"},
                                    "sanitized_diagnostics": {"type": "string"}
                                }
                            },
                            "affected_file_paths": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "test_names": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "source_excerpts": {
                                "type": "object",
                                "additionalProperties": {"type": "string"}
                            },
                            "git_diff_info": {"type": ["string", "null"]}
                        },
                        "required": ["analysis_id", "task_id", "validation_result", "affected_file_paths"]
                    }
                },
                "required": ["analysis_request"]
            },
            output_schema={
                "type": "object",
                "properties": {
                    "failure_analysis_result": {
                        "type": "object",
                        "properties": {
                            "analysis_id": {"type": "string"},
                            "task_id": {"type": "string"},
                            "failure_summary": {"type": "string"},
                            "evidence": {"type": "array"},
                            "affected_files": {"type": "array"},
                            "likely_cause": {"type": ["string", "null"]},
                            "hypotheses": {"type": "array"},
                            "confidence_level": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "very_high"]
                            },
                            "suggested_next_step": {"type": ["string", "null"]},
                            "code_change_justified": {"type": "boolean"}
                        }
                    }
                },
                "required": ["failure_analysis_result"]
            },
            risk_level="low",
            side_effects=[],  # Pure analysis, no side effects
            permission_required="failure.analyze",
            verification_required=True,
            availability_requirements=[],
            lifecycle_state=ToolLifecycleState.REGISTERED,
            emits_monitoring=True
        )

    def get_metadata(self) -> EnhancedToolMetadata:
        return self._metadata

    def execute(self, arguments: Dict[str, Any]) -> Any:
        """Execute failure analysis on validation results."""
        if "analysis_request" not in arguments:
            raise ValueError("Missing analysis_request in arguments")
        
        # Convert dict to FailureAnalysisRequest
        req_data = arguments["analysis_request"]
        
        # Handle the validation_result which comes as a dict
        validation_result_dict = req_data["validation_result"]
        validation_result = ValidationResult(**validation_result_dict)
        
        # Create the request object
        analysis_request = FailureAnalysisRequest(
            analysis_id=req_data["analysis_id"],
            task_id=req_data["task_id"],
            validation_result=validation_result,
            affected_file_paths=req_data["affected_file_paths"],
            test_names=req_data.get("test_names", []),
            source_excerpts=req_data.get("source_excerpts", {}),
            git_diff_info=req_data.get("git_diff_info"),
        )
        
        # Execute the analysis
        result = self._analyze_failure(analysis_request)
        
        # Return structured result
        return {"failure_analysis_result": self._result_to_dict(result)}

    def is_available(self) -> bool:
        """Check if failure analyzer tool is available."""
        return True  # Always available if dependencies are met

    def _analyze_failure(self, request: FailureAnalysisRequest) -> FailureAnalysisResult:
        """Analyze a validation failure to determine likely causes."""
        start_time = datetime.utcnow()
        
        result = FailureAnalysisResult(
            analysis_id=request.analysis_id,
            task_id=request.task_id,
            failure_summary="Analysis in progress",
            affected_files=request.affected_file_paths.copy(),
            confidence_level=ConfidenceLevel.LOW,
            code_change_justified=False
        )

        try:
            # 1. Determine failure category from validation result
            failure_category = self._categorize_failure(request.validation_result)
            
            # 2. Extract evidence from validation output
            evidence = self._extract_evidence(request.validation_result, request.source_excerpts)
            
            # 3. Generate hypotheses based on failure category and evidence
            hypotheses = self._generate_hypotheses(failure_category, evidence, request)
            
            # 4. Determine likely cause and confidence
            likely_cause, confidence = self._determine_likely_cause(hypotheses, evidence)
            
            # 5. Determine if code change is justified
            code_change_justified = self._is_code_change_justified(hypotheses, evidence, request)
            
            # 6. Suggest next diagnostic step
            suggested_next_step = self._suggest_next_step(hypotheses, evidence, request)
            
            # 7. Build failure summary
            failure_summary = self._build_failure_summary(failure_category, evidence, request.validation_result)
            
            # Populate result
            result.failure_summary = failure_summary
            result.evidence = evidence
            result.likely_cause = likely_cause
            result.hypotheses = hypotheses
            result.confidence_level = confidence
            result.suggested_next_step = suggested_next_step
            result.code_change_justified = code_change_justified
            
            result.created_at = datetime.utcnow()
            return result

        except Exception as e:
            # If analysis itself fails, return error result
            result.failure_summary = f"Failure analysis error: {str(e)}"
            result.evidence = [{"type": "analysis_error", "content": str(e)}]
            result.confidence_level = ConfidenceLevel.LOW
            result.code_change_justified = False
            result.created_at = datetime.utcnow()
            return result

    def _categorize_failure(self, validation_result: ValidationResult) -> FailureCategory:
        """Categorize the failure based on validation result."""
        status = validation_result.status
        stdout = validation_result.stdout.lower()
        stderr = validation_result.stderr.lower()
        combined = stdout + stderr
        
        if status == ValidationStatus.TIMED_OUT:
            return FailureCategory.TIMEOUT_ERROR
        
        if "syntaxerror" in combined or "syntax error" in combined:
            return FailureCategory.SYNTAX_ERROR
            
        if "importerror" in combined or "import error" in combined or "modulenotfounderror" in combined:
            return FailureCategory.IMPORT_ERROR
            
        if "assertionerror" in combined or "assertion failed" in combined or "assert" in combined:
            return FailureCategory.ASSERTION_ERROR
            
        if "permission denied" in combined or "access is denied" in combined:
            return FailureCategory.PERMISSION_ERROR
            
        if "file not found" in combined or "no such file" in combined or "path" in combined:
            return FailureCategory.PATH_ERROR
            
        if "memoryerror" in combined or "out of memory" in combined:
            return FailureCategory.RESOURCE_ERROR
            
        # Check for test framework specific failures
        if "failed" in combined or "error" in combined:
            if "test" in combined or "assert" in combined:
                return FailureCategory.TEST_FAILURE
            return FailureCategory.VALIDATION_ERROR
            
        return FailureCategory.UNKNOWN

    def _extract_evidence(self, validation_result: ValidationResult, source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Extract evidence from validation output and source excerpts."""
        evidence = []
        
        # Add validation result info
        evidence.append({
            "type": "validation_result",
            "status": validation_result.status.value,
            "exit_code": validation_result.exit_code,
            "duration": validation_result.duration_seconds,
            "stdout_truncated": validation_result.truncated,
            "stderr_truncated": validation_result.truncated  # Assuming same truncation flag
        })
        
        # Add structured failures if available
        if validation_result.structured_failures:
            for i, failure in enumerate(validation_result.structured_failures):
                evidence.append({
                    "type": "structured_failure",
                    "index": i,
                    "content": failure
                })
        
        # Add sanitized diagnostics
        if validation_result.sanitized_diagnostics:
            evidence.append({
                "type": "sanitized_diagnostics",
                "content": validation_result.sanitized_diagnostics[:500]  # Bound the size
            })
        
        # Add test counts
        if validation_result.test_counts:
            evidence.append({
                "type": "test_counts",
                "counts": validation_result.test_counts
            })
        
        # Add bounded source excerpts
        for file_path, excerpt in source_excerpts.items():
            # Bound the excerpt size
            bounded_excerpt = excerpt[:1000] + ("..." if len(excerpt) > 1000 else "")
            evidence.append({
                "type": "source_excerpt",
                "file_path": file_path,
                "content": bounded_excerpt,
                "size": len(excerpt)
            })
        
        return evidence

    def _generate_hypotheses(self, failure_category: FailureCategory, evidence: List[Dict[str, Any]], 
                           request: FailureAnalysisRequest) -> List[Dict[str, Any]]:
        """Generate hypotheses about the likely cause of the failure."""
        hypotheses = []
        
        # Extract key information from evidence
        validation_info = None
        structured_failures = []
        source_excerpts = {}
        
        for ev in evidence:
            if ev["type"] == "validation_result":
                validation_info = ev
            elif ev["type"] == "structured_failure":
                structured_failures.append(ev["content"])
            elif ev["type"] == "source_excerpt":
                source_excerpts[ev["file_path"]] = ev["content"]
        
        # Generate hypotheses based on failure category
        if failure_category == FailureCategory.SYNTAX_ERROR:
            hypotheses.extend(self._generate_syntax_hypotheses(validation_info, structured_failures, source_excerpts))
        elif failure_category == FailureCategory.IMPORT_ERROR:
            hypotheses.extend(self._generate_import_hypotheses(validation_info, structured_failures, source_excerpts))
        elif failure_category == FailureCategory.ASSERTION_ERROR:
            hypotheses.extend(self._generate_assertion_hypotheses(validation_info, structured_failures, source_excerpts))
        elif failure_category == FailureCategory.TEST_FAILURE:
            hypotheses.extend(self._generate_test_failure_hypotheses(validation_info, structured_failures, source_excerpts))
        elif failure_category == FailureCategory.PATH_ERROR:
            hypotheses.extend(self._generate_path_hypotheses(validation_info, structured_failures, source_excerpts))
        elif failure_category == FailureCategory.PERMISSION_ERROR:
            hypotheses.extend(self._generate_permission_hypotheses(validation_info, structured_failures, source_excerpts))
        else:
            # Generic hypotheses for unknown/un categorized failures
            hypotheses.extend(self._generate_generic_hypotheses(validation_info, structured_failures, source_excerpts))
        
        # Add hypothesis about external changes if relevant
        if request.affected_file_paths:
            hypotheses.append({
                "description": "External modification of affected files since change proposal",
                "confidence": ConfidenceLevel.LOW,
                "evidence_refs": [i for i, ev in enumerate(evidence) if ev["type"] == "validation_result"],
                "type": "external_change",
                "justifies_code_change": False  # This would require reverting external changes, not fixing code
            })
        
        return hypotheses

    def _generate_syntax_hypotheses(self, validation_info: Dict, structured_failures: List, 
                                  source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate hypotheses for syntax errors."""
        hypotheses = []
        
        # Look for common syntax error patterns in output
        all_output = ""
        for ev in structured_failures:
            if isinstance(ev, dict) and "raw" in ev:
                all_output += ev["raw"] + "\n"
        
        # Common Python syntax errors
        if "invalid syntax" in all_output.lower():
            hypotheses.append({
                "description": "Invalid Python syntax - missing colon, parenthesis, or incorrect indentation",
                "confidence": ConfidenceLevel.HIGH,
                "evidence_refs": [0],  # Reference to validation info
                "type": "syntax_error",
                "justifies_code_change": True
            })
        
        if "eol while scanning string literal" in all_output.lower():
            hypotheses.append({
                "description": "Unterminated string literal - missing closing quote",
                "confidence": ConfidenceLevel.HIGH,
                "evidence_refs": [0],
                "type": "syntax_error",
                "justifies_code_change": True
            })
            
        if "unexpected indent" in all_output.lower() or "indentationerror" in all_output.lower():
            hypotheses.append({
                "description": "Incorrect indentation - mixing tabs and spaces or inconsistent indentation",
                "confidence": ConfidenceLevel.HIGH,
                "evidence_refs": [0],
                "type": "syntax_error",
                "justifies_code_change": True
            })
        
        return hypotheses

    def _generate_import_hypotheses(self, validation_info: Dict, structured_failures: List, 
                                  source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate hypotheses for import errors."""
        hypotheses = []
        
        all_output = ""
        for ev in structured_failures:
            if isinstance(ev, dict) and "raw" in ev:
                all_output += ev["raw"] + "\n"
        
        # Extract module name from error if possible
        module_match = re.search(r"No module named ['\"]([^'\"]+)['\"]", all_output, re.IGNORECASE)
        if module_match:
            module_name = module_match.group(1)
            hypotheses.append({
                "description": f"Missing module '{module_name}' - not installed or not in PYTHONPATH",
                "confidence": ConfidenceLevel.MEDIUM,
                "evidence_refs": [0],
                "type": "import_error",
                "justifies_code_change": False  # This is an environment issue, not code fix
            })
        
        hypotheses.append({
            "description": "Import error due to missing dependency or incorrect import path",
            "confidence": ConfidenceLevel.LOW,
            "evidence_refs": [0],
            "type": "import_error",
            "justifies_code_change": False
        })
        
        return hypotheses

    def _generate_assertion_hypotheses(self, validation_info: Dict, structured_failures: List, 
                                     source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate hypotheses for assertion errors."""
        hypotheses = []
        
        # Look for assertion message in failures
        assertion_messages = []
        for ev in structured_failures:
            if isinstance(ev, dict) and "raw" in ev:
                raw = ev["raw"]
                # Extract assertion message
                assert_match = re.search(r"AssertionError:\s*(.*)", raw)
                if assert_match:
                    assertion_messages.append(assert_match.group(1).strip())
                elif "assert" in raw.lower():
                    assertion_messages.append(raw.strip())
        
        if assertion_messages:
            hypotheses.append({
                "description": f"Assertion failed: {assertion_messages[0]}",
                "confidence": ConfidenceLevel.HIGH,
                "evidence_refs": [0],
                "type": "assertion_error",
                "justifies_code_change": True
            })
        else:
            hypotheses.append({
                "description": "Assertion failed - expected condition did not hold",
                "confidence": ConfidenceLevel.MEDIUM,
                "evidence_refs": [0],
                "type": "assertion_error",
                "justifies_code_change": True
            })
        
        return hypotheses

    def _generate_test_failure_hypotheses(self, validation_info: Dict, structured_failures: List, 
                                        source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate hypotheses for test failures."""
        hypotheses = []
        
        # Look for test names and failure patterns
        failed_tests = []
        for ev in structured_failures:
            if isinstance(ev, dict) and "raw" in ev:
                raw = ev["raw"]
                # Extract test function name
                test_match = re.search(r"(test_[^\s\(]+)", raw)
                if test_match:
                    failed_tests.append(test_match.group(1))
        
        if failed_tests:
            hypotheses.append({
                "description": f"Test failure in: {', '.join(failed_tests[:3])}",
                "confidence": ConfidenceLevel.MEDIUM,
                "evidence_refs": [0],
                "type": "test_failure",
                "justifies_code_change": True
            })
        else:
            hypotheses.append({
                "description": "Test failure - unexpected behavior in code under test",
                "confidence": ConfidenceLevel.LOW,
                "evidence_refs": [0],
                "type": "test_failure",
                "justifies_code_change": True
            })
        
        return hypotheses

    def _generate_path_hypotheses(self, validation_info: Dict, structured_failures: List, 
                                source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate hypotheses for path errors."""
        hypotheses = []
        
        all_output = ""
        for ev in structured_failures:
            if isinstance(ev, dict) and "raw" in ev:
                all_output += ev["raw"] + "\n"
        
        if "no such file" in all_output.lower() or "file not found" in all_output.lower():
            hypotheses.append({
                "description": "File not found - incorrect path or file was deleted",
                "confidence": ConfidenceLevel.HIGH,
                "evidence_refs": [0],
                "type": "path_error",
                "justifies_code_change": True
            })
        
        hypotheses.append({
            "description": "Path error - file access failed due to incorrect path or permissions",
            "confidence": ConfidenceLevel.LOW,
            "evidence_refs": [0],
            "type": "path_error",
            "justifies_code_change": True
        })
        
        return hypotheses

    def _generate_permission_hypotheses(self, validation_info: Dict, structured_failures: List, 
                                      source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate hypotheses for permission errors."""
        hypotheses = []
        
        hypotheses.append({
            "description": "Permission denied - insufficient rights to access file or resource",
            "confidence": ConfidenceLevel.MEDIUM,
            "evidence_refs": [0],
            "type": "permission_error",
            "justifies_code_change": False  # This is an environment/config issue
        })
        
        return hypotheses

    def _generate_generic_hypotheses(self, validation_info: Dict, structured_failures: List, 
                                   source_excerpts: Dict[str, str]) -> List[Dict[str, Any]]:
        """Generate generic hypotheses for un categorized failures."""
        hypotheses = []
        
        hypotheses.append({
            "description": "Unexpected behavior or error during validation execution",
            "confidence": ConfidenceLevel.LOW,
            "evidence_refs": [0],
            "type": "unknown_error",
            "justifies_code_change": True  # Conservative assumption for analysis
        })
        
        return hypotheses

    def _determine_likely_cause(self, hypotheses: List[Dict[str, Any]], 
                              evidence: List[Dict[str, Any]]) -> Tuple[Optional[str], ConfidenceLevel]:
        """Determine the most likely cause from hypotheses."""
        if not hypotheses:
            return None, ConfidenceLevel.LOW
        
        # Sort hypotheses by confidence (descending)
        confidence_order = {
            ConfidenceLevel.VERY_HIGH: 4,
            ConfidenceLevel.HIGH: 3,
            ConfidenceLevel.MEDIUM: 2,
            ConfidenceLevel.LOW: 1
        }
        
        sorted_hypotheses = sorted(
            hypotheses, 
            key=lambda h: confidence_order.get(h.get("confidence", ConfidenceLevel.LOW), 0),
            reverse=True
        )
        
        # Take the highest confidence hypothesis that justifies a code change
        for hyp in sorted_hypotheses:
            if hyp.get("justifies_code_change", False):
                return hyp.get("description"), hyp.get("confidence", ConfidenceLevel.LOW)
        
        # If none justify code change, return the highest confidence anyway
        if sorted_hypotheses:
            top = sorted_hypotheses[0]
            return top.get("description"), top.get("confidence", ConfidenceLevel.LOW)
        
        return None, ConfidenceLevel.LOW

    def _is_code_change_justified(self, hypotheses: List[Dict[str, Any]], 
                                evidence: List[Dict[str, Any]], 
                                request: FailureAnalysisRequest) -> bool:
        """Determine if a code change is justified based on the analysis."""
        # Check if any high-confidence hypothesis justifies code change
        for hyp in hypotheses:
            confidence = hyp.get("confidence", ConfidenceLevel.LOW)
            justifies = hyp.get("justifies_code_change", False)
            
            if justifies and confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.VERY_HIGH]:
                return True
        
        # If we have test failures or assertion errors, generally justify code change
        validation_status = request.validation_result.status
        if validation_status in [ValidationStatus.FAILED]:
            # Check if it's likely a code issue vs environment issue
            failure_category = self._categorize_failure(request.validation_result)
            if failure_category in [
                FailureCategory.SYNTAX_ERROR,
                FailureCategory.ASSERTION_ERROR,
                FailureCategory.TEST_FAILURE,
                FailureCategory.PATH_ERROR
            ]:
                return True
        
        return False

    def _suggest_next_step(self, hypotheses: List[Dict[str, Any]], 
                         evidence: List[Dict[str, Any]], 
                         request: FailureAnalysisRequest) -> Optional[str]:
        """Suggest the next diagnostic step based on analysis."""
        if not hypotheses:
            return "Gather more validation output or test details"
        
        # Look for hypotheses that suggest gathering more information
        info_gathering = [h for h in hypotheses if "gather" in h.get("description", "").lower() or 
                         "more" in h.get("description", "").lower() or
                         "check" in h.get("description", "").lower()]
        
        if info_gathering:
            return info_gathering[0].get("description")
        
        # If we have a high confidence hypothesis that justifies code change, suggest proposing a fix
        for hyp in hypotheses:
            if (hyp.get("justifies_code_change", False) and 
                hyp.get("confidence") in [ConfidenceLevel.HIGH, ConfidenceLevel.VERY_HIGH]):
                return f"Propose code change to address: {hyp.get('description')}"
        
        # Default suggestion based on failure category
        failure_category = self._categorize_failure(request.validation_result)
        if failure_category == FailureCategory.SYNTAX_ERROR:
            return "Review recent syntax changes in affected files"
        elif failure_category == FailureCategory.IMPORT_ERROR:
            return "Check installed dependencies and import paths"
        elif failure_category == FailureCategory.ASSERTION_ERROR:
            return "Examine the assertion condition and expected values"
        elif failure_category == FailureCategory.TEST_FAILURE:
            return "Look at the specific test that is failing and its expectations"
        elif failure_category == FailureCategory.PATH_ERROR:
            return "Verify file paths and existence of target files"
        else:
            return "Examine validation output for more specific error details"

    def _build_failure_summary(self, failure_category: FailureCategory, 
                             evidence: List[Dict[str, Any]], 
                             validation_result: ValidationResult) -> str:
        """Build a human-readable failure summary."""
        status = validation_result.status.value
        
        if status == ValidationStatus.TIMED_OUT:
            return f"Validation timed out after {validation_result.duration_seconds:.1f} seconds"
        
        if status == ValidationStatus.CANCELLED:
            return "Validation was cancelled"
        
        if status == ValidationStatus.REJECTED:
            return "Validation command was rejected by security policy"
        
        if status == ValidationStatus.UNAVAILABLE:
            return "Validation tool or command is not available"
        
        # For failures, provide more detail
        if failure_category != FailureCategory.UNKNOWN:
            category_desc = failure_category.value.replace("_", " ").title()
            return f"{category_desc} detected during validation"
        
        # Fallback
        if validation_result.exit_code is not None and validation_result.exit_code != 0:
            return f"Validation failed with exit code {validation_result.exit_code}"
        
        return "Validation failed - see diagnostics for details"

    def _result_to_dict(self, result: FailureAnalysisResult) -> Dict[str, Any]:
        """Convert FailureAnalysisResult to dictionary for serialization."""
        return {
            "analysis_id": result.analysis_id,
            "task_id": result.task_id,
            "failure_summary": result.failure_summary,
            "evidence": result.evidence,
            "affected_files": result.affected_files,
            "likely_cause": result.likely_cause,
            "hypotheses": result.hypotheses,
            "confidence_level": result.confidence_level.value,
            "suggested_next_step": result.suggested_next_step,
            "code_change_justified": result.code_change_justified
        }


def create_failure_analyzer_tool() -> FailureAnalyzerTool:
    """Factory function to create a failure analyzer tool instance."""
    return FailureAnalyzerTool()


# Register the failure analyzer tool with the dynamic tool system when imported
def register_failure_analyzer_tool(dynamic_registry):
    """Register the failure analyzer tool with a dynamic tool registry."""
    tool = create_failure_analyzer_tool()
    dynamic_registry.register_tool(tool)
    return tool