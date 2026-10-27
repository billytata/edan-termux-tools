cd ~/EDAN/backend && cat > edan_domain_classification_fix_v3.py <<'PY'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Correction protégée du classement des domaines EDAN."""

from pathlib import Path
from datetime import datetime
import subprocess
import sys

ROOT = Path.cwd()
CATALOG = ROOT / "src/ai/understanding/domainCatalog.ts"
UNDERSTANDING = ROOT / "src/ai/understanding/appUnderstanding.ts"
TEST = ROOT / ".tmp-edan-domain-classification-v3.ts"

ANCHOR = '    id: "immobilier-general",'

ENTRIES = '''  {
    id: "gestion-locative",
    name: "Gestion locative",
    sector: "Immobilier et gestion locative",
    aliases: [
      "application de gestion locative",
      "gestion locative",
      "gestion des locations",
      "gestion de biens locatifs",
      "gestion des biens locatifs",
      "location immobilière",
      "gestion des loyers",
      "gestion des propriétaires et locataires",
      "rental management",
      "property rental management",
      "rental property management",
      "lease management",
      "landlord and tenant management",
      "rent collection management",
      "landlord management",
      "tenant management",
      "rent collection",
      "rental property",
      "property rentals"
    ],
    uiuxCategory: "real-estate"
  },
  {
    id: "reparation-telephones",
    name: "Réparation de téléphones",
    sector: "Réparation et maintenance de téléphones",
    aliases: [
      "réparation de téléphone",
      "réparation de téléphones",
      "réparateur de téléphones",
      "service de réparation de téléphones",
      "atelier de réparation de téléphones",
      "phone repair",
      "mobile phone repair",
      "cell phone repair",
      "phone repair shop",
      "smartphone repair"
    ],
    uiuxCategory: "general"
  },
'''

TEST_CODE = r'''
import { strict as assert } from "node:assert";
import { understandApp } from "./src/ai/understanding/appUnderstanding";
import { findDomainCandidates, validateDomainCatalog } from "./src/ai/understanding/domainCatalog";

const cases = [
  {
    label: "Gestion locative français",
    prompt: "Créer une application de gestion locative pour gérer les propriétaires, les locataires, les contrats et les paiements des loyers.",
    expected: "Gestion locative"
  },
  {
    label: "Rental management English",
    prompt: "Build a rental management application to manage landlords, tenants, lease agreements and rent payments.",
    expected: "Gestion locative"
  },
  {
    label: "Cardiologie",
    prompt: "Créer une application de gestion de cardiologie pour suivre les patients et les consultations.",
    expected: "Cardiologie"
  },
  {
    label: "Réparation de téléphones",
    prompt: "Créer une application de réparation de téléphones pour gérer les réparations et les clients.",
    expected: "Réparation de téléphones"
  },
  {
    label: "Phone repair English",
    prompt: "Build a phone repair application to manage repairs and customers.",
    expected: "Réparation de téléphones"
  }
];

for (const item of cases) {
  const actual = understandApp(item.prompt).domain;
  console.log(`${item.label}: ${actual}`);
  assert.equal(actual, item.expected, `Échec : ${item.label}`);
}

const validation = validateDomainCatalog();
assert.equal(validation.duplicateIds.length, 0,
  `Identifiants en double : ${validation.duplicateIds.join(", ")}`);
assert.equal(validation.duplicateNames.length, 0,
  `Noms en double : ${validation.duplicateNames.join(", ")}`);
assert.equal(validation.invalidEntries.length, 0,
  `Entrées invalides : ${validation.invalidEntries.join(", ")}`);

for (const phrase of [
  "gestion locative",
  "rental management",
  "lease management",
  "réparation de téléphones",
  "phone repair"
]) {
  const candidates = findDomainCandidates(phrase);
  assert(candidates.length > 0, `Aucun candidat pour : ${phrase}`);
}

console.log("PASS — 5 scénarios fonctionnels et validation du catalogue");
'''

def run(command, label):
    print(f"\n=== {label} ===", flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"{label} a échoué (code {result.returncode})")

def main():
    for path in (CATALOG, UNDERSTANDING):
        if not path.is_file():
            print(f"ARRÊT : fichier absent : {path}")
            return 2

    if TEST.exists():
        print(f"ARRÊT : test temporaire déjà présent : {TEST}")
        print("Aucun fichier source n'a été modifié.")
        return 2

    original = CATALOG.read_bytes()
    source = original.decode("utf-8")

    if source.count(ANCHOR) != 1:
        print("ARRÊT : point d'insertion du catalogue absent ou ambigu.")
        return 2

    if 'id: "gestion-locative"' in source or \
       'id: "reparation-telephones"' in source:
        print("ARRÊT : un identifiant existe déjà.")
        print("Inspecter le catalogue avant de poursuivre.")
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = ROOT / ".edan-backups" / f"domain-classification-v3-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    (backup_dir / "domainCatalog.ts").write_bytes(original)

    changed = False
    try:
        updated = source.replace(ANCHOR, ENTRIES + ANCHOR, 1)
        CATALOG.write_text(updated, encoding="utf-8")
        changed = True
        print("Catalogue modifié : 2 domaines spécialisés ajoutés.")
        print("Sauvegarde :", backup_dir)

        TEST.write_text(TEST_CODE, encoding="utf-8")

        run(
            ["npx", "tsx", str(TEST)],
            "Tests fonctionnels français/anglais et intégrité du catalogue"
        )

        regressions = [
            "test-domain-catalog-integration.ts",
            "test-domain-ranking-regression.ts",
            "test-domain-candidate-ranking.ts",
            "test-domain-catalog-new-profiles.ts",
            "test-understanding-domain-bilingual-targeted.ts",
            "test-understanding-domain-bilingual-regression.ts",
        ]

        for name in regressions:
            path = ROOT / name
            if path.is_file():
                run(["npx", "tsx", name], f"Régression : {name}")
            else:
                print(f"TEST ABSENT — ignoré : {name}")

        run(["npx", "tsc", "--noEmit"], "Vérification TypeScript")

        print("\nSUCCÈS : toutes les validations exécutées ont réussi.")
        print("Sauvegarde conservée :", backup_dir)
        return 0

    except Exception as exc:
        print(f"\nÉCHEC : {exc}", file=sys.stderr)
        if changed:
            CATALOG.write_bytes(original)
            print("Catalogue restauré à son état initial.", file=sys.stderr)
        print("Sauvegarde conservée :", backup_dir, file=sys.stderr)
        return 1

    finally:
        if TEST.exists():
            TEST.unlink()

if __name__ == "__main__":
    sys.exit(main())
PY
python3 edan_domain_classification_fix_v3.py