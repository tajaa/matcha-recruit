#!/usr/bin/env python3
"""
Count lines of code in each folder and subfolder of the project.
Shows both total lines per folder and breakdown by subfolder.
"""

import os
from pathlib import Path
from collections import defaultdict
from typing import Dict, Tuple

# File extensions to count as "code"
CODE_EXTENSIONS = {
    '.py', '.ts', '.tsx', '.js', '.jsx', '.json',
    '.css', '.scss', '.html', '.vue', '.sql',
    '.sh', '.bash', '.yaml', '.yml', '.md'
}

# Directories to skip
SKIP_DIRS = {
    '.git', 'node_modules', '.env', '__pycache__', '.venv', 'venv',
    'dist', 'build', '.pytest_cache', '.next', '.vercel',
    'coverage', '.tox', 'eggs', '.eggs', '.mypy_cache',
    '.DS_Store', 'target', '.gradle', '.cache'
}

def count_lines_in_file(filepath: Path) -> int:
    """Count non-empty lines in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return sum(1 for line in f if line.strip())
    except Exception:
        return 0

def count_lines_in_directory(dirpath: Path) -> int:
    """Count all lines in a directory."""
    total = 0
    for filepath in dirpath.rglob('*'):
        if filepath.is_file() and filepath.suffix in CODE_EXTENSIONS:
            total += count_lines_in_file(filepath)
    return total

def should_skip_dir(dirname: str) -> bool:
    """Check if directory should be skipped."""
    return dirname in SKIP_DIRS or dirname.startswith('.')

def analyze_project_structure(root_path: Path) -> Dict[str, Dict]:
    """
    Analyze project structure and count lines.
    Returns dict with folder stats and subfolder breakdowns.
    """
    results = {}

    for item in sorted(root_path.iterdir()):
        if not item.is_dir() or should_skip_dir(item.name):
            continue

        folder_name = item.name
        subfolder_counts = {}
        total_in_folder = 0

        # Count lines in subfolders
        for subfolder in sorted(item.iterdir()):
            if not subfolder.is_dir() or should_skip_dir(subfolder.name):
                continue

            subfolder_name = subfolder.name
            line_count = count_lines_in_directory(subfolder)

            if line_count > 0:
                subfolder_counts[subfolder_name] = line_count
                total_in_folder += line_count

        # Also count files directly in the folder (not in subfolders)
        root_level_lines = 0
        for filepath in item.glob('*'):
            if filepath.is_file() and filepath.suffix in CODE_EXTENSIONS:
                root_level_lines += count_lines_in_file(filepath)

        if root_level_lines > 0:
            subfolder_counts['[root level]'] = root_level_lines
            total_in_folder += root_level_lines

        if subfolder_counts:  # Only include if there's code
            results[folder_name] = {
                'total': total_in_folder,
                'subfolders': subfolder_counts
            }

    return results

def format_number(num: int) -> str:
    """Format number with thousands separator."""
    return f"{num:,}"

def print_results(results: Dict[str, Dict]):
    """Print results in a nice format."""
    print("\n" + "=" * 80)
    print("PROJECT CODE LINE COUNT ANALYSIS")
    print("=" * 80)

    # Calculate grand total
    grand_total = sum(data['total'] for data in results.values())

    # Sort by total lines (descending)
    sorted_folders = sorted(results.items(), key=lambda x: x[1]['total'], reverse=True)

    for folder_name, data in sorted_folders:
        total = data['total']
        subfolders = data['subfolders']

        # Print folder header
        print(f"\n📁 {folder_name}: {format_number(total)} lines")
        print("-" * 80)

        # Sort subfolders by line count
        sorted_subs = sorted(subfolders.items(), key=lambda x: x[1], reverse=True)

        for subfolder_name, count in sorted_subs:
            percentage = (count / total * 100) if total > 0 else 0
            bar_length = int(percentage / 2)
            bar = "█" * bar_length
            print(f"  {subfolder_name:<30} {format_number(count):>10} lines  {percentage:>5.1f}%  {bar}")

    # Print summary
    print("\n" + "=" * 80)
    print(f"TOTAL: {format_number(grand_total)} lines across {len(results)} folders")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    root = Path("/Users/finch/Documents/github/matcha-recruit")

    print("Analyzing project structure... (this may take a moment)")
    results = analyze_project_structure(root)

    print_results(results)
