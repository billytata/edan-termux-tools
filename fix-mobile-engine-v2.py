#!/usr/bin/env python3
"""
EDAN — Mobile Engine Repair V2

Fichier : scripts/fix-mobile-engine-v2.py

Objectifs :
- sauvegarder les fichiers avant correction ;
- corriger le défaut confirmé de normalisation des routes ;
- sécuriser les chaînes Dart générées par le générateur de pages ;
- vérifier les modifications avant de les conserver ;
- préserver les modifications préexistantes du dépôt ;
- exécuter TypeScript et des tests ciblés.

Important :
Cette version ne prétend pas résoudre automatiquement tous les défauts
métier du moteur mobile. Les autres corrections nécessitent des tests
fonctionnels adaptés aux contrats réels du générateur.
"""

from __future__ import annotations

import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

RUNTIME_FILE = Path("src/generator/runtime.ts")
PAGE_FILE = Path("src/generator/full/mobilePageGenerator.ts")

TARGET_FILES = [
    RUNTIME_FILE,
    PAGE_FILE,
]


class RepairError(Exception):
    """Erreur contrôlée pendant le correctif."""


def execute(
    command: list[str],
    *,
    required: bool = True,
) -> bool:
    """Exécute une commande dans le backend EDAN."""

    print("\n$", " ".join(command), flush=True)

    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
    )

    if result.returncode == 0:
        return True

    message = (
        f"Commande échouée, code {result.returncode} : "
        + " ".join(command)
    )

    print(f"\nERREUR : {message}")

    if required:
        raise RepairError(message)

    return False


