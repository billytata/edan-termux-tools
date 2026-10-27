#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EDAN — Correction globale du classement des domaines métier.

Objectifs :
1. Vérifier les fichiers et leurs empreintes avant toute modification.
2. Sauvegarder les fichiers concernés.
3. Renforcer la reconnaissance des domaines en français et en anglais.
4. Éviter que les paiements de loyers soient classés automatiquement en Finance.
5. Ajouter des alias métier utiles au catalogue.
6. Créer un test indépendant bilingue.
7. Exécuter les tests fonctionnels, les régressions et TypeScript.
8. Restaurer uniquement les fichiers modifiés par ce script si une validation échoue.

IMPORTANT :
- Le script s'arrête si les empreintes attendues ne correspondent pas.
- Il ne supprime pas les modifications préexistantes.
- Il ne prétend pas réussir si un test échoue.
"""

from pathlib import Path
from datetime import datetime
import hashlib
import re
import subprocess
import sys


# ============================================================
# 1. CONFIGURATION
# ============================================================

ROOT = Path.home() / "EDAN" / "backend"

CATALOG = ROOT / "src/ai/understanding/domainCatalog.ts"
UNDERSTANDING = ROOT / "src/ai/understanding/appUnderstanding.ts"

TEST = ROOT / "test-domain-catalog-global-correction-independent.ts"

EXPECTED_SHA256 = {
    CATALOG: (
        "ccbe136366c2c750b8176b209d93fdb21c06b440053d44ac072761134d4ba06c"
    ),
    UNDERSTANDING: (
        "ea36c1d882fd9912c467813257c0b0776fe8927cdcb668ca1e4fea887b45e4d4"
    ),
}

BACKUP_DIR = ROOT / ".edan-backups" / (
    "domain-catalog-global-v2-"
    + datetime.now().strftime("%Y%m%d-%H%M%S")
)


# ============================================================
# 2. TESTS INDÉPENDANTS
# ============================================================

TEST_CONTENT = r'''import assert from "node:assert/strict";

import {
  DOMAIN_CATALOG,
  findDomainCandidates,
  validateDomainCatalog,
} from "./src/ai/understanding/domainCatalog";

import {
  understandApp,
} from "./src/ai/understanding/appUnderstanding";


const catalogCases = [
  [
    "application de gestion des stocks",
    "gestion-stocks-generale",
  ],
  [
    "inventory management application",
    "gestion-stocks-generale",
  ],
  [
    "application bancaire",
    "finance-bancaire",
  ],
  [
    "banking application",
    "finance-bancaire",
  ],
  [
    "application de livraison de repas",
    "livraison-generale",
  ],
  [
    "food delivery app",
    "livraison-generale",
  ],
  [
    "application de gestion de chantier",
    "gestion-projets-construction",
  ],
  [
    "construction project management",
    "gestion-projets-construction",
  ],
] as const;


const understandingCases = [
  [
    "Créer une application de gestion locative pour gérer les propriétaires, les locataires, les contrats de location et les paiements des loyers.",
    "Gestion locative",
  ],
  [
    "Build a rental management app for landlords, tenants, leases and rent payments.",
    "Gestion locative",
  ],
] as const;


// Vérification structurelle du catalogue.

const validation = validateDomainCatalog();

assert.equal(
  validation.duplicateIds.length,
  0,
  "Identifiants dupliqués : " + validation.duplicateIds.join(", "),
);

assert.equal(
  validation.duplicateNames.length,
  0,
  "Noms dupliqués : " + validation.duplicateNames.join(", "),
);

assert.equal(
  validation.invalidEntries.length,
  0,
  "Entrées invalides : " + JSON.stringify(validation.invalidEntries),
);


// Vérification de la reconnaissance des domaines.

for (const [prompt, expectedId] of catalogCases) {
  const candidates = findDomainCandidates(prompt);

  assert.ok(
    candidates.some((candidate) => candidate.id === expectedId),
    "Candidat attendu absent pour : " + prompt
      + ". Candidats trouvés : "
      + candidates.map((candidate) => candidate.id).join(", "),
  );

  console.log("PASS catalogue : " + prompt);
}


// Vérification de la classification métier complète.

for (const [prompt, expectedDomain] of understandingCases) {
  const result = understandApp(prompt);

  assert.equal(
    result.domain,
    expectedDomain,
    "Domaine incorrect pour : " + prompt
      + ". Domaine obtenu : " + result.domain,
  );

  console.log("PASS compréhension : " + prompt);
}


// Vérification de la taille minimale attendue.

assert.ok(
  DOMAIN_CATALOG.length >= 221,
  "Catalogue potentiellement incomplet : " + DOMAIN_CATALOG.length,
);

console.log(
  "PASS validation du catalogue : "
  + DOMAIN_CATALOG.length
  + " domaines",
);

console.log(
  "PASS scénarios catalogue : " + catalogCases.length,
);

console.log(
  "PASS scénarios métier : " + understandingCases.length,
);
'''


# ============================================================
# 3. NOUVELLES ENTRÉES DU CATALOGUE
# ============================================================

NEW_ENTRIES = [
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
''' ,
]


# ============================================================
# 4. UTILITAIRES DE SÉCURITÉ
# ============================================================

def sha256(path: Path) -> str:
    """Calcule l'empreinte SHA-256 d'un fichier."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def run(command: list[str], label: str) -> None:
    """Exécute une commande et interrompt le processus en cas d'échec."""
    print("\n" + "=" * 72, flush=True)
    print(label, flush=True)
    print("$ " + " ".join(map(str, command)), flush=True)
    print("=" * 72, flush=True)

    result = subprocess.run(command, cwd=ROOT)

    if result.returncode != 0:
        raise RuntimeError(
            label
            + " a échoué avec le code "
            + str(result.returncode)
        )


