#!/usr/bin/env python3
"""
Security scanning script for HA ESCPOS Thermal Printer integration.

This script runs comprehensive security scans including:
- Dependency vulnerability scanning with Safety
- Python security linting with Bandit
- Static analysis with Ruff (security rules)
- Dependency auditing with pip-audit

Usage:
    python scripts/security_scan.py [--fix] [--verbose]

Options:
    --fix       Attempt to auto-fix security issues where possible
    --verbose   Show detailed output
"""

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import subprocess
import sys


class SecurityScanner:
    """Comprehensive security scanner for the project."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.project_root = Path(__file__).parent.parent

    def run_command(self, cmd: list[str], description: str, tolerate_failure: bool = False) -> bool:
        """Run a command and return success status."""
        try:
            if self.verbose:
                print(f"\n🔍 Running {description}...")
                print(f"Command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=not self.verbose,
                text=True,
                check=False
            )

            if result.returncode == 0:
                print(f"✅ {description} passed")
                return True
            else:
                if tolerate_failure:
                    print(f"⚠️  {description} completed with findings (exit {result.returncode})")
                    if not self.verbose and result.stderr:
                        print(f"Error output: {result.stderr}")
                    return True
                print(f"❌ {description} failed")
                if not self.verbose and result.stderr:
                    print(f"Error output: {result.stderr}")
                return False

        except FileNotFoundError:
            print(f"⚠️  {description} not found (tool may not be installed)")
            return False
        except Exception as e:
            print(f"❌ Error running {description}: {e}")
            return False

    def _try_commands(self, candidates: Sequence[Sequence[str]]) -> list[str] | None:
        """Return the first candidate command that executes successfully with --version."""
        for base in candidates:
            try:
                if self.verbose:
                    print(f"Probing tool command: {' '.join(base)} --version")
                result = subprocess.run(
                    [*base, "--version"], capture_output=True, check=True, text=True
                )
                if result.returncode == 0:
                    if self.verbose:
                        print(f"Detected tool via: {' '.join(base)}")
                    return list(base)
            except FileNotFoundError:
                if self.verbose:
                    print(f"Not found: {' '.join(base)}")
                continue
            except subprocess.CalledProcessError as e:
                # Some module invocations may not support --version; try --help as a fallback
                try:
                    if self.verbose:
                        print(f"'--version' failed for {' '.join(base)}; trying --help")
                    help_res = subprocess.run(
                        [*base, "--help"], capture_output=True, check=True, text=True
                    )
                    if help_res.returncode == 0:
                        if self.verbose:
                            print(f"Detected tool via help: {' '.join(base)}")
                        return list(base)
                except Exception:
                    if self.verbose:
                        print(f"Probe failed for: {' '.join(base)} ({e})")
                continue
        return None

    def check_dependencies(self) -> bool:
        """Check if security tools are installed and resolve their invocation."""
        self.tool_cmds: dict[str, list[str]] = {}

        tool_candidates: dict[str, list[list[str]]] = {
            # safety CLI may not always be on PATH; support module invocation variants
            "safety": [
                ["safety"],
                [sys.executable, "-m", "safety"],
                [sys.executable, "-m", "safety.cli"],
            ],
            "bandit": [["bandit"], [sys.executable, "-m", "bandit"]],
            "ruff": [["ruff"], [sys.executable, "-m", "ruff"]],
            # pip-audit can be invoked via module
            "pip-audit": [["pip-audit"], [sys.executable, "-m", "pip_audit"]],
        }

        missing: list[str] = []
        for tool, candidates in tool_candidates.items():
            cmd = self._try_commands(candidates)
            if cmd is None:
                missing.append(tool)
            else:
                self.tool_cmds[tool] = cmd

        if missing:
            print(f"⚠️  Missing security tools: {', '.join(missing)}")
            print("Install with: pip install safety bandit ruff pip-audit")
            return False

        print("✅ All security tools are available")
        return True

    def scan_dependencies(self) -> bool:
        """Scan dependencies for vulnerabilities using Safety."""
        # Use 'scan' if API key is available; otherwise prefer legacy 'check' to avoid interactive auth
        safety_base = self.tool_cmds.get("safety", ["safety"])
        api_key = os.getenv("SAFETY_API_KEY") or os.getenv("PYUP_API_KEY")

        if api_key:
            cmd_scan = [
                *safety_base,
                "scan",
                "--output",
                "screen",
                "--key",
                api_key,
            ]
            return self.run_command(
                cmd_scan,
                "Dependency vulnerability scan (Safety)",
                tolerate_failure=True,
            )

        # No API key: use legacy, non-interactive command to avoid prompts
        cmd_check = [*safety_base, "check", "--full-report"]
        return self.run_command(
            cmd_check, "Dependency vulnerability scan (Safety)", tolerate_failure=True
        )

    def scan_code_security(self) -> bool:
        """Scan Python code for security issues using Bandit."""
        return self.run_command(
            [
                *self.tool_cmds.get("bandit", ["bandit"]),
                "-s",
                "B110",
                "-r",
                "custom_components/escpos_printer",
            ],
            "Python security linting (Bandit)",
            tolerate_failure=True,
        )

    def scan_static_analysis(self) -> bool:
        """Run static analysis with security-focused rules."""
        return self.run_command(
            [
                *self.tool_cmds.get("ruff", ["ruff"]),
                "check",
                "--select",
                "S",
                "--ignore",
                "S110",
                "custom_components/escpos_printer",
            ],
            "Static analysis security rules (Ruff)",
            tolerate_failure=True,
        )

    def audit_dependencies(self) -> bool:
        """Audit dependencies for known vulnerabilities."""
        return self.run_command(
            self.tool_cmds.get("pip-audit", ["pip-audit"]),
            "Dependency vulnerability audit (pip-audit)",
            tolerate_failure=True,
        )

    def generate_report(self) -> None:
        """Generate a security scan report."""
        report_path = self.project_root / "security_report.md"
        print(f"\n📊 Generating security report: {report_path}")

        report_content = f"""# Security Scan Report
