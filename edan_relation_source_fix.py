#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EDAN — Correction ciblée de la provenance des relations.

Objectifs :
- Sauvegarder le moteur avant modification.
- Vérifier précisément le code à corriger.
- Uniformiser la source des relations en retirant
  la ponctuation finale.
- Exécuter les tests bilingues et les régressions.
- Vérifier TypeScript.
- Restaurer uniquement le fichier modifié si une
  validation échoue.

Aucun git reset, checkout, commit ou push.
Aucun autre fichier source n'est modifié.
"""

from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import time


TARGET = Path(
    "src/ai/understanding/universalRelationEngine.ts"
)

OLD = (
    "return clean(text.slice(start,end<text.length?end+1:end));"
)

NEW = (
    'return clean(text.slice(start,end<text.length?end+1:end))'
    '.replace(/[.!?;]+$/,"");'
)

TESTS = [
    (
        ["npx", "tsx",
         "test-understanding-bilingual-integration-independent.ts"],
        "Test indépendant de provenance bilingue",
    ),
    (
        ["npx", "tsx",
         "test-understanding-domain-bilingual-targeted.ts"],
        "Compréhension métier française et anglaise",
    ),
    (
        ["npx", "tsx", "test-domain-ranking-regression.ts"],
        "Régression du classement des domaines",
    ),
    (
        ["npx", "tsx", "test-domain-candidate-ranking.ts"],
        "Classement des candidats du catalogue",
    ),
    (
        ["npx", "tsc", "--noEmit"],
        "Vérification TypeScript",
    ),
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def section(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72, flush=True)


def run(command, cwd, title):
    section(title)
    print("$", " ".join(command), flush=True)

    try:
        result = subprocess.run(command, cwd=cwd, check=False)
    except OSError as exc:
        print("ERREUR :", exc)
        return False

    if result.returncode != 0:
        print("ÉCHEC : code de sortie", result.returncode)
        return False

    print("PASS :", title)
    return True


def main():
    backend = Path.cwd().resolve()

    if len(sys.argv) > 1:
        backend = Path(sys.argv[1]).expanduser().resolve()

    section("1. VÉRIFICATION DE L'ENVIRONNEMENT")

    print("Backend :", backend)

    if not (backend / "package.json").is_file():
        print("ARRÊT : package.json introuvable.")
        return 2

    target = backend / TARGET

    if not target.is_file():
        print("ARRÊT : moteur de relations introuvable.")
        return 2

    try:
        original = target.read_bytes()
        source = original.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print("ARRÊT : lecture impossible :", exc)
        return 2

    print("Fichier :", TARGET)
    print("SHA256 initial :", digest(original))

    section("2. VÉRIFICATION DU BLOC À CORRIGER")

    count = source.count(OLD)

    if count != 1:
        print("ARRÊT SÉCURISÉ : bloc attendu non unique.")
        print("Occurrences :", count)
        print("Aucune modification effectuée.")
        return 3

    section("3. SAUVEGARDE")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup_dir = (
        backend / ".edan-backups" / f"relation-source-{stamp}"
    )

    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
        backup = backup_dir / "universalRelationEngine.ts.before"
        shutil.copy2(target, backup)

        if backup.read_bytes() != original:
            print("ARRÊT : sauvegarde non conforme.")
            return 4

    except OSError as exc:
        print("ARRÊT : sauvegarde impossible :", exc)
        return 4

    print("Sauvegarde :", backup)
    print("SHA256 sauvegarde :", digest(backup.read_bytes()))

    section("4. APPLICATION DU CORRECTIF")

    corrected = source.replace(OLD, NEW, 1)

    try:
        target.write_text(
            corrected,
            encoding="utf-8",
            newline="",
        )
    except OSError as exc:
        print("ERREUR d'écriture :", exc)

        try:
            shutil.copy2(backup, target)
        except OSError as restore_exc:
            print("ERREUR CRITIQUE de restauration :", restore_exc)

        return 5

    print("Correction appliquée :", TARGET)
    print("SHA256 corrigé :", digest(target.read_bytes()))

    section("5. VALIDATIONS FONCTIONNELLES ET TECHNIQUES")

    for command, title in TESTS:
        if not run(command, backend, title):
            section("6. ÉCHEC — RESTAURATION SÉCURISÉE")

            try:
                shutil.copy2(backup, target)

                if target.read_bytes() != original:
                    print("ERREUR CRITIQUE : restauration incorrecte.")
                    print("Sauvegarde conservée :", backup)
                    return 10

            except OSError as exc:
                print("ERREUR CRITIQUE de restauration :", exc)
                print("Sauvegarde conservée :", backup)
                return 10

            print("Fichier restauré :", TARGET)
            print("SHA256 restauré :", digest(target.read_bytes()))
            print("Aucun autre fichier source n'a été restauré.")
            print("La correction n'est pas validée.")
            return 1

    section("6. RÉSULTAT")

    print("PASS : tous les tests obligatoires ont réussi.")
    print("Fichier modifié :", TARGET)
    print("Sauvegarde conservée :", backup)
    print("Aucun commit ou push effectué.")

    run(
        ["git", "status", "--short"],
        backend,
        "État Git final",
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterruption. Vérifie le fichier et sa sauvegarde.")
        sys.exit(130)