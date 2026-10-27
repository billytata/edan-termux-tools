#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EDAN — Correction sécurisée du classement des domaines.

Fonctions :
1. Vérifier le dépôt et le fichier cible.
2. Sauvegarder le fichier avant modification.
3. Refuser toute modification si le code attendu est absent ou ambigu.
4. Corriger le reclassement redondant des candidats.
5. Exécuter les tests fonctionnels et de régression.
6. Vérifier TypeScript.
7. Restaurer le fichier modifié par ce script en cas d'échec.

Le script ne fait ni git reset, ni checkout, ni commit, ni push.
Il ne supprime pas les modifications préexistantes.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path


TARGET_REL = Path("src/ai/understanding/appUnderstanding.ts")


OLD_BLOCK = r''' const catalogCandidates = findDomainCandidates(idea);
 if (catalogCandidates.length > 0) {
  const candidateMatchLength = (entry: (typeof catalogCandidates)[number]) =>
   [entry.name, ...entry.aliases].reduce((best, term) => {
    const normalizedTerm = lower(term)
     .normalize("NFD")
     .replace(/[\u0300-\u036f]/g, "")
     .replace(/[^a-z0-9]+/g, " ")
     .trim();

    const normalizedIdea = normalizedText
     .replace(/[^a-z0-9]+/g, " ")
     .trim();

    return normalizedIdea.includes(normalizedTerm)
     ? Math.max(best, normalizedTerm.length)
     : best;
   }, 0);

  return [...catalogCandidates]
   .sort((a, b) => candidateMatchLength(b) - candidateMatchLength(a))[0].name;
 }
'''


NEW_BLOCK = r''' const catalogCandidates = findDomainCandidates(idea);
 if (catalogCandidates.length > 0) {
  // Le catalogue centralise deja le classement des candidats.
  // Ne pas le remplacer par un second classement par longueur de sous-chaine :
  // ce second classement peut contredire les priorites du catalogue.
  return catalogCandidates[0].name;
 }
'''


TESTS = [
    (
        ["npx", "tsx", "test-domain-ranking-regression.ts"],
        "Régression du classement du catalogue",
    ),
    (
        ["npx", "tsx", "test-domain-candidate-ranking.ts"],
        "Vérification du classement des candidats",
    ),
    (
        ["npx", "tsx", "test-understanding-domain-bilingual-targeted.ts"],
        "Compréhension métier ciblée français/anglais",
    ),
    (
        ["npx", "tsx", "test-understanding-bilingual-integration-independent.ts"],
        "Régression indépendante français/anglais",
    ),
    (
        ["npx", "tsc", "--noEmit"],
        "Vérification TypeScript",
    ),
]


def afficher(titre: str) -> None:
    print("\n" + "=" * 72)
    print(titre)
    print("=" * 72)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def executer(
    commande: list[str],
    dossier: Path,
    titre: str,
) -> bool:
    afficher(titre)
    print("$", " ".join(commande), flush=True)

    try:
        resultat = subprocess.run(
            commande,
            cwd=str(dossier),
            check=False,
        )
    except FileNotFoundError as erreur:
        print("ERREUR : commande introuvable :", erreur)
        return False

    if resultat.returncode != 0:
        print(
            f"ÉCHEC : code de sortie {resultat.returncode}"
        )
        return False

    print("PASS :", titre)
    return True


