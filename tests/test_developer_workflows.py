#!/usr/bin/env python3
"""
Test script for Stage 32 Phase 8 Developer Workflows
Verifies that the four developer workflows are properly defined and can be used.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from app.extensions.developer_workflows import (
    create_local_project_inspection_skill,
    create_github_issue_investigation_skill,
    create_pull_request_review_skill,
    create_local_remote_repository_context_skill,
)
from app.extensions.contracts import SkillContract
from app.extensions.executable_skills import ExecutableSkillContract
from app.extensions.registry import ExtensionManager, ExtensionType


class TestDeveloperWorkflows(unittest.TestCase):
    """Test the developer workflows."""

    def setUp(self):
        """Set up test fixtures."""
        self.workflows = [
            create_local_project_inspection_skill(),
            create_github_issue_investigation_skill(),
            create_pull_request_review_skill(),
            create_local_remote_repository_context_skill(),
        ]

    def test_workflow_creation(self):
        """Test that we can create the four workflows."""
        for workflow in self.workflows:
            self.assertIsNotNone(workflow)
            self.assertIsInstance(workflow, ExecutableSkillContract)  # Note: This is the actual type
            self.assertTrue(workflow.skill_id.startswith(
                ('local_project_inspection', 'github_issue_investigation', 'pull_request_review', 'local_remote_repository_context')
            ))

    def test_workflow_registration(self):
        """Test that workflows can be registered with ExtensionManager."""
        manager = ExtensionManager()
        for workflow in self.workflows:
            # Convert to base SkillContract for registration (as we did in integration)
            base_contract = SkillContract(
                name=workflow.skill_id,
                intent=workflow.intent,
                required_capabilities=workflow.required_capabilities,
                workflow=[w.to_dict() for w in workflow.workflow],
                constraints=workflow.constraints,
                verification_strategy=workflow.verification_strategy.value,
                success_history=workflow.success_history,
                usage_metadata=workflow.usage_metadata,
            )
            # This should not raise
            manager.skills.register(base_contract)
            # Verify it's registered
            retrieved = manager.skills.get(workflow.skill_id)
            self.assertIsNotNone(retrieved)
            self.assertEqual(retrieved.name, workflow.skill_id)

    def test_local_project_inspection_parameters(self):
        """Test the local project inspection skill parameters."""
        workflow = create_local_project_inspection_skill()
        param_names = {p.name for p in workflow.parameters}
        self.assertIn('workspace_path', param_names)
        self.assertIn('max_files', param_names)
        self.assertIn('file_extensions', param_names)
        # Check defaults
        workspace_param = workflow.get_parameter('workspace_path')
        self.assertEqual(workspace_param.default, "")
        max_files_param = workflow.get_parameter('max_files')
        self.assertEqual(max_files_param.default, 5)
        self.assertEqual(max_files_param.min_value, 1)
        self.assertEqual(max_files_param.max_value, 20)
        extensions_param = workflow.get_parameter('file_extensions')
        self.assertIsInstance(extensions_param.default, list)
        self.assertIn("*.py", extensions_param.default)

    def test_github_issue_investigation_parameters(self):
        """Test the GitHub issue investigation skill parameters."""
        workflow = create_github_issue_investigation_skill()
        param_names = {p.name for p in workflow.parameters}
        self.assertIn('repository', param_names)
        self.assertIn('search_query', param_names)
        self.assertIn('max_issues', param_names)
        # Check defaults and constraints
        max_issues_param = workflow.get_parameter('max_issues')
        self.assertEqual(max_issues_param.default, 10)
        self.assertEqual(max_issues_param.min_value, 1)
        self.assertEqual(max_issues_param.max_value, 50)

    def test_pull_request_review_parameters(self):
        """Test the pull request review skill parameters."""
        workflow = create_pull_request_review_skill()
        param_names = {p.name for p in workflow.parameters}
        self.assertIn('repository', param_names)
        self.assertIn('pull_number', param_names)
        self.assertIn('max_files', param_names)
        # pull_number is required
        pull_number_param = workflow.get_parameter('pull_number')
        self.assertTrue(pull_number_param.required)
        self.assertEqual(pull_number_param.min_value, 1)
        # max_files defaults
        max_files_param = workflow.get_parameter('max_files')
        self.assertEqual(max_files_param.default, 10)
        self.assertEqual(max_files_param.min_value, 1)
        self.assertEqual(max_files_param.max_value, 50)

    def test_local_remote_repository_context_parameters(self):
        """Test the local/remote repository context skill parameters."""
        workflow = create_local_remote_repository_context_skill()
        param_names = {p.name for p in workflow.parameters}
        self.assertIn('workspace_path', param_names)
        self.assertIn('repository', param_names)
        self.assertIn('compare_type', param_names)
        # compare_type should have enum
        compare_type_param = workflow.get_parameter('compare_type')
        self.assertEqual(compare_type_param.default, "status")
        self.assertEqual(compare_type_param.enum, ["status", "log", "diff"])

    def test_workflow_steps_not_empty(self):
        """Test that each workflow has at least one step."""
        for workflow in self.workflows:
            self.assertGreater(len(workflow.workflow), 0)
            # Each step should have a tool and step_id
            for step in workflow.workflow:
                self.assertTrue(step.step_id)
                self.assertTrue(step.tool)

        def test_workflow_requires_and_produces(self):
            """Test that workflow steps have proper dependency mapping."""
            for workflow in self.workflows:
                produced = set()
                # First, add the skill parameters as available inputs
                # (In real execution, these would come from skill inputs)
                for param in workflow.parameters:
                    produced.add(param.name)
            
                for step in workflow.workflow:
                    # Each required output must have been produced by a previous step OR be a skill parameter
                    for req in step.requires:
                        self.assertIn(req, produced, f"Step {step.step_id} requires {req} which is not produced by previous steps or skill parameters")
                    # Add the outputs of this step to produced set
                    produced.update(step.produces)

    def test_workflow_capabilities(self):
        """Test that workflows declare required capabilities."""
        expected_caps = {
            'local_project_inspection': {'git.status', 'filesystem.read'},
            'github_issue_investigation': {'git.detect', 'github.search_issues', 'github.allowlist_check'},
            'pull_request_review': {'git.detect', 'github.get_pull_request', 'github.get_pull_request_files', 'github.allowlist_check', 'filesystem.read'},
            'local_remote_repository_context': {'git.status', 'git.log', 'git.diff', 'github.get_repo_info', 'filesystem.read'},
        }
        for workflow in self.workflows:
            declared = set(workflow.required_capabilities)
            expected = expected_caps[workflow.skill_id]
            # Note: Some capabilities might be internal (like github.allowlist_check) and not appear in the adapter's public list,
            # but we at least check that the workflow declares them.
            for cap in expected:
                self.assertIn(cap, declared, f"Workflow {workflow.skill_id} missing required capability {cap}")

    def test_workflow_constraints(self):
        """Test that workflows have constraints defined."""
        for workflow in self.workflows:
            self.assertGreater(len(workflow.constraints), 0)
            # Constraints should be strings
            for constraint in workflow.constraints:
                self.assertIsInstance(constraint, str)

    def test_workflow_risk_and_verification(self):
        """Test that workflows have risk level and verification strategy set."""
        for workflow in self.workflows:
            self.assertIn(workflow.risk_level.value, ['low', 'medium', 'high'])
            self.assertIn(workflow.verification_strategy.value, ['standard', 'strict', 'none'])


if __name__ == '__main__':
    unittest.main()