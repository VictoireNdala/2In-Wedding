"""Étape 6 du pipeline de provisioning : association carte physique (UID) ↔ invité.

Réutilise la boucle de lecture NFC de référence (voir section 3.7 du fichier de
suivi) — à factoriser dans un module commun quand le service principal (couche
logique métier, mode Accueil) sera construit, pour ne pas dupliquer ce code.
"""
import argparse
import time

from smartcard.System import readers
from smartcard.util import toHexString

import db

GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]


def get_reader():
    r = readers()
    if not r:
        raise RuntimeError("Aucun lecteur NFC détecté")
    return r[0]


def lire_uid(connection):
    response, sw1, sw2 = connection.transmit(GET_UID)
    if sw1 == 0x90:
        return toHexString(response).replace(" ", "")
    return None


def attendre_carte(connection, timeout=30):
    """Bloque jusqu'à détection d'une carte ou expiration du délai. Retourne l'UID ou None."""
    debut = time.time()
    while time.time() - debut < timeout:
        try:
            connection.connect()
            uid = lire_uid(connection)
            if uid:
                return uid
        except Exception:
            pass
        time.sleep(0.3)
    return None


def mode_association(event_id, db_path=db.APP_DB_PATH):
    guests = [g for g in db.list_guests_for_event(event_id, db_path=db_path) if not g["card_uid"]]
    if not guests:
        print("Tous les invités de cet événement ont déjà une carte associée.")
        return

    reader = get_reader()
    connection = reader.createConnection()

    print(f"{len(guests)} invité(s) sans carte associée.")
    for guest in guests:
        print(f"\nApprochez la carte pour : {guest['full_name']} (id={guest['id']})...")
        uid = attendre_carte(connection)
        if uid is None:
            print("  Aucune carte détectée (délai dépassé). Invité ignoré, relancez plus tard.")
            continue

        carte_existante = db.get_card(uid, db_path=db_path)
        if carte_existante and carte_existante["current_guest_id"] != guest["id"]:
            print(f"  ATTENTION : cet UID est déjà associé à l'invité #{carte_existante['current_guest_id']}.")
            confirmation = input("  Réassigner cette carte à ce nouvel invité ? (o/n) ")
            if confirmation.strip().lower() != "o":
                print("  Association annulée pour cet invité.")
                continue

        db.assign_card(uid, guest["id"], db_path=db_path)
        print(f"  Carte associée : {uid}")


def main():
    parser = argparse.ArgumentParser(description="Association carte physique (NFC) ↔ invité")
    parser.add_argument("event_id", type=int)
    args = parser.parse_args()
    mode_association(args.event_id)


if __name__ == "__main__":
    main()