def read_text(path: Path) -> str:
    """Lit un fichier UTF-8 existant."""

    absolute = ROOT / path

    if not absolute.is_file():
        raise RepairError(f"Fichier introuvable : {path}")

    return absolute.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Écrit un fichier UTF-8."""

    absolute = ROOT / path
    absolute.write_text(content, encoding="utf-8")


def backup_files() -> tuple[Path, dict[Path, bytes]]:
    """Crée une sauvegarde indépendante des fichiers ciblés."""

    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

    backup_dir = (
        ROOT
        / ".edan-backups"
        / f"mobile-engine-v2-{stamp}"
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    originals: dict[Path, bytes] = {}

    for relative in TARGET_FILES:
        source = ROOT / relative

        if not source.is_file():
            raise RepairError(
                f"Fichier requis absent : {relative}"
            )

        original = source.read_bytes()
        originals[relative] = original

        destination = backup_dir / relative
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(source, destination)

        print(f"Sauvegarde créée : {relative}")

    return backup_dir, originals


def restore_files(originals: dict[Path, bytes]) -> None:
    """Restaure uniquement les fichiers ciblés par ce script."""

    print("\n=== RESTAURATION DES FICHIERS CIBLÉS ===")

    for relative, original in originals.items():
        destination = ROOT / relative
        destination.write_bytes(original)
        print(f"Restauré : {relative}")


def fix_runtime_route_normalization() -> bool:
    """
    Corrige uniquement la forme reconnue de la regex.

    La forme erronée recherche littéralement '\\s' au lieu des espaces.
    Si le code est différent, le script ne tente pas de le deviner.
    """

    content = read_text(RUNTIME_FILE)

    incorrect = r'replace(/\\s+/g, "-")'
    correct = r'replace(/\s+/g, "-")'

    if incorrect in content:
        content = content.replace(
            incorrect,
            correct,
            1,
        )

        write_text(RUNTIME_FILE, content)

        print(
            "CORRIGÉ : normalisation des espaces dans runtime.ts"
        )

        return True

    if correct in content:
        print(
            "OK : la regex de normalisation est déjà correcte."
        )

        return False

    print(
        "NON MODIFIÉ : la regex attendue n'a pas été reconnue."
    )

    return False


def fix_dart_string_escaping() -> bool:
    """
    Ajoute un encodeur Dart et remplace l'échappement fragile
    des apostrophes dans mobilePageGenerator.ts.

    Le correctif s'arrête si la structure attendue n'est pas reconnue.
    """

    content = read_text(PAGE_FILE)

    helper_name = "function dartStringLiteral("

    if helper_name in content:
        print(
            "OK : le générateur possède déjà dartStringLiteral()."
        )
        return False

    marker = (
        'function className(value:string):string{'
    )

    if marker not in content:
        raise RepairError(
            "Structure de mobilePageGenerator.ts non reconnue ; "
            "aucune modification de ce fichier effectuée."
        )

    helper = r'''
function dartStringLiteral(value: string): string {
  // JSON produit une chaîne doublement citée compatible avec Dart
  // pour les caractères usuels, guillemets, retours à la ligne
  // et barres obliques inverses.
  return JSON.stringify(value)
    .replace(/\$/g, "\\$");
}

'''

    content = content.replace(
        marker,
        helper + marker,
        1,
    )

    old_expression = r"${page.replace(/'/g,\"\\'\")}"

    if old_expression not in content:
        # Le fichier a pu évoluer ; ne pas écrire une modification
        # partielle qui ajouterait un helper non utilisé.
        raise RepairError(
            "Expression d'échappement Dart non reconnue. "
            "Le fichier sera restauré par le mécanisme de sécurité."
        )

    content = content.replace(
        old_expression,
        "${dartStringLiteral(page)}",
    )

    write_text(PAGE_FILE, content)

    print(
        "CORRIGÉ : échappement des chaînes Dart dans "
        "mobilePageGenerator.ts"
    )

    return True


def check_generator_presence() -> None:
    """Vérifie que les principaux générateurs mobiles existent."""

    required_files = [
        Path("src/generator/full/mobilePageGenerator.ts"),
        Path("src/generator/full/mobileNavigationGenerator.ts"),
        Path("src/generator/full/mobileNavigationFileGenerator.ts"),
        Path("src/generator/full/mobileFileGenerator.ts"),
        Path("src/generator/full/fullGenerationRunner.ts"),
        Path("src/generator/runtimeBuilder.ts"),
        Path("src/generator/runtimeTypes.ts"),
    ]

    print("\n=== VÉRIFICATION DES GÉNÉRATEURS ===")

    missing = []

    for relative in required_files:
        if (ROOT / relative).is_file():
            print(f"OK      : {relative}")
        else:
            print(f"MANQUANT: {relative}")
            missing.append(relative)

    if missing:
        raise RepairError(
            "Des fichiers nécessaires au moteur mobile sont absents."
        )


def main() -> int:
    print("=" * 64)
    print("EDAN — CORRECTEUR DU MOTEUR MOBILE V2")
    print("=" * 64)
    print(f"Backend : {ROOT}")

    if not (ROOT / "package.json").is_file():
        raise RepairError(
            "package.json introuvable : vérifie le dossier du backend."
        )

    check_generator_presence()

    print("\n=== ÉTAT GIT INITIAL ===")
    execute(
        ["git", "status", "--short"],
        required=False,
    )

    print("\n=== SAUVEGARDE ===")
    backup_dir, originals = backup_files()

    print(f"\nSauvegardes : {backup_dir}")

    try:
        print("\n=== CORRECTIONS CIBLÉES ===")

        runtime_changed = fix_runtime_route_normalization()
        page_changed = fix_dart_string_escaping()

        print("\n=== CONTRÔLE TYPESCRIPT ===")
        execute(["npx", "tsc", "--noEmit"])

        print("\n=== CONTRÔLE DES ESPACES ET PATCHES GIT ===")
        execute(["git", "diff", "--check"])

        print("\n=== BILAN ===")
        print(
            "Regex runtime modifiée : "
            + ("oui" if runtime_changed else "non")
        )
        print(
            "Chaînes Dart modifiées : "
            + ("oui" if page_changed else "non")
        )
        print("TypeScript : PASS")
        print("git diff --check : PASS")
        print("Sauvegardes conservées.")

        print(
            "\nATTENTION : ces contrôles ne prouvent pas à eux seuls "
            "que les applications Flutter générées sont fonctionnelles."
        )
        print(
            "Les tests de navigation, formulaires, actions et API "
            "doivent encore être exécutés."
        )
        print(
            "\nAucun commit Git n'a été créé automatiquement."
        )

        return 0

    except Exception:
        restore_files(originals)

        print(
            "\nÉCHEC : les fichiers ciblés ont été restaurés."
        )

        raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RepairError, OSError, UnicodeError) as error:
        print(
            f"\nÉCHEC DU CORRECTIF : {error}",
            file=sys.stderr,
        )
        sys.exit(1)