def main() -> int:
    backend = Path.cwd().resolve()

    if len(sys.argv) > 1:
        backend = Path(sys.argv[1]).expanduser().resolve()

    afficher("1. VÉRIFICATION DE L'ENVIRONNEMENT")

    print("Backend :", backend)

    if not (backend / "package.json").is_file():
        print(
            "ARRÊT : package.json introuvable. "
            "Lance le script depuis ~/EDAN/backend."
        )
        return 2

    if not (backend / "src").is_dir():
        print("ARRÊT : répertoire src introuvable.")
        return 2

    target = backend / TARGET_REL

    if not target.is_file():
        print("ARRÊT : fichier cible introuvable :", target)
        return 2

    for _, description in TESTS:
        print("Test prévu :", description)

    afficher("2. INSPECTION DU FICHIER CIBLE")

    try:
        contenu_initial = target.read_bytes()
        source = contenu_initial.decode("utf-8")
    except (OSError, UnicodeDecodeError) as erreur:
        print("ARRÊT : lecture impossible :", erreur)
        return 2

    print("Fichier :", TARGET_REL)
    print("Taille :", len(contenu_initial), "octets")
    print("SHA256 initial :", sha256(contenu_initial))

    occurrences = source.count(OLD_BLOCK)

    if occurrences != 1:
        print(
            "\nARRÊT SÉCURISÉ : le bloc attendu doit être présent "
            "exactement une fois."
        )
        print("Occurrences trouvées :", occurrences)
        print(
            "Aucune modification effectuée. "
            "Le fichier réel doit être réexaminé avant de continuer."
        )
        return 3

    afficher("3. SAUVEGARDE")

    horodatage = time.strftime("%Y%m%d-%H%M%S")
    repertoire_sauvegarde = (
        backend / ".edan-backups" / f"domain-ranking-{horodatage}"
    )

    try:
        repertoire_sauvegarde.mkdir(
            parents=True,
            exist_ok=False,
        )

        sauvegarde = repertoire_sauvegarde / "appUnderstanding.ts.before"

        shutil.copy2(target, sauvegarde)

        # Vérification de l'identité de la sauvegarde.
        if sauvegarde.read_bytes() != contenu_initial:
            print("ARRÊT : la sauvegarde ne correspond pas à l'original.")
            return 4

    except OSError as erreur:
        print("ARRÊT : création de la sauvegarde impossible :", erreur)
        return 4

    print("Sauvegarde :", sauvegarde)
    print("SHA256 sauvegarde :", sha256(sauvegarde.read_bytes()))

    afficher("4. APPLICATION DU CORRECTIF")

    nouveau_source = source.replace(OLD_BLOCK, NEW_BLOCK, 1)

    if nouveau_source == source:
        print("ARRÊT : aucune différence détectée.")
        return 5

    try:
        target.write_text(
            nouveau_source,
            encoding="utf-8",
            newline="",
        )
    except OSError as erreur:
        print("ERREUR d'écriture :", erreur)

        try:
            shutil.copy2(sauvegarde, target)
            print("Fichier restauré depuis la sauvegarde.")
        except OSError as restauration:
            print("ERREUR CRITIQUE de restauration :", restauration)

        return 5

    contenu_corrige = target.read_bytes()

    print("Correction écrite :", TARGET_REL)
    print("SHA256 après correction :", sha256(contenu_corrige))

    if contenu_corrige == contenu_initial:
        print("ERREUR : le fichier n'a pas changé.")
        return 5

    afficher("5. TESTS FONCTIONNELS ET DE RÉGRESSION")

    echecs = []

    for commande, description in TESTS:
        if not executer(commande, backend, description):
            echecs.append(description)
            break

    if echecs:
        afficher("6. ÉCHEC : RESTAURATION DU FICHIER CIBLE")

        try:
            # Ne restaure que le fichier modifié par ce script.
            # Ne touche pas aux autres fichiers du dépôt.
            shutil.copy2(sauvegarde, target)

            if target.read_bytes() != contenu_initial:
                print(
                    "ERREUR CRITIQUE : le fichier restauré "
                    "ne correspond pas à l'original."
                )
                return 10

            print("Fichier restauré :", TARGET_REL)
            print("SHA256 restauré :", sha256(target.read_bytes()))
            print("Les autres fichiers n'ont pas été restaurés ni supprimés.")

        except OSError as erreur:
            print("ERREUR CRITIQUE de restauration :", erreur)
            print("Sauvegarde conservée :", sauvegarde)
            return 10

        print("\nValidations échouées :")
        for nom in echecs:
            print("-", nom)

        print("La correction n'est pas validée.")
        return 1

    afficher("6. VÉRIFICATION DU DIFF GIT")

    executer(
        ["git", "diff", "--", str(TARGET_REL)],
        backend,
        "Diff du fichier corrigé",
    )

    afficher("7. RÉSULTAT")

    print("PASS : tous les tests obligatoires ont réussi.")
    print("Fichier corrigé :", TARGET_REL)
    print("Sauvegarde conservée :", sauvegarde)
    print("Aucun commit ni push n'a été effectué.")
    print()
    print(
        "IMPORTANT : cette correction unifie le classement des candidats. "
        "Elle ne crée pas automatiquement les profils métier absents et "
        "ne garantit pas la résolution de tous les cas multidomaines."
    )

    executer(
        ["git", "status", "--short"],
        backend,
        "État Git final",
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(
            "\nInterruption reçue. Vérifie le fichier cible et sa sauvegarde "
            "avant toute nouvelle exécution."
        )
        raise SystemExit(130)