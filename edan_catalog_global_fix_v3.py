#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EDAN — Correction ciblée de la détection du domaine Gestion locative.

Fonctions :
1. Vérifie les empreintes des sources.
2. Crée des sauvegardes horodatées.
3. Ajoute des alias locatifs au catalogue.
4. Ajoute une priorité métier française/anglaise.
5. Exécute un test fonctionnel dédié.
6. Exécute les tests de régression disponibles.
7. Exécute npx tsc --noEmit.
8. Restaure les sources modifiées par ce script en cas d'échec.
"""

from pathlib import Path
from datetime import datetime
import hashlib
import subprocess
import sys

ROOT = Path.home() / "EDAN" / "backend"

CATALOG = ROOT / "src/ai/understanding/domainCatalog.ts"
UNDERSTANDING = ROOT / "src/ai/understanding/appUnderstanding.ts"

EXPECTED_HASHES = {
    CATALOG: (
        "ccbe136366c2c750b8176b209d93fdb21c06b440053d44ac072761134d4ba06c"
    ),
    UNDERSTANDING: (
        "ea36c1d882fd9912c467813257c0b0776fe8927cdcb668ca1e4fea887b45e4d4"
    ),
}

ALIASES = [
    "gestion locative",
    "application de gestion locative",
    "gestion des locations",
    "gestion de biens locatifs",
    "location immobilière",
    "gestion des loyers",
    "rental management",
    "property rental management",
    "rental property management",
    "lease management",
    "landlord and tenant management",
    "rent collection management",
]

PRIORITY_MARKER = "EDAN_RENTAL_DOMAIN_PRIORITY_V3"

PRIORITY_BLOCK = '''  // EDAN_RENTAL_DOMAIN_PRIORITY_V3
  // Priorité métier : les paiements de loyers ne doivent pas
  // faire classer une application locative dans Finance.
  const rentalDomainTerms = [
    "gestion locative",
    "application de gestion locative",
    "gestion des locations",
    "gestion de biens locatifs",
    "location immobiliere",
    "gestion des loyers",
    "rental management",
    "property rental management",
    "rental property management",
    "landlord and tenant management",
    "rent collection management",
    "lease management",
    "rental property",
    "property rentals"
  ];

  if (rentalDomainTerms.some(term => normalizedText.includes(term))) {
    return "Gestion locative";
  }

'''

REGRESSION_TESTS = [
    "test-domain-catalog-integration.ts",
    "test-domain-ranking-regression.ts",
    "test-domain-candidate-ranking.ts",
    "test-understanding-domain-bilingual-targeted.ts",
    "test-understanding-bilingual-integration-independent.ts",
    "test-understanding-multidomain.ts",
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute(command, label):
    print(f"\n=== {label} ===", flush=True)
    print("$ " + " ".join(command), flush=True)

    result = subprocess.run(command, cwd=ROOT)

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} a échoué avec le code {result.returncode}."
        )


def add_aliases(source):
    marker = 'id: "immobilier-general"'
    start = source.find(marker)

    if start < 0:
        raise RuntimeError(
            'Entrée id: "immobilier-general" introuvable.'
        )

    aliases_pos = source.find("aliases:", start)

    if aliases_pos < 0:
        raise RuntimeError("Champ aliases introuvable.")

    opening = source.find("[", aliases_pos)

    if opening < 0:
        raise RuntimeError("Ouverture du tableau aliases introuvable.")

    # Recherche de la fermeture du tableau.
    depth = 0
    quote = None
    escaped = False
    closing = -1

    for index in range(opening, len(source)):
        char = source[index]

        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in ('"', "'", "`"):
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1

            if depth == 0:
                closing = index
                break

    if closing < 0:
        raise RuntimeError("Fermeture du tableau aliases introuvable.")

    body = source[opening + 1:closing]

    existing = {
        item.strip().casefold()
        for item in __import__("re").findall(
            r"""["']([^"']*)["']""", body
        )
    }

    missing = [
        alias for alias in ALIASES
        if alias.casefold() not in existing
    ]

    if not missing:
        print("Catalogue : alias locatifs déjà présents.")
        return source, False

    # Ajouter les alias avant la fermeture, sans réécrire
    # les éléments déjà présents.
    trimmed = body.rstrip()

    if trimmed.strip() and not trimmed.endswith(","):
        trimmed += ","

    if trimmed.strip():
        trimmed += "\n"

    trimmed += "\n".join(
        f'    "{alias}",' for alias in missing
    )

    trimmed += "\n  "

    result = (
        source[:opening + 1]
        + "\n"
        + trimmed
        + source[closing:]
    )

    return result, True


def main():
    if not ROOT.is_dir():
        print(f"ERREUR : dépôt introuvable : {ROOT}")
        return 2

    if not CATALOG.is_file() or not UNDERSTANDING.is_file():
        print("ERREUR : une ou plusieurs sources sont absentes.")
        return 2

    print("=== 1. Vérification des empreintes ===")

    for path, expected in EXPECTED_HASHES.items():
        actual = sha256(path)

        print(f"\nFichier : {path.relative_to(ROOT)}")
        print(f"SHA256 actuel : {actual}")

        if actual != expected:
            print("\nARRÊT DE SÉCURITÉ.")
            print("Le fichier a changé depuis l'audit précédent.")
            print("Aucune source n'a été modifiée.")
            print("Il faut réexaminer les fichiers avant de continuer.")
            return 3

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = (
        ROOT / ".edan-backups" / f"domain-global-v3-{stamp}"
    )

    backup_dir.mkdir(parents=True, exist_ok=False)

    original_catalog = CATALOG.read_bytes()
    original_understanding = UNDERSTANDING.read_bytes()

    (backup_dir / "domainCatalog.ts").write_bytes(
        original_catalog
    )
    (backup_dir / "appUnderstanding.ts").write_bytes(
        original_understanding
    )

    print(f"\nSauvegardes créées : {backup_dir}")

    changed_catalog = False
    changed_understanding = False
    temporary_test = ROOT / ".tmp-edan-domain-global-fix-v3.ts"

    try:
        if temporary_test.exists():
            raise RuntimeError(
                f"Le fichier temporaire existe déjà : {temporary_test}. "
                "Le script refuse de l'écraser."
            )

        catalog_source = CATALOG.read_text(encoding="utf-8")
        understanding_source = UNDERSTANDING.read_text(
            encoding="utf-8"
        )

        # Étape 1 : catalogue.
        patched_catalog, catalog_changed = add_aliases(
            catalog_source
        )

        if catalog_changed:
            CATALOG.write_text(
                patched_catalog, encoding="utf-8"
            )
            changed_catalog = True
            print("Catalogue immobilier/locatif corrigé.")

        # Étape 2 : priorité métier dans la compréhension.
        if PRIORITY_MARKER not in understanding_source:
            anchor = (
                "  const catalogCandidates = "
                "findDomainCandidates(idea);"
            )

            if understanding_source.count(anchor) != 1:
                raise RuntimeError(
                    "Point d'insertion absent ou ambigu dans "
                    "appUnderstanding.ts."
                )

            patched_understanding = understanding_source.replace(
                anchor,
                PRIORITY_BLOCK + anchor,
                1,
            )

            UNDERSTANDING.write_text(
                patched_understanding, encoding="utf-8"
            )
            changed_understanding = True
            print("Priorité de domaine Gestion locative ajoutée.")
        else:
            print("Priorité Gestion locative déjà présente.")

        # Étape 3 : test fonctionnel autonome.
        test_code = r'''
import { strict as assert } from "node:assert";
import { understandApp } from "./src/ai/understanding/appUnderstanding";

const french =
  "Créer une application de gestion locative pour gérer les propriétaires, les locataires, les contrats et les paiements des loyers.";

const english =
  "Build a rental management application to manage landlords, tenants, lease agreements and rent payments.";

const frenchResult = understandApp(french);
const englishResult = understandApp(english);

assert.equal(
  frenchResult.domain,
  "Gestion locative",
  `Domaine français incorrect : ${String(frenchResult.domain)}`
);

assert.equal(
  englishResult.domain,
  "Gestion locative",
  `Domaine anglais incorrect : ${String(englishResult.domain)}`
);

console.log("PASS : prompt français ->", frenchResult.domain);
console.log("PASS : prompt anglais ->", englishResult.domain);
'''

        temporary_test.write_text(test_code, encoding="utf-8")

        execute(
            ["npx", "tsx", str(temporary_test)],
            "Test fonctionnel Gestion locative FR/EN",
        )

        # Étape 4 : régressions présentes dans le dépôt.
        for test_name in REGRESSION_TESTS:
            test_path = ROOT / test_name

            if test_path.is_file():
                execute(
                    ["npx", "tsx", test_name],
                    f"Régression {test_name}",
                )
            else:
                print(
                    f"TEST ABSENT — ignoré : {test_name}",
                    flush=True,
                )

        # Étape 5 : compilation TypeScript.
        execute(
            ["npx", "tsc", "--noEmit"],
            "Contrôle TypeScript",
        )

        print("\nSUCCÈS : toutes les validations exécutées ont réussi.")
        print(f"Sauvegardes conservées : {backup_dir}")
        return 0

    except Exception as error:
        print(f"\nÉCHEC : {error}", file=sys.stderr)
        print("Restauration des fichiers touchés…", file=sys.stderr)

        if changed_catalog:
            CATALOG.write_bytes(original_catalog)
            print("Restauré : domainCatalog.ts", file=sys.stderr)

        if changed_understanding:
            UNDERSTANDING.write_bytes(original_understanding)
            print("Restauré : appUnderstanding.ts", file=sys.stderr)

        print(f"Sauvegardes conservées : {backup_dir}", file=sys.stderr)
        return 1

    finally:
        if temporary_test.exists():
            temporary_test.unlink()


if __name__ == "__main__":
    sys.exit(main())