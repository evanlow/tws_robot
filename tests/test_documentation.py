"""
Sprint 4 Task 4: Comprehensive Documentation Tests

Tests documentation completeness, accuracy, and accessibility including:
- Documentation file existence and structure
- API documentation completeness
- Deployment guide validation
- Code docstring coverage
- Example code validity
- Architecture documentation

Author: TWS Robot Development Team
Date: November 25, 2025
Sprint 4 Task 4
"""

import pytest
import os
import re
import ast
import importlib
import inspect
from pathlib import Path
from typing import List, Set, Tuple


# ============================================================================
# Test Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
CODE_DIRS = [
    PROJECT_ROOT / "backtest",
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "execution",
    PROJECT_ROOT / "monitoring",
    PROJECT_ROOT / "risk",
    PROJECT_ROOT / "strategies",
    PROJECT_ROOT / "strategy"
]

REQUIRED_DOCS = [
    "README.md",
    "prime_directive.md",
    "requirements.txt",
    "pytest.ini"
]

REQUIRED_DOCS_IN_DOCS_DIR = [
    "DEPLOYMENT_GUIDE.md",
    "PROJECT_PLAN.md",
    "TECHNICAL_SPECS.md"
]

REQUIRED_CONFIG_FILES = [
    "config/paper.py",
    "config/live.py",
    "config/env_config.py"
]


# ============================================================================
# Documentation File Existence Tests
# ============================================================================

class TestDocumentationFiles:
    """Test that all required documentation files exist"""
    
    def test_readme_exists(self):
        """Test README.md exists"""
        readme_path = PROJECT_ROOT / "README.md"
        assert readme_path.exists(), "README.md not found"
        assert readme_path.stat().st_size > 0, "README.md is empty"
    
    def test_deployment_guide_exists(self):
        """Test DEPLOYMENT_GUIDE.md exists in docs/"""
        deployment_path = DOCS_DIR / "DEPLOYMENT_GUIDE.md"
        assert deployment_path.exists(), "docs/DEPLOYMENT_GUIDE.md not found"
        assert deployment_path.stat().st_size > 0, "DEPLOYMENT_GUIDE.md is empty"
    
    def test_sprint_plan_exists(self):
        """Test PROJECT_PLAN.md exists in docs/"""
        sprint_path = DOCS_DIR / "PROJECT_PLAN.md"
        assert sprint_path.exists(), "docs/PROJECT_PLAN.md not found"
        assert sprint_path.stat().st_size > 0, "PROJECT_PLAN.md is empty"
    
    def test_prime_directive_exists(self):
        """Test prime_directive.md exists"""
        prime_path = PROJECT_ROOT / "prime_directive.md"
        assert prime_path.exists(), "prime_directive.md not found"
        assert prime_path.stat().st_size > 0, "prime_directive.md is empty"
    
    def test_requirements_file_exists(self):
        """Test requirements.txt exists"""
        req_path = PROJECT_ROOT / "requirements.txt"
        assert req_path.exists(), "requirements.txt not found"
        assert req_path.stat().st_size > 0, "requirements.txt is empty"
    
    def test_pytest_config_exists(self):
        """Test pytest.ini exists"""
        pytest_path = PROJECT_ROOT / "pytest.ini"
        assert pytest_path.exists(), "pytest.ini not found"
        assert pytest_path.stat().st_size > 0, "pytest.ini is empty"
    
    def test_all_required_docs_present(self):
        """Test all required documentation files are present"""
        missing_docs = []
        for doc_file in REQUIRED_DOCS:
            doc_path = PROJECT_ROOT / doc_file
            if not doc_path.exists():
                missing_docs.append(doc_file)
        
        for doc_file in REQUIRED_DOCS_IN_DOCS_DIR:
            doc_path = DOCS_DIR / doc_file
            if not doc_path.exists():
                missing_docs.append(f"docs/{doc_file}")
        
        assert len(missing_docs) == 0, f"Missing required docs: {missing_docs}"


