#!/usr/bin/env python3
"""Audit sécurisé du moteur de détection des domaines EDAN."""

from pathlib import Path
import re
import sys

ROOT = Path.cwd()

FILES = [
    "src/ai/understanding/domainCatalog.ts",
    "src/ai/understanding/appUnderstanding.ts",
]

print("=" * 60)
print("AUDIT DU MOTEUR DE DOMAINES EDAN")
print("=" * 60)
print("Répertoire :", ROOT)

missing = []

for relative in FILES:
    path = ROOT / relative
    print(f"\n--- {relative} ---")

    if not path.is_file():
        print("FICHIER INTROUVABLE")
        missing.append(relative)
        continue

    source = path.read_text(encoding="utf-8")
    print("Taille :", len(source), "caractères")
    print("Nombre de lignes :", len(source.splitlines()))

    patterns = [
        r"findDomainCandidates",
        r"validateDomainCatalog",
        r"detectDomain",
        r"DOMAIN_CATALOG",
        r"businessDomainProfile",
    ]

    lines = source.splitlines()
    found = set()

    for number, line in enumerate(lines, 1):
        for pattern in patterns:
            if re.search(pattern, line):
                found.add(pattern)
                print(f"L{number}: {line.strip()[:200]}")

    print("Symboles trouvés :", ", ".join(sorted(found)) or "aucun")

if missing:
    print("\nATTENTION : fichiers manquants.")
    print("Lance ce script depuis ~/EDAN/backend.")
    sys.exit(1)

print("\nAUDIT TERMINÉ : aucune source n'a été modifiée.")