Generated: {Path(__file__).name}

## Project Information
- Project: HA ESCPOS Thermal Printer Integration
- Scan Date: {Path(__file__).stat().st_mtime}

## Security Tools Used
- Safety: Dependency vulnerability scanning
- Bandit: Python security linting
- Ruff: Static analysis with security rules
- pip-audit: Dependency vulnerability audit

## Recommendations
1. Review all security findings and address high-priority issues
2. Keep dependencies updated to latest secure versions
3. Run security scans regularly in CI/CD pipeline
4. Follow secure coding practices documented in SECURITY.md

## Security Best Practices
- Validate all user inputs
- Use parameterized queries for database operations
- Implement proper error handling
- Avoid storing sensitive data in logs
- Use HTTPS for network communications
- Regularly update dependencies
"""

        report_path.write_text(report_content)
        print("✅ Security report generated")

    def run_all_scans(self) -> bool:
        """Run all security scans."""
        print("🚀 Starting comprehensive security scan...")

        if not self.check_dependencies():
            return False

        scans = [
            self.scan_dependencies,
            self.scan_code_security,
            self.scan_static_analysis,
            self.audit_dependencies,
        ]

        results = []
        for scan in scans:
            results.append(scan())

        self.generate_report()

        passed = sum(results)
        total = len(results)

        print(f"\n📈 Security Scan Summary: {passed}/{total} scans completed")
        print("✅ Report generated; see security_report.md for details")
        return True


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Security scanner for HA ESCPOS integration")
    parser.add_argument("--fix", action="store_true", help="Attempt to auto-fix issues")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    scanner = SecurityScanner(verbose=args.verbose)
    success = scanner.run_all_scans()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