def require_exactly_one(source: str, fragment: str, description: str) -> None:
    """Refuse une modification si le point d'insertion est ambigu."""
    count = source.count(fragment)

    if count != 1:
        raise RuntimeError(
            description
            + " : occurrence attendue = 1, occurrences trouvées = "
            + str(count)
        )


# ============================================================
# 5. AJOUT GARDÉ D'ALIAS
# ============================================================

def add_aliases(
    source: str,
    entry_id: str,
    aliases: list[str],
) -> str:
    """
    Ajoute des alias à une entrée existante sans remplacer
    ses alias actuels.
    """

    pattern = re.compile(
        r'(?P<head>\{\s*id:\s*"'
        + re.escape(entry_id)
        + r'"\s*,[\s\S]*?\baliases:\s*\[)'
        r'(?P<body>[\s\S]*?)'
        r'(?P<tail>\])'
    )

    matches = list(pattern.finditer(source))

    if len(matches) != 1:
        raise RuntimeError(
            "Entrée du catalogue absente ou ambiguë : "
            + entry_id
        )

    match = matches[0]
    body = match.group("body")

    existing = {
        value.casefold().strip()
        for value in re.findall(
            r'"((?:\\.|[^"\\])*)"',
            body,
        )
    }

    additions = [
        alias
        for alias in aliases
        if alias.casefold().strip() not in existing
    ]

    if not additions:
        print(
            "INFO : alias déjà présents pour "
            + entry_id
        )
        return source

    trimmed = body.rstrip()

    if not trimmed:
        separator = ""
    elif trimmed.endswith(","):
        separator = ""
    else:
        separator = ","

    new_body = (
        trimmed
        + separator
        + "\n"
        + "".join(
            '      "' + alias + '",\n'
            for alias in additions
        )
    )

    updated = (
        source[:match.start("body")]
        + new_body
        + source[match.end("body"):]
    )

    print(
        "ALIAS AJOUTÉS : "
        + entry_id
        + " : "
        + ", ".join(additions)
    )

    return updated


# ============================================================
# 6. AJOUT GARDÉ DE DOMAINES
# ============================================================

