#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EDAN — Correction globale et gardée du catalogue des domaines.
- Vérifie l'état attendu du fichier.
- Crée une sauvegarde horodatée.
- Corrige les alias et ajoute les domaines manquants.
- Crée un test indépendant.
- Lance les tests fonctionnels, les régressions et TypeScript.
- Restaure uniquement les fichiers modifiés par ce script en cas d'échec.
"""

from pathlib import Path
from datetime import datetime
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path.home() / "EDAN" / "backend"
CATALOG = ROOT / "src/ai/understanding/domainCatalog.ts"
TEST = ROOT / "test-domain-catalog-global-correction-independent.ts"

EXPECTED_SHA256 = (
    "ccbe136366c2c750b8176b209d93fdb21c06b440053d44ac072761134d4ba06c"
)

BACKUP_DIR = ROOT / ".edan-backups" / (
    "domain-catalog-global-" + datetime.now().strftime("%Y%m%d-%H%M%S")
)

TEST_CONTENT = r'''import assert from "node:assert/strict";
import {
  DOMAIN_CATALOG,
  findDomainCandidates,
  validateDomainCatalog,
} from "./src/ai/understanding/domainCatalog";

const cases: Array<{ prompt: string; expected: string }> = [
  {
    prompt: "application de gestion des stocks",
    expected: "gestion-stocks-generale",
  },
  {
    prompt: "inventory management application",
    expected: "gestion-stocks-generale",
  },
  {
    prompt: "application bancaire",
    expected: "finance-bancaire",
  },
  {
    prompt: "banking application",
    expected: "finance-bancaire",
  },
  {
    prompt: "application de livraison de repas",
    expected: "livraison-generale",
  },
  {
    prompt: "food delivery app",
    expected: "livraison-generale",
  },
  {
    prompt: "application de gestion de chantier",
    expected: "gestion-projets-construction",
  },
  {
    prompt: "construction project management",
    expected: "gestion-projets-construction",
  },
];

const validation = validateDomainCatalog();

assert.equal(
  validation.duplicateIds.length,
  0,
  `Identifiants dupliqués : ${validation.duplicateIds.join(", ")}`
);
assert.equal(
  validation.duplicateNames.length,
  0,
  `Noms dupliqués : ${validation.duplicateNames.join(", ")}`
);
assert.equal(
  validation.invalidEntries.length,
  0,
  `Entrées invalides : ${JSON.stringify(validation.invalidEntries)}`
);

for (const item of cases) {
  const candidates = findDomainCandidates(item.prompt);
  assert.ok(
    candidates.some((candidate) => candidate.id === item.expected),
    `Domaine attendu absent pour "${item.prompt}". Candidats : ${
      candidates.map((candidate) => candidate.id).join(", ") || "aucun"
    }`
  );
  console.log(`PASS ${item.prompt} -> ${item.expected}`);
}

assert.ok(DOMAIN_CATALOG.length >= 218, "Le catalogue semble incomplet.");

console.log(`PASS validation du catalogue (${DOMAIN_CATALOG.length} domaines)`);
console.log(`PASS ${cases.length}/${cases.length} scénarios bilingues`);
'''

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], description: str) -> None:
    print(f"\n=== {description} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(
            f"Échec de « {description} » (code {result.returncode})"
        )


def add_aliases(source: str, entry_id: str, aliases: list[str]) -> str:
    pattern = re.compile(
        r'(\{\s*id:\s*"' + re.escape(entry_id) +
        r'"\s*,[\s\S]*?\baliases:\s*\[)([\s\S]*?)(\])'
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise RuntimeError(
            f"Impossible d'identifier de façon unique le domaine {entry_id}"
        )

    match = matches[0]
    existing = re.findall(r'"((?:\\.|[^"\\])*)"', match.group(2))
    normalized = {value.casefold().strip() for value in existing}
    additions = [
        alias for alias in aliases
        if alias.casefold().strip() not in normalized
    ]
    if not additions:
        return source

    new_array_body = match.group(2).rstrip()
    if existing and not new_array_body.rstrip().endswith(","):
        new_array_body += ","

    if new_array_body and not new_array_body.endswith(("\n", " ", "\t")):
        new_array_body += "\n"

    new_array_body += "".join(f'    "{alias}",\n' for alias in additions)
    replacement = match.group(1) + new_array_body + match.group(3)
    return source[:match.start()] + replacement + source[match.end():]


def add_domains(source: str) -> str:
    new_entries = [
        '''  {
    id: "gestion-stocks-generale",
    name: "Gestion des stocks",
    sector: "business",
    aliases: [
      "gestion des stocks",
      "application de gestion des stocks",
      "gestion de stock",
      "inventaire général",
      "inventory management",
      "inventory management application",
      "stock management",
      "stock control",
      "inventory tracking",
    ],
    uiuxCategory: "business",
  },
''',
        '''  {
    id: "finance-bancaire",
    name: "Services bancaires",
    sector: "finance",
    aliases: [
      "application bancaire",
      "services bancaires",
      "gestion bancaire",
      "gestion de banque",
      "banque en ligne",
      "banking application",
      "banking app",
      "bank management",
      "online banking",
      "bank account management",
    ],
    uiuxCategory: "finance",
  },
''',
        '''  {
    id: "livraison-generale",
    name: "Livraison",
    sector: "delivery",
    aliases: [
      "application de livraison",
      "gestion des livraisons",
      "service de livraison",
      "livraison de repas",
      "application de livraison de repas",
      "livraison de commandes",
      "food delivery",
      "food delivery app",
      "delivery application",
      "delivery management",
      "package delivery",
    ],
    uiuxCategory: "delivery",
  },
''',
    ]

    for entry in new_entries:
        entry_id = re.search(r'id:\s*"([^"]+)"', entry).group(1)
        if re.search(r'id:\s*"' + re.escape(entry_id) + r'"', source):
            continue

        anchor = re.search(
            r'(?m)^\s*\{\s*\n\s*id:\s*"immobilier-general"',
            source
        )
        if not anchor:
            raise RuntimeError(
                "Point d'insertion immobilier-general introuvable; "
                "aucune insertion risquée ne sera effectuée."
            )
        source = source[:anchor.start()] + entry + source[anchor.start():]

    return source


def main() -> int:
    if not ROOT.is_dir():
        raise RuntimeError(f"Dossier EDAN introuvable : {ROOT}")
    if not CATALOG.is_file():
        raise RuntimeError(f"Catalogue introuvable : {CATALOG}")

    initial_hash = sha256(CATALOG)
    if initial_hash != EXPECTED_SHA256:
        raise RuntimeError(
            "Le catalogue a changé depuis l'audit. Arrêt sans modification.\n"
            f"SHA attendu : {EXPECTED_SHA256}\n"
            f"SHA actuel  : {initial_hash}\n"
            "Relancez d'abord un audit du fichier actuel."
        )

    if TEST.exists():
        raise RuntimeError(
            f"Le test indépendant existe déjà : {TEST.name}. "
            "Le script refuse de l'écraser."
        )

    original_catalog = CATALOG.read_text(encoding="utf-8")
    updated = original_catalog

    updated = add_aliases(
        updated,
        "commerce-general",
        [
            "gestion des stocks commerciaux",
            "commercial and inventory management",
            "retail inventory management",
            "sales and inventory management",
        ],
    )
    updated = add_aliases(
        updated,
        "logistique-transport",
        [
            "gestion logistique",
            "transport management",
            "logistics management",
        ],
    )
    updated = add_aliases(
        updated,
        "gestion-projets-construction",
        [
            "gestion de chantier",
            "application de gestion de chantier",
            "construction project management",
            "construction site management",
            "construction management",
        ],
    )
    updated = add_aliases(
        updated,
        "construction-batiments",
        [
            "gestion de construction",
            "building construction management",
            "building construction",
        ],
    )
    updated = add_domains(updated)

    if updated == original_catalog:
        raise RuntimeError(
            "Aucune modification prévue : arrêt plutôt que créer un faux succès."
        )

    BACKUP_DIR.mkdir(parents=True, exist_ok=False)
    backup_catalog = BACKUP_DIR / "domainCatalog.ts.before"
    backup_catalog.write_text(original_catalog, encoding="utf-8")

    catalog_written = False
    test_written = False

    try:
        CATALOG.write_text(updated, encoding="utf-8")
        catalog_written = True

        TEST.write_text(TEST_CONTENT, encoding="utf-8")
        test_written = True

        print("\n=== Fichiers modifiés ===")
        print(f"Catalogue : {CATALOG}")
        print(f"Test      : {TEST}")
        print(f"Sauvegarde: {backup_catalog}")

        tests = [
            (
                ["npx", "tsx", TEST.name],
                "Test indépendant du catalogue bilingue",
            ),
            (
                ["npx", "tsx", "test-domain-ranking-regression.ts"],
                "Régression du classement des domaines",
            ),
            (
                ["npx", "tsx", "test-domain-candidate-ranking.ts"],
                "Classement des candidats",
            ),
            (
                ["npx", "tsx", "test-domain-catalog-integration.ts"],
                "Intégration du catalogue",
            ),
            (
                ["npx", "tsx", "test-understanding-domain-bilingual-targeted.ts"],
                "Compréhension bilingue ciblée",
            ),
            (
                ["npx", "tsx", "test-understanding-bilingual-integration-independent.ts"],
                "Intégration bilingue indépendante",
            ),
            (
                ["npx", "tsx", "test-understanding-multidomain.ts"],
                "Compréhension multidomaine",
            ),
            (
                ["npx", "tsc", "--noEmit"],
                "Vérification TypeScript",
            ),
        ]

        for command, description in tests:
            run(command, description)

        print("\nSUCCÈS : toutes les validations demandées ont réussi.")
        print(f"Sauvegarde conservée : {backup_catalog}")
        return 0

    except Exception as error:
        print(f"\nÉCHEC : {error}", file=sys.stderr)
        print("Restauration des seuls fichiers touchés par ce script…")

        if catalog_written:
            CATALOG.write_text(original_catalog, encoding="utf-8")
            print("Catalogue restauré.")

        if test_written and TEST.exists():
            TEST.unlink()
            print("Test créé par ce script supprimé.")

        print(f"Sauvegarde conservée : {backup_catalog}")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ARRÊT SÉCURISÉ : {exc}", file=sys.stderr)
        sys.exit(1)