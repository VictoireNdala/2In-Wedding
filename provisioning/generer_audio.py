"""Étape 4 du pipeline de provisioning : génération audio en lot pour tous les
invités résolus d'un événement (via Amazon Polly + lexique(s) phonétique publiés).
"""
import argparse
import os

import db
import phonetics
import tts
from config import AUDIO_DIR, POLLY_LEXICON_DEFAULT


def generer_audio_event(event_id, lexicon_names=None, forcer=False, db_path=db.APP_DB_PATH):
    event = db.get_event(event_id, db_path=db_path)
    if not event:
        raise ValueError(f"Événement introuvable : {event_id}")

    lexicon_names = lexicon_names or [POLLY_LEXICON_DEFAULT]
    guests = db.list_guests_for_event(event_id, db_path=db_path)

    generes, en_attente = [], []
    for guest in guests:
        if guest["audio_file_path"] and not forcer:
            continue

        trouve = phonetics.chercher_ipa(guest["last_name"])
        if not trouve or not trouve[1]:  # absent ou non vérifié
            en_attente.append(guest)
            continue

        dossier_event = os.path.join(AUDIO_DIR, str(event_id))
        chemin_sortie = os.path.join(dossier_event, f"{guest['id']}.mp3")
        tts.generer_audio_invite(guest, event, chemin_sortie, lexicon_names=lexicon_names)
        db.update_guest_audio_path(guest["id"], chemin_sortie, db_path=db_path)
        generes.append(guest)

    return {"generes": generes, "en_attente": en_attente}


def main():
    parser = argparse.ArgumentParser(description="Génération audio en lot pour un événement")
    parser.add_argument("event_id", type=int)
    parser.add_argument("--lexiques", help="Noms de lexiques Polly séparés par des virgules", default=None)
    parser.add_argument("--force", action="store_true", help="Régénère même les audios déjà générés")
    args = parser.parse_args()

    lexicon_names = args.lexiques.split(",") if args.lexiques else None
    resultat = generer_audio_event(args.event_id, lexicon_names=lexicon_names, forcer=args.force)

    print(f"Audios générés : {len(resultat['generes'])}")
    if resultat["en_attente"]:
        print(f"En attente de validation phonétique ({len(resultat['en_attente'])}) :")
        for guest in resultat["en_attente"]:
            print(f"  - {guest['full_name']} (id={guest['id']})")


if __name__ == "__main__":
    main()