def add_new_entries(source: str) -> str:
    """Insère les nouvelles entrées au début du tableau du catalogue."""

    opening = re.search(
        r'export\s+const\s+DOMAIN_CATALOG'
        r'(?:\s*:\s*[^=]+)?\s*=\s*\[',
        source,
    )

    if not opening:
        raise RuntimeError(
            "Déclaration DOMAIN_CATALOG introuvable."
        )

    insertion_position = opening.end()
    additions = []

    for entry in NEW_ENTRIES:
        match = re.search(
            r'id:\s*"([^"]+)"',
            entry,
        )

        if not match:
            raise RuntimeError(
                "Une nouvelle entrée ne contient pas d'identifiant."
            )

        entry_id = match.group(1)

        if re.search(
            r'\bid:\s*"'
            + re.escape(entry_id)
            + r'"',
            source,
        ):
            print(
                "INFO : domaine déjà présent : "
                + entry_id
            )
            continue

        additions.append(entry)

    if not additions:
        return source

    return (
        source[:insertion_position]
        + "\n"
        + "\n".join(additions)
        + source[insertion_position:]
    )


# ============================================================
# 7. PRIORITÉ DE LA GESTION LOCATIVE
# ============================================================

def patch_understanding(source: str) -> str:
    """
    Reconnaît explicitement le domaine locatif avant le classement
    générique susceptible de confondre loyers et finance.
    """

    anchor = " const catalogCandidates = findDomainCandidates(idea);"

    require_exactly_one(
        source,
        anchor,
        "Point d'insertion de la priorité métier",
    )

    priority_code = r'''
 // Priorité métier ciblée : les marqueurs de gestion locative
 // doivent être interprétés dans leur contexte immobilier.
 // Les loyers et leur paiement ne suffisent pas à transformer
 // une application locative en application financière.
 const rentalDomainPattern = /\b(?:gestion\s+locative|application\s+de\s+gestion\s+locative|location\s+immobili[eè]re|gestion\s+des\s+locations|rental\s+management|property\s+rental\s+management|rental\s+property\s+management|landlords?\s+and\s+tenants?|tenants?\s+and\s+landlords?|lease\s+management|rent\s+collection|rent\s+payment\s+management)\b/i;

 if (rentalDomainPattern.test(normalizedText)) {
   return "Gestion locative";
 }

'''

    updated = source.replace(
        anchor,
        priority_code + anchor,
        1,
    )

    if updated == source:
        raise RuntimeError(
            "La priorité locative n'a pas été insérée."
        )

    return updated


# ============================================================
# 8. EXÉCUTION PRINCIPALE
# ============================================================

