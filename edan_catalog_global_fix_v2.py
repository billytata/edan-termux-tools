#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EDAN — Correction ciblée de la classification des domaines.
Version 2 : Gestion locative, français et anglais.

Fonctionnalités :
- Vérification stricte des empreintes des fichiers.
- Sauvegarde avant modification.
- Ajout d'alias immobiliers au catalogue.
- Priorité métier pour la gestion locative.
- Tests fonctionnels et tests de régression.
- Vérification TypeScript.
- Restauration des fichiers modifiés si les validations échouent.

Exécution depuis ~/EDAN/backend :
python3 ~/edan_catalog_global_fix_v2.py
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT = Path.home() / "EDAN" / "backend"

CATALOG_REL = Path("src/ai/understanding/domainCatalog.ts")
UNDERSTANDING_REL = Path("src/ai/understanding/appUnderstanding.ts")

EXPECTED_SHA256 = {
    CATALOG_REL: (
        "ccbe136366c2c750b8176b209d93fdb21c06b440053d44ac072761134d4ba06c"
    ),
    UNDERSTANDING_REL: (
        "ea36c1d882fd9912c467813257c0b0776fe8927cdcb668ca1e4fea887b45e4d4"
    ),
}

TEST_REL = Path(".tmp-edan-domain-global-fix-v2.ts")

ALIASES = [
    "gestion locative",
    "application de gestion locative",
    "gestion des locations",
    "gestion de biens locatifs",
    "gestion immobilière locative",
    "gestion des loyers",
    "gestion des propriétaires et des locataires",
    "location immobilière",
    "application de location immobilière",
    "rental management",
    "property rental management",
    "rental property management",
    "lease management",
    "landlord and tenant management",
    "rent collection management",
]

RENTAL_PATTERN = r"""(?ix)
\b(?:
    gestion\s+locative
    | application\s+de\s+gestion\s+locative
    | gestion\s+des\s+locations
    | gestion\s+de\s+biens\s+locatifs
    | gestion\s+immobili[eè]re\s+locative
    | location\s+immobili[eè]re
    | application\s+de\s+location\s+immobili[eè]re
    | gestion\s+des\s+propri[eé]taires\s+et\s+des\s+locataires
    | rental\s+management
    | property\s+rental\s+management
    | rental\s+property\s+management
    | lease\s+management
    | landlord\s+and\s+tenant\s+management
    | rent\s+collection\s+management
)\b
"""


def log(message: str) -> None:
    print(f"[EDAN] {message}", flush=True)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_command(command: list[str], description: str) -> None:
    log(f"Vérification : {description}")
    result = subprocess.run(
        command,
        cwd=PROJECT,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Échec : {description} (code {result.returncode})."
        )


def add_aliases_to_catalog(source: str) -> str:
    """
    Ajoute les alias à l'entrée immobilier-general.
    Refuse de modifier le fichier si la structure attendue est absente.
    """

    marker = re.search(
        r"""\bid\s*:\s*["']immobilier-general["']""",
        source,
    )

    if not marker:
        raise RuntimeError(
            "Entrée 'immobilier-general' introuvable dans domainCatalog.ts."
        )

    next_entry = re.search(
        r"""\bid\s*:\s*["'][^"']+["']""",
        source[marker.end():],
    )

    entry_end = (
        marker.end() + next_entry.start()
        if next_entry
        else len(source)
    )

    entry = source[marker.start():entry_end]

    aliases_match = re.search(
        r"""\baliases\s*:\s*\[""",
        entry,
    )

    if not aliases_match:
        raise RuntimeError(
            "Tableau aliases introuvable dans l'entrée immobilier-general."
        )

    opening_bracket = entry.find(
        "[",
        aliases_match.start(),
    )

    # Recherche de la fermeture du tableau sans confondre
    # les crochets présents dans les chaînes.
    quote = None
    escaped = False
    closing_bracket = None

    for index in range(opening_bracket, len(entry)):
        char = entry[index]

        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in ("'", '"', "`"):
            quote = char
        elif char == "]":
            closing_bracket = index
            break

    if closing_bracket is None:
        raise RuntimeError(
            "Impossible de trouver la fin du tableau aliases."
        )

    existing_array = entry[opening_bracket + 1:closing_bracket]

    existing_normalized = {
        value.casefold()
        for value in re.findall(
            r"""["']([^"']+)["']""",
            existing_array,
        )
    }

    missing = [
        alias
        for alias in ALIASES
        if alias.casefold() not in existing_normalized
    ]

    if not missing:
        log("Les alias locatifs sont déjà présents dans le catalogue.")
        return source

    insertion = "".join(
        f'\n      "{alias}",'
        for alias in missing
    )

    new_entry = (
        entry[:closing_bracket]
        + insertion
        + "\n    "
        + entry[closing_bracket:]
    )

    return (
        source[:marker.start()]
        + new_entry
        + source[entry_end:]
    )


