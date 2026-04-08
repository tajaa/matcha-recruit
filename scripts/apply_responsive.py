import re
import os

files = [
    "client/src/pages/app/Employees.tsx",
    "client/src/pages/app/Onboarding.tsx",
    "client/src/pages/app/Accommodations.tsx",
    "client/src/pages/app/CompanySettings.tsx",
    "client/src/pages/app/Compliance.tsx",
    "client/src/pages/app/Handbooks.tsx",
    "client/src/pages/app/CredentialTemplates.tsx",
    "client/src/pages/app/EscalatedQueries.tsx",
    "client/src/pages/app/IRList.tsx",
    "client/src/pages/app/Policies.tsx",
    "client/src/pages/app/RiskAssessment.tsx",
    "client/src/pages/app/ERCopilot.tsx"
]

for file_path in files:
    if not os.path.exists(file_path):
        print(f"Skipping {file_path}, does not exist.")
        continue
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    
    # 1. Stack headers
    content = content.replace(
        '<div className="flex items-center justify-between">',
        '<div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 sm:gap-0">'
    )
    content = content.replace(
        '<div className="flex justify-between items-center mb-6">',
        '<div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 sm:gap-0 mb-6">'
    )
    # Buttons container in headers (approximate)
    content = content.replace(
        '<div className="flex gap-2">',
        '<div className="flex gap-2 w-full sm:w-auto">'
    )

    # 2. Filter inputs
    content = content.replace(
        '<div className="mt-6 flex items-center gap-3">',
        '<div className="mt-6 flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4 flex-wrap">'
    )
    # Right-aligned filter buttons
    content = content.replace(
        '<div className="flex gap-1 ml-auto">',
        '<div className="flex gap-1 w-full sm:w-auto sm:ml-auto overflow-x-auto pb-2 sm:pb-0">'
    )
    
    # 3. Tab navigation bars
    content = content.replace(
        '<div className="flex gap-1 mt-4 border-b border-zinc-800">',
        '<div className="flex gap-1 mt-4 border-b border-zinc-800 overflow-x-auto whitespace-nowrap [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">'
    )
    content = content.replace(
        '<div className="flex gap-1 border-b border-zinc-800/60 pb-px">',
        '<div className="flex gap-1 border-b border-zinc-800/60 pb-px overflow-x-auto whitespace-nowrap [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">'
    )
    content = content.replace(
        '<div className="flex gap-1 mb-5">',
        '<div className="flex gap-1 mb-5 overflow-x-auto whitespace-nowrap [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">'
    )

    # 4. Tables
    content = content.replace(
        '<table className="w-full text-sm text-left">',
        '<table className="w-full text-sm text-left min-w-[800px]">'
    )
    content = content.replace(
        '<div className="overflow-hidden rounded-xl border border-zinc-800">',
        '<div className="overflow-x-auto rounded-xl border border-zinc-800">'
    )

    # 5. Grids
    # For grid-cols-2
    content = re.sub(
        r'className="([^"]*\b)grid-cols-2(\b[^"]*)"',
        lambda m: f'className="{m.group(1)}grid-cols-1 sm:grid-cols-2{m.group(2)}"' if 'grid-cols-1' not in m.group(1) and 'md:grid-cols' not in m.group(1) else m.group(0),
        content
    )
    # For grid-cols-3
    content = re.sub(
        r'className="([^"]*\b)grid-cols-3(\b[^"]*)"',
        lambda m: f'className="{m.group(1)}grid-cols-1 md:grid-cols-3{m.group(2)}"' if 'grid-cols-1' not in m.group(1) and 'lg:grid-cols' not in m.group(1) else m.group(0),
        content
    )
    # For grid-cols-4
    content = re.sub(
        r'className="([^"]*\b)grid-cols-4(\b[^"]*)"',
        lambda m: f'className="{m.group(1)}grid-cols-1 md:grid-cols-2 lg:grid-cols-4{m.group(2)}"' if 'grid-cols-1' not in m.group(1) else m.group(0),
        content
    )
    # For grid-cols-5
    content = re.sub(
        r'className="([^"]*\b)grid-cols-5(\b[^"]*)"',
        lambda m: f'className="{m.group(1)}grid-cols-1 md:grid-cols-3 lg:grid-cols-5{m.group(2)}"' if 'grid-cols-1' not in m.group(1) else m.group(0),
        content
    )

    if content != original:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {file_path}")
    else:
        print(f"No changes for {file_path}")

print("Done")