def main() -> int:
    print("=" * 72)
    print("EDAN — CORRECTION GLOBALE DU CLASSEMENT DES DOMAINES")
    print("=" * 72)

    if not ROOT.is_dir():
        raise RuntimeError(
            "Dossier EDAN introuvable : "
            + str(ROOT)
        )

    # Vérifier tous les fichiers avant la moindre modification.

    for path, expected_hash in EXPECTED_SHA256.items():
        if not path.is_file():
            raise RuntimeError(
                "Fichier requis introuvable : "
                + str(path)
            )

        actual_hash = sha256(path)

        print(
            "SHA-256 "
            + path.name
            + " : "
            + actual_hash
        )

        if actual_hash != expected_hash:
            raise RuntimeError(
                "Empreinte différente pour "
                + path.name
                + ".\nEmpreinte attendue : "
                + expected_hash
                + "\nEmpreinte actuelle : "
                + actual_hash
                + "\nArrêt sans aucune modification. "
                  "Un nouvel audit est nécessaire."
            )

    # Ne jamais écraser un test ou un travail préexistant.

    if TEST.exists():
        raise RuntimeError(
            "Le test indépendant existe déjà : "
            + str(TEST)
            + ". Le script refuse de l'écraser."
        )

    # Charger les originaux en mémoire.

    originals = {
        path: path.read_text(encoding="utf-8")
        for path in EXPECTED_SHA256
    }

    # Préparer les modifications en mémoire avant toute écriture.

    updated_catalog = originals[CATALOG]

    updated_catalog = add_aliases(
        updated_catalog,
        "immobilier-general",
        [
            "gestion locative",
            "application de gestion locative",
            "location immobilière",
            "gestion des locations immobilières",
            "rental management application",
            "landlord and tenant management",
        ],
    )

    updated_catalog = add_aliases(
        updated_catalog,
        "gestion-projets-construction",
        [
            "gestion de chantier",
            "application de gestion de chantier",
            "construction project management",
            "construction site management",
            "construction management",
        ],
    )

    updated_catalog = add_aliases(
        updated_catalog,
        "construction-batiments",
        [
            "gestion de construction",
            "building construction management",
            "building construction",
        ],
    )

    updated_catalog = add_aliases(
        updated_catalog,
        "commerce-general",
        [
            "gestion des stocks commerciaux",
            "commercial and inventory management",
            "retail inventory management",
            "sales and inventory management",
        ],
    )

    updated_catalog = add_new_entries(
        updated_catalog
    )

    updated_understanding = patch_understanding(
        originals[UNDERSTANDING]
    )

    if updated_catalog == originals[CATALOG]:
        raise RuntimeError(
            "Aucune modification du catalogue préparée. "
            "Arrêt sécurisé."
        )

    if updated_understanding == originals[UNDERSTANDING]:
        raise RuntimeError(
            "Aucune modification de la compréhension préparée. "
            "Arrêt sécurisé."
        )

    # Créer les sauvegardes avant de toucher aux sources.

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=False,
    )

    backups = {}

    for path, original_text in originals.items():
        backup_path = BACKUP_DIR / (
            path.name + ".before"
        )

        backup_path.write_text(
            original_text,
            encoding="utf-8",
        )

        # Vérifier que la sauvegarde est identique à l'original.

        if sha256(backup_path) != sha256(path):
            raise RuntimeError(
                "Vérification de sauvegarde échouée : "
                + str(backup_path)
            )

        backups[path] = backup_path

    print("\nSauvegardes créées :")

    for original_path, backup_path in backups.items():
        print(
            str(original_path)
            + " -> "
            + str(backup_path)
        )

    changed_files = []
    test_created = False

    try:
        # Écriture du catalogue.

        CATALOG.write_text(
            updated_catalog,
            encoding="utf-8",
        )
        changed_files.append(CATALOG)

        # Écriture du moteur de compréhension.

        UNDERSTANDING.write_text(
            updated_understanding,
            encoding="utf-8",
        )
        changed_files.append(UNDERSTANDING)

        # Création du test indépendant.

        TEST.write_text(
            TEST_CONTENT,
            encoding="utf-8",
        )
        test_created = True

        # Vérification des fichiers effectivement écrits.

        if CATALOG.read_text(encoding="utf-8") != updated_catalog:
            raise RuntimeError(
                "Le contenu du catalogue après écriture est incorrect."
            )

        if UNDERSTANDING.read_text(encoding="utf-8") != updated_understanding:
            raise RuntimeError(
                "Le contenu du moteur après écriture est incorrect."
            )

        print("\nFichiers modifiés :")
        print(" - " + str(CATALOG))
        print(" - " + str(UNDERSTANDING))
        print(" - " + str(TEST))

        # Tests indépendants, fonctionnels et régressions.

        checks = [
            (
                ["npx", "tsx", TEST.name],
                "Test indépendant catalogue et compréhension bilingue",
            ),
            (
                ["npx", "tsx", "test-domain-catalog-integration.ts"],
                "Intégration cardiologie, gestion locative et réparation",
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
                [
                    "npx",
                    "tsx",
                    "test-understanding-domain-bilingual-targeted.ts",
                ],
                "Compréhension bilingue ciblée",
            ),
            (
                [
                    "npx",
                    "tsx",
                    "test-understanding-bilingual-integration-independent.ts",
                ],
                "Intégration bilingue indépendante",
            ),
            (
                [
                    "npx",
                    "tsx",
                    "test-understanding-multidomain.ts",
                ],
                "Compréhension multidomaine",
            ),
            (
                [
                    "npx",
                    "tsx",
                    "test-relations-multidomain-independent.ts",
                ],
                "Régression des relations multidomaines",
            ),
            (
                ["npx", "tsc", "--noEmit"],
                "Vérification TypeScript complète",
            ),
        ]

        for command, label in checks:
            run(
                command,
                label,
            )

        print("\n" + "=" * 72)
        print("SUCCÈS : toutes les validations ont réussi.")
        print("Les sauvegardes sont conservées.")
        print("Répertoire : " + str(BACKUP_DIR))
        print("=" * 72)

        return 0

    except Exception as error:
        print(
            "\nÉCHEC : "
            + str(error),
            file