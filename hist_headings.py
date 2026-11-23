import subprocess, re, sys

PATH = "build_site.py"
commits = subprocess.run(["git", "log", "--format=%h %ad %s", "--date=short", "-25", "--", PATH],
                         capture_output=True, text=True).stdout.strip().splitlines()
print(f"{len(commits)} commits touching {PATH}\n")
rows = []
for line in commits:
    sha = line.split()[0]
    blob = subprocess.run(["git", "show", f"{sha}:{PATH}"], capture_output=True, text=True).stdout
    m_card = re.search(r"^\.card h3\{([^}]*)\}", blob, re.M)
    m_base = re.search(r"^h3\{([^}]*)\}", blob, re.M)
    card = m_card.group(1) if m_card else "-"
    base = m_base.group(1) if m_base else "-"
    fs_card = re.search(r"font-size:([^;]+)", card)
    fs_base = re.search(r"font-size:([^;]+)", base)
    rows.append((sha, fs_base.group(1) if fs_base else "-", fs_card.group(1) if fs_card else "-",
                 line.split(" ", 2)[2][:44]))

print(f"{'commit':9} {'h3 base':9} {'.card h3':9} subject")
for r in rows:
    print(f"{r[0]:9} {r[1]:9} {r[2]:9} {r[3]}")