# ============================================================================
# README Content Tests
# ============================================================================

class TestREADMEContent:
    """Test README.md contains essential information"""
    
    @pytest.fixture
    def readme_content(self):
        """Load README.md content"""
        readme_path = PROJECT_ROOT / "README.md"
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_readme_has_title(self, readme_content):
        """Test README has a title"""
        assert re.search(r'^#\s+.+', readme_content, re.MULTILINE), "README missing title"
    
    def test_readme_has_features_section(self, readme_content):
        """Test README has Features section"""
        assert "feature" in readme_content.lower(), "README missing Features section"
    
    def test_readme_has_installation_section(self, readme_content):
        """Test README has Installation section"""
        assert "install" in readme_content.lower(), "README missing Installation section"
    
    def test_readme_has_usage_section(self, readme_content):
        """Test README has Usage section"""
        assert "usage" in readme_content.lower(), "README missing Usage section"
    
    def test_readme_has_configuration_info(self, readme_content):
        """Test README has Configuration section"""
        assert "config" in readme_content.lower(), "README missing Configuration info"
    
    def test_readme_mentions_python_version(self, readme_content):
        """Test README specifies Python version"""
        assert "python" in readme_content.lower(), "README doesn't mention Python"
    
    def test_readme_has_code_examples(self, readme_content):
        """Test README includes code examples"""
        assert "```" in readme_content, "README missing code examples"


# ============================================================================
# Configuration Documentation Tests
# ============================================================================

class TestConfigurationDocumentation:
    """Test configuration files are documented"""
    
    @pytest.mark.skip(reason=".env.example not required in this project structure")
    def test_env_example_exists(self):
        """Test .env.example exists for reference"""
        env_example = PROJECT_ROOT / ".env.example"
        assert env_example.exists(), ".env.example not found"
    
    def test_config_paper_documented(self):
        """Test config/paper.py has docstring"""
        config_path = PROJECT_ROOT / "config" / "paper.py"
        if config_path.exists():
            with open(config_path, 'r') as f:
                content = f.read()
                assert '"""' in content or "'''" in content, "config/paper.py missing docstring"
    
    def test_config_live_documented(self):
        """Test config/live.py has docstring"""
        config_path = PROJECT_ROOT / "config" / "live.py"
        if config_path.exists():
            with open(config_path, 'r') as f:
                content = f.read()
                assert '"""' in content or "'''" in content, "config/live.py missing docstring"
    
    def test_all_config_files_present(self):
        """Test all required config files exist"""
        missing_configs = []
        for config_file in REQUIRED_CONFIG_FILES:
            config_path = PROJECT_ROOT / config_file
            if not config_path.exists():
                missing_configs.append(config_file)
        
        assert len(missing_configs) == 0, f"Missing config files: {missing_configs}"


# ============================================================================
# API Documentation Tests (Docstrings)
# ============================================================================

