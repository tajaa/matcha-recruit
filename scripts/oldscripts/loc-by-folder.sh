#!/usr/bin/env python3
# loc-by-folder.sh — count lines of code by top-level folder in client/src
#
# Usage:
#   ./scripts/loc-by-folder.sh                  # uses client/src relative to script
#   ./scripts/loc-by-folder.sh /path/to/src      # explicit path

import os
import sys
from pathlib import Path
from collections import defaultdict

EXTENSIONS = {'.tsx', '.ts', '.css', '.js', '.jsx'}

script_dir = Path(__file__).parent
root = Path(sys.argv[1]) if len(sys.argv) > 1 else (script_dir / '../client/src').resolve()
root = root.resolve()

folder_lines = defaultdict(int)
folder_files = defaultdict(int)

for path in root.rglob('*'):
    if path.is_file() and path.suffix in EXTENSIONS:
        rel = path.relative_to(root)
        folder = rel.parts[0] if len(rel.parts) > 1 else '(root)'
        try:
            lines = path.read_text(encoding='utf-8', errors='ignore').count('\n')
        except Exception:
            continue
        folder_lines[folder] += lines
        folder_files[folder] += 1

sorted_folders = sorted(folder_lines.items(), key=lambda x: x[1], reverse=True)

max_lines = sorted_folders[0][1] if sorted_folders else 1
bar_max = 24

print()
print(f"  Lines of code by folder")
print(f"  {root}")
print(f"  {'═' * 62}")
print(f"  {'Folder':<20}  {'Lines':>7}  {'Files':>5}   {'Bar'}")
print(f"  {'─' * 62}")

for folder, lines in sorted_folders:
    files = folder_files[folder]
    bar_len = round((lines / max_lines) * bar_max)
    bar = '█' * bar_len
    print(f"  {folder:<20}  {lines:>7,}  {files:>5}   {bar}")

print(f"  {'─' * 62}")
total_lines = sum(folder_lines.values())
total_files = sum(folder_files.values())
print(f"  {'TOTAL':<20}  {total_lines:>7,}  {total_files:>5}")
print()
