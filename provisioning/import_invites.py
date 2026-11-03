"""Étapes 1-2 du pipeline de provisioning : import de la liste d'invités (CSV/Excel)
et résolution automatique contre la bibliothèque phonétique (prénom et nom séparément).
"""
import argparse

import pandas as pd

import db
import phonetics

COLONNES_ATTENDUES = ["prenom", "nom", "civilite"]


def lire_fichier(chemin_fichier):
    if chemin_fichier.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(chemin_fichier, dtype=str)
    else:
        df = pd.read_csv(chemin_fichier, dtype=str)

    df.columns = [c.strip().lower() for c in df.columns]
    manquantes = [c for c in COLONNES_ATTENDUES if c not in df.columns]
    if manquantes:
        raise ValueError(f"Colonnes manquantes dans {chemin_fichier} : {manquantes}")

    return df.fillna("").to_dict(orient="records")


def resoudre_invite(prenom, nom):
    """Recherche prénom et nom séparément dans la bibliothèque phonétique.
    Retourne un statut par partie du nom : ('resolu', ipa) ou ('a_valider', None).
    """
    resultat = {}
    for cle, valeur in (("prenom", prenom), ("nom", nom)):
        trouve = phonetics.chercher_ipa(valeur)
        if trouve:
            ipa, verifie = trouve
            resultat[cle] = {"statut": "resolu", "ipa": ipa, "verifie": bool(verifie)}
        else:
            resultat[cle] = {"statut": "a_valider", "ipa": None, "verifie": False}
    return resultat


def importer(event_id, chemin_fichier, db_path=db.APP_DB_PATH):
    lignes = lire_fichier(chemin_fichier)

    guests_crees = []
    a_valider = []

    for ligne in lignes:
        prenom, nom, civilite = ligne["prenom"].strip(), ligne["nom"].strip(), ligne["civilite"].strip()
        if not prenom or not nom:
            continue

        guest_id = db.add_guest(event_id, prenom, nom, civilite or None, db_path=db_path)
        guests_crees.append(guest_id)

        resolution = resoudre_invite(prenom, nom)
        for cle, valeur in (("prenom", prenom), ("nom", nom)):
            if resolution[cle]["statut"] == "a_valider":
                a_valider.append({"type": cle, "nom": valeur, "guest_id": guest_id})

    return {
        "total_importes": len(guests_crees),
        "guest_ids": guests_crees,
        "a_valider": a_valider,
    }


def main():
    parser = argparse.ArgumentParser(description="Import d'invités (CSV/Excel) + résolution phonétique")
    parser.add_argument("event_id", type=int, help="ID de l'événement (voir db.create_event)")
    parser.add_argument("fichier", help="Chemin du fichier CSV/Excel (colonnes: prenom, nom, civilite)")
    args = parser.parse_args()

    db.init_db()
    phonetics.init_phonetics_db()

    resultat = importer(args.event_id, args.fichier)
    print(f"Invités importés : {resultat['total_importes']}")
    print(f"Noms à valider (phonétique inconnue) : {len(resultat['a_valider'])}")
    for entree in resultat["a_valider"]:
        print(f"  - [{entree['type']}] {entree['nom']}")


if __name__ == "__main__":
    main()