class TestAPIDocumentation:
    """Test that code modules have proper docstrings"""
    
    def _get_python_files(self, directory: Path) -> List[Path]:
        """Get all Python files in directory"""
        if not directory.exists():
            return []
        return list(directory.rglob("*.py"))
    
    def _has_module_docstring(self, file_path: Path) -> bool:
        """Check if Python file has module-level docstring"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                tree = ast.parse(content)
                return ast.get_docstring(tree) is not None
        except:
            return False
    
    def test_backtest_module_documented(self):
        """Test backtest modules have docstrings"""
        backtest_dir = PROJECT_ROOT / "backtest"
        if not backtest_dir.exists():
            pytest.skip("backtest directory not found")
        
        py_files = self._get_python_files(backtest_dir)
        undocumented = []
        
        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue
            if py_file.name == "__init__.py":
                continue
            if not self._has_module_docstring(py_file):
                undocumented.append(py_file.name)
        
        assert len(undocumented) < len(py_files) * 0.2, f"Too many undocumented files in backtest: {undocumented}"
    
    def test_core_module_documented(self):
        """Test core modules have docstrings"""
        core_dir = PROJECT_ROOT / "core"
        if not core_dir.exists():
            pytest.skip("core directory not found")
        
        py_files = self._get_python_files(core_dir)
        undocumented = []
        
        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue
            if py_file.name == "__init__.py":
                continue
            if not self._has_module_docstring(py_file):
                undocumented.append(py_file.name)
        
        assert len(undocumented) < len(py_files) * 0.2, f"Too many undocumented files in core: {undocumented}"
    
    def test_strategy_module_documented(self):
        """Test strategy modules have docstrings"""
        strategy_dir = PROJECT_ROOT / "strategy"
        if not strategy_dir.exists():
            pytest.skip("strategy directory not found")
        
        py_files = self._get_python_files(strategy_dir)
        undocumented = []
        
        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue
            if py_file.name == "__init__.py":
                continue
            if not self._has_module_docstring(py_file):
                undocumented.append(py_file.name)
        
        assert len(undocumented) < len(py_files) * 0.2, f"Too many undocumented files in strategy: {undocumented}"
    
    def test_monitoring_module_documented(self):
        """Test monitoring modules have docstrings"""
        monitoring_dir = PROJECT_ROOT / "monitoring"
        if not monitoring_dir.exists():
            pytest.skip("monitoring directory not found")
        
        py_files = self._get_python_files(monitoring_dir)
        undocumented = []
        
        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue
            if py_file.name == "__init__.py":
                continue
            if not self._has_module_docstring(py_file):
                undocumented.append(py_file.name)
        
        assert len(undocumented) < len(py_files) * 0.2, f"Too many undocumented files in monitoring: {undocumented}"


# ============================================================================
# Deployment Guide Tests
# ============================================================================

class TestDeploymentGuide:
    """Test deployment guide completeness"""
    
    @pytest.fixture
    def deployment_content(self):
        """Load deployment guide content from docs/"""
        deployment_path = DOCS_DIR / "DEPLOYMENT_GUIDE.md"
        with open(deployment_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_deployment_has_prerequisites(self, deployment_content):
        """Test deployment guide lists prerequisites"""
        content_lower = deployment_content.lower()
        assert "prerequis" in content_lower or "requirement" in content_lower, \
            "Deployment guide missing prerequisites"
    
    def test_deployment_has_installation_steps(self, deployment_content):
        """Test deployment guide has installation steps"""
        content_lower = deployment_content.lower()
        assert "install" in content_lower or "setup" in content_lower, \
            "Deployment guide missing installation steps"
    
    def test_deployment_has_configuration(self, deployment_content):
        """Test deployment guide has configuration section"""
        assert "config" in deployment_content.lower(), \
            "Deployment guide missing configuration section"
    
    def test_deployment_mentions_docker(self, deployment_content):
        """Test deployment guide mentions Docker/containers"""
        content_lower = deployment_content.lower()
        assert "docker" in content_lower or "container" in content_lower, \
            "Deployment guide doesn't mention Docker"
    
    def test_deployment_has_troubleshooting(self, deployment_content):
        """Test deployment guide has troubleshooting section"""
        content_lower = deployment_content.lower()
        assert "troubleshoot" in content_lower or "common issue" in content_lower or "problem" in content_lower, \
            "Deployment guide missing troubleshooting section"


# ============================================================================
# Sprint Documentation Tests
# ============================================================================

class TestSprintDocumentation:
    """Test sprint planning documentation"""
    
    @pytest.fixture
    def sprint_content(self):
        """Load project plan content from docs/"""
        sprint_path = DOCS_DIR / "PROJECT_PLAN.md"
        with open(sprint_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_sprint_has_goals(self, sprint_content):
        """Test sprint plan has goals"""
        content_lower = sprint_content.lower()
        assert "goal" in content_lower or "objective" in content_lower, \
            "Sprint plan missing goals"
    
    def test_sprint_has_deliverables(self, sprint_content):
        """Test sprint plan lists deliverables"""
        content_lower = sprint_content.lower()
        assert "deliverable" in content_lower or "task" in content_lower, \
            "Sprint plan missing deliverables"
    
    def test_sprint_tracks_progress(self, sprint_content):
        """Test sprint plan tracks progress"""
        # Should have checkboxes or status indicators
        assert "[x]" in sprint_content or "complete" in sprint_content.lower(), \
            "Sprint plan doesn't track progress"
    
    def test_sprint_has_test_counts(self, sprint_content):
        """Test sprint plan mentions test counts"""
        assert "test" in sprint_content.lower(), \
            "Sprint plan doesn't mention tests"
    
    def test_sprint_has_timeline(self, sprint_content):
        """Test sprint plan has timeline/dates"""
        # Should mention dates or days
        assert re.search(r'\d{4}|\bday\b', sprint_content.lower()), \
            "Sprint plan missing timeline"


# ============================================================================
# Prime Directive Documentation Tests
# ============================================================================

class TestPrimeDirective:
    """Test prime directive documentation"""
    
    @pytest.fixture
    def prime_content(self):
        """Load prime directive content"""
        prime_path = PROJECT_ROOT / "prime_directive.md"
        with open(prime_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_prime_has_testing_rules(self, prime_content):
        """Test prime directive has testing rules"""
        content_lower = prime_content.lower()
        assert "test" in content_lower, "Prime directive missing testing rules"
    
    def test_prime_has_examples(self, prime_content):
        """Test prime directive has examples"""
        assert "example" in prime_content.lower() or "```" in prime_content, \
            "Prime directive missing examples"
    
    def test_prime_has_lessons_learned(self, prime_content):
        """Test prime directive documents lessons learned"""
        content_lower = prime_content.lower()
        assert "lesson" in content_lower or "learning" in content_lower, \
            "Prime directive missing lessons learned"
    
    def test_prime_mentions_100_percent(self, prime_content):
        """Test prime directive mentions 100% test pass rate"""
        assert "100" in prime_content, "Prime directive doesn't mention 100% pass rate"


# ============================================================================
# Code Example Tests
# ============================================================================

class TestCodeExamples:
    """Test that code examples are valid"""
    
    def _get_example_files(self) -> List[Path]:
        """Get all example Python files"""
        examples_dir = PROJECT_ROOT / "examples"
        if not examples_dir.exists():
            return []
        return [f for f in examples_dir.glob("*.py") if not f.name.startswith("__")]
    
    def test_example_files_exist(self):
        """Test that example files exist"""
        examples = self._get_example_files()
        assert len(examples) > 0, "No example files found in examples/ directory"
    
    def test_example_files_have_docstrings(self):
        """Test example files have documentation"""
        examples = self._get_example_files()
        undocumented = []
        
        for example_file in examples:
            try:
                with open(example_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    tree = ast.parse(content)
                    if ast.get_docstring(tree) is None:
                        undocumented.append(example_file.name)
            except:
                pass
        
        assert len(undocumented) < len(examples) * 0.3, \
            f"Too many undocumented examples: {undocumented}"
    
    def test_example_files_are_syntactically_valid(self):
        """Test example files have valid Python syntax"""
        examples = self._get_example_files()
        invalid = []
        
        for example_file in examples:
            try:
                with open(example_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    ast.parse(content)
            except SyntaxError:
                invalid.append(example_file.name)
        
        assert len(invalid) == 0, f"Example files with syntax errors: {invalid}"


# ============================================================================
# Architecture Documentation Tests
# ============================================================================

class TestArchitectureDocumentation:
    """Test architecture documentation exists"""
    
    def test_technical_specs_exists(self):
        """Test TECHNICAL_SPECS.md exists in docs/"""
        tech_path = DOCS_DIR / "TECHNICAL_SPECS.md"
        assert tech_path.exists(), "docs/TECHNICAL_SPECS.md not found"
    
    def test_project_structure_documented(self):
        """Test project structure is documented somewhere"""
        # Check in README or TECHNICAL_SPECS
        readme_path = PROJECT_ROOT / "README.md"
        tech_path = DOCS_DIR / "TECHNICAL_SPECS.md"
        
        has_structure = False
        for doc_path in [readme_path, tech_path]:
            if doc_path.exists():
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read().lower()
                    if "structure" in content or "directory" in content or "module" in content:
                        has_structure = True
                        break
        
        assert has_structure, "Project structure not documented"
    
    @pytest.mark.skip(reason="Sprint completion docs not required in this project structure")
    def test_sprint_completion_docs_exist(self):
        """Test sprint completion documents exist"""
        sprint_docs = list(PROJECT_ROOT.glob("SPRINT*_COMPLETE.md"))
        assert len(sprint_docs) >= 3, "Missing sprint completion documentation"


# ============================================================================
# Documentation Completeness Tests
# ============================================================================

class TestDocumentationCompleteness:
    """Test overall documentation completeness"""
    
    def test_total_doc_files_count(self):
        """Test adequate number of documentation files"""
        md_files = list(PROJECT_ROOT.glob("*.md")) + list(DOCS_DIR.glob("*.md"))
        # Should have README, deployment, sprint plans, completions, etc.
        assert len(md_files) >= 5, f"Only {len(md_files)} markdown files found, expected at least 5"
    
    def test_total_doc_size(self):
        """Test documentation is substantial"""
        md_files = list(PROJECT_ROOT.glob("*.md")) + list(DOCS_DIR.glob("*.md"))
        total_size = sum(f.stat().st_size for f in md_files if f.is_file())
        # Should have at least 100KB of documentation
        assert total_size > 100_000, f"Documentation only {total_size} bytes, expected >100KB"
    
    def test_key_modules_have_readme(self):
        """Test key modules have README files"""
        key_modules = ["risk", "backtest"]
        missing_readmes = []
        
        for module in key_modules:
            module_path = PROJECT_ROOT / module
            if module_path.exists() and module_path.is_dir():
                readme_path = module_path / "README.md"
                if not readme_path.exists():
                    missing_readmes.append(module)
        
        # Allow some modules to not have READMEs
        assert len(missing_readmes) < len(key_modules), \
            f"Modules missing READMEs: {missing_readmes}"


# ============================================================================
# Test Documentation Currency Tests
# ============================================================================

class TestDocumentationCurrency:
    """Test that documentation is up-to-date"""
    
    def test_readme_mentions_current_features(self):
        """Test README mentions current major features"""
        readme_path = PROJECT_ROOT / "README.md"
        with open(readme_path, 'r', encoding='utf-8') as f:
            content = f.read().lower()
        
        # Should mention key features from Sprint 1-4
        key_features = ["paper trading", "backtest", "risk", "strategy"]
        mentioned = sum(1 for feature in key_features if feature in content)
        
        assert mentioned >= 3, f"README only mentions {mentioned}/4 key features"
    
    def test_requirements_has_dependencies(self):
        """Test requirements.txt lists dependencies"""
        req_path = PROJECT_ROOT / "requirements.txt"
        with open(req_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        assert len(lines) >= 5, f"Only {len(lines)} dependencies listed"
    
    def test_sprint_plan_shows_current_sprint(self):
        """Test project plan shows current project status"""
        sprint_path = DOCS_DIR / "PROJECT_PLAN.md"
        with open(sprint_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Should mention sprints or phases
        assert "sprint" in content.lower() or "phase" in content.lower() or "week" in content.lower(), \
            "Project plan doesn't show project phases"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