def add_rental_priority(source: str) -> str:
    """
    Priorise le domaine locatif avant le classement générique.
    Les termes financiers comme paiement ou loyer ne doivent pas,
    à eux seuls, transformer une application locative en application
    financière.
    """

    marker = "const catalogCandidates = findDomainCandidates(idea);"

    if marker not in source:
        raise RuntimeError(
            "Point d'insertion introuvable dans appUnderstanding.ts. "
            "Aucune modification automatique ne sera tentée."
        )

    if "EDAN_RENTAL_DOMAIN_PRIORITY_V2" in source:
        log("La priorité locative est déjà présente.")
        return source

    insertion = r'''
  // EDAN_RENTAL_DOMAIN_PRIORITY_V2
  // Priorité métier : la gestion locative reste un domaine immobilier.
  // Les loyers et leurs paiements ne suffisent pas à classer
  // une application locative dans le domaine financier.
  const rentalDomainPattern = /''' + RENTAL_PATTERN + r'''/;

  if (rentalDomainPattern.test(normalizedText)) {
    return "Gestion locative";
  }

'''

    return source.replace(
        marker,
        insertion + "  " + marker,
        1,
    )


TEST_CONTENT = r'''
import { strict as assert } from "node:assert";
import { findDomainCandidates } from "./src/ai/understanding/domainCatalog";
import { understandApp } from "./src/ai/understanding/appUnderstanding";

async function main() {
  const catalogCases = [
    "gestion locative",
    "application de gestion locative",
    "gestion des locations",
    "gestion de biens locatifs",
    "location immobilière",
    "rental management",
    "property rental management",
    "rental property management",
    "lease management",
  ];

  for (const phrase of catalogCases) {
    const candidates = findDomainCandidates(phrase);
    assert.ok(
      candidates.some((candidate: { name: string }) =>
        /immobilier|locatif|location/i.test(candidate.name)
      ),
      `Le catalogue ne reconnaît pas le domaine immobilier pour : ${phrase}`
    );
  }

  const understandingCases = [
    {
      prompt:
        "Créer une application de gestion locative pour gérer les propriétaires, les locataires, les contrats et les paiements des loyers.",
      expected: "Gestion locative",
    },
    {
      prompt:
        "Build a rental management application to manage landlords, tenants, leases and rent payments.",
      expected: "Gestion locative",
    },
  ];

  for (const testCase of understandingCases) {
    const result = await understandApp(testCase.prompt);

    assert.equal(
      result.domain,
      testCase.expected,
      `Prompt=${JSON.stringify(testCase.prompt)}, obtenu=${JSON.stringify(result.domain)}`
    );
  }

  console.log("SUCCÈS : tests ciblés du domaine locatif.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
'''


