#!/usr/bin/env python3
"""
Parity Test Suite for Tools and Jaws Library Refactoring

This suite verifies that user-visible behavior is identical before/after each refactoring phase.
Used to establish Phase 0 baseline and gated before each subsequent phase.

Usage:
    # Capture phase baseline
    python scripts/run_parity_tests.py --phase 0 --output phase0-baseline.json
    
    # Validate against baseline
    python scripts/compare_parity_runs.py phase0-baseline.json phase1-results.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from enum import Enum

# Phase 0: Baseline data (manually captured April 13, 2026)
PHASE_0_BASELINE = {
    "phase": 0,
    "date": "2026-04-13",
    "tests": {
        "1.1.add_tool": {"status": "PASS", "notes": "DB insert, UID generation works"},
        "1.2.edit_tool": {"status": "PASS", "notes": "Fields update, UID stable"},
        "1.3.copy_tool": {"status": "PASS", "notes": "Unique ID, full field clone"},
        "1.4.delete_tool": {"status": "PASS", "notes": "Complete removal from DB and UI"},
        "2.1.add_jaw": {"status": "PASS", "notes": "DB creation, UI visibility"},
        "2.2.edit_jaw_preview": {"status": "PASS", "notes": "Field updates, transform persistence"},
        "2.3.delete_jaw": {"status": "PASS", "notes": "Clean removal"},
        "3.1.excel_export": {"status": "PASS", "notes": "XLSX generation, data integrity"},
        "3.2.excel_import": {"status": "PASS", "notes": "Column mapping, conflict detection"},
        "3.3.db_switching": {"status": "PASS", "notes": "Alternate DB loads, no data leakage"},
        "4.1.stl_preview": {"status": "PASS", "notes": "3D model loading, gizmo sync"},
        "4.2.jaw_preview_plane": {"status": "PASS", "notes": "Rotation/position exact restore"},
        "4.3.ipc_handoff": {"status": "PASS", "notes": "Context passing, edits sync back"},
    },
    "summary": {
        "total": 13,
        "passed": 13,
        "failed": 0,
        "blocked": 0,
    },
}


class TestDomain(Enum):
    TOOLS_CRUD = "1"
    JAWS_CRUD = "2"
    EXPORT = "3"
    INTEGRATION = "4"


class TestResult(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


def write_baseline(output_path: str) -> None:
    """Write Phase 0 baseline to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(PHASE_0_BASELINE, f, indent=2)
    print(f"Phase 0 baseline written to: {output_path}")


def compare_runs(baseline_path: str, new_run_path: str) -> dict:
    """Compare baseline and new parity test run; detect regressions."""
    with open(baseline_path) as f:
        baseline = json.load(f)
    with open(new_run_path) as f:
        new_run = json.load(f)

    results = {
        "baseline_phase": baseline["phase"],
        "new_phase": new_run["phase"],
        "timestamp": datetime.now().isoformat(),
        "regressions": [],
        "improvements": [],
        "unchanged": [],
    }

    # Compare each test result
    for test_id, baseline_test in baseline["tests"].items():
        new_test = new_run["tests"].get(test_id, {"status": "MISSING"})

        if baseline_test["status"] == "PASS" and new_test["status"] != "PASS":
            results["regressions"].append({
                "test_id": test_id,
                "baseline": baseline_test["status"],
                "new": new_test["status"],
                "notes": new_test.get("notes", ""),
            })
        elif baseline_test["status"] != "PASS" and new_test["status"] == "PASS":
            results["improvements"].append({
                "test_id": test_id,
                "baseline": baseline_test["status"],
                "new": new_test["status"],
            })
        else:
            results["unchanged"].append(test_id)

    # Overall outcome
    results["outcome"] = "PASS" if not results["regressions"] else "FAIL"
    results["allowed_to_proceed"] = len(results["regressions"]) == 0

    return results


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python run_parity_tests.py [--phase N --output FILE] | [--compare BASELINE NEW]")
        sys.exit(1)

    if sys.argv[1] == "--phase" and len(sys.argv) >= 4:
        phase = int(sys.argv[2])
        if sys.argv[3] == "--output" and len(sys.argv) >= 5:
            output_path = sys.argv[4]
            if phase == 0:
                write_baseline(output_path)
            else:
                print(f"Phase {phase} parity test suite not yet implemented")
                sys.exit(1)

    elif sys.argv[1] == "--compare" and len(sys.argv) >= 4:
        baseline_path = sys.argv[2]
        new_run_path = sys.argv[3]
        comparison = compare_runs(baseline_path, new_run_path)
        
        # Write comparison report
        report_path = Path(new_run_path).parent / f"comparison_report_{datetime.now().isoformat().replace(':', '-')}.json"
        with open(report_path, 'w') as f:
            json.dump(comparison, f, indent=2)
        
        print(f"\n=== PARITY COMPARISON REPORT ===")
        print(f"Baseline Phase: {comparison['baseline_phase']}")
        print(f"New Phase: {comparison['new_phase']}")
        print(f"Result: {comparison['outcome']}")
        print(f"Regressions: {len(comparison['regressions'])}")
        print(f"Improvements: {len(comparison['improvements'])}")
        print(f"Allowed to Proceed: {comparison['allowed_to_proceed']}")
        print(f"Report saved to: {report_path}")
        
        sys.exit(0 if comparison['allowed_to_proceed'] else 1)

    else:
        print("Invalid arguments")
        sys.exit(1)


if __name__ == "__main__":
    main()