def main() -> int:
    if not PROJECT.is_dir():
        log(f"ERREUR : projet introuvable : {PROJECT}")
        return 1

    if Path.cwd().resolve() != PROJECT.resolve():
        log(f"Placez-vous d'abord dans : {PROJECT}")
        return 1

    paths = {
        relative: PROJECT / relative
        for relative in EXPECTED_SHA256
    }

    for relative, path in paths.items():
        if not path.is_file():
            log(f"ERREUR : fichier requis absent : {relative}")
            return 1

        actual = sha256(path.read_bytes())
        expected = EXPECTED_SHA256[relative]

        if actual != expected:
            log(f"ARRÊT DE SÉCURITÉ : empreinte différente pour {relative}")
            log(f"Attendue : {expected}")
            log(f"Obtenue  : {actual}")
            log(
                "Aucun fichier EDAN n'a été modifié. "
                "Les empreintes doivent être réexaminées."
            )
            return 1

    log("Empreintes vérifiées.")

    originals = {
        relative: path.read_text(encoding="utf-8")
        for relative, path in paths.items()
    }

    if TEST_REL.exists():
        log(
            f"ARRÊT : {TEST_REL} existe déjà. "
            "Le script ne l'écrasera pas."
        )
        return 1

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = PROJECT / ".edan-backups" / f"domain-global-v2-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for relative, path in paths.items():
        backup_path = backup_dir / relative.name
        shutil.copy2(path, backup_path)
        log(f"Sauvegarde : {backup_path}")

    changed = []
    test_created = False

    try:
        catalog = add_aliases_to_catalog(originals[CATALOG_REL])
        understanding = add_rental_priority(
            originals[UNDERSTANDING_REL]
        )

        if catalog == originals[CATALOG_REL]:
            log("Aucun alias nouveau à ajouter au catalogue.")
        else:
            paths[CATALOG_REL].write_text(
                catalog,
                encoding="utf-8",
            )
            changed.append(CATALOG_REL)
            log("Catalogue immobilier mis à jour.")

        if understanding != originals[UNDERSTANDING_REL]:
            paths[UNDERSTANDING_REL].write_text(
                understanding,
                encoding="utf-8",
            )
            changed.append(UNDERSTANDING_REL)
            log("Priorité du domaine locatif ajoutée.")

        TEST_REL_PATH = PROJECT / TEST_REL
        TEST_REL_PATH.write_text(
            TEST_CONTENT.strip() + "\n",
            encoding="utf-8",
        )
        test_created = True

        run_command(
            ["npx", "tsx", str(TEST_REL)],
            "tests fonctionnels locatifs français et anglais",
        )

        regression_tests = [
            "test-domain-catalog-integration.ts",
            "test-domain-ranking-regression.ts",
            "test-domain-candidate-ranking.ts",
            "test-understanding-domain-bilingual-targeted.ts",
            "test-understanding-bilingual-integration-independent.ts",
            "test-understanding-multidomain.ts",
            "test-relations-multidomain-independent.ts",
        ]

        for test_name in regression_tests:
            test_path = PROJECT / test_name
            if test_path.is_file():
                run_command(
                    ["npx", "tsx", test_name],
                    f"test de régression {test_name}",
                )
            else:
                log(f"TEST NON DISPONIBLE : {test_name}")

        run_command(
            ["npx", "tsc", "--noEmit"],
            "vérification TypeScript npx tsc --noEmit",
        )

        if test_created:
            TEST_REL_PATH.unlink(missing_ok=True)
            test_created = False

        log("SUCCÈS : toutes les validations exécutées ont réussi.")
        log(f"Sauvegardes conservées dans : {backup_dir}")
        return 0

    except Exception as error:
        log(f"ÉCHEC : {error}")
        log("Restauration des fichiers modifiés...")

        for relative in reversed(changed):
            backup_path = backup_dir / relative.name
            if backup_path.is_file():
                shutil.copy2(backup_path, paths[relative])
                log(f"Restauré : {relative}")

        if test_created:
            (PROJECT / TEST_REL).unlink(missing_ok=True)

        log("Restauration terminée. Les sauvegardes sont conservées.")
        return 1


if __name__ == "__main__":
    sys.exit(main())