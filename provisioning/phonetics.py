"""Bibliothèque phonétique — actif transversal, indépendant des événements.

Stockée dans une base SQLite séparée (phonetics.db). Source de vérité éditable ;
publiée vers un lexique Amazon Polly (PLS) par generer_lexique.py à chaque évolution.
"""
import sqlite3
import unicodedata

from config import PHONETICS_DB_PATH, ensure_data_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS name_phonetics (
    nom_normalise TEXT PRIMARY KEY,
    nom_original TEXT NOT NULL,
    ipa TEXT NOT NULL,
    langue_origine TEXT,
    verifie INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
"""


def normaliser(nom):
    nom = nom.lower().strip()
    nom = unicodedata.normalize('NFD', nom)
    return ''.join(c for c in nom if unicodedata.category(c) != 'Mn')


def get_connection(db_path=PHONETICS_DB_PATH):
    ensure_data_dirs()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_phonetics_db(db_path=PHONETICS_DB_PATH):
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def chercher_ipa(nom, db_path=PHONETICS_DB_PATH):
    """Retourne (ipa, verifie) ou None si le nom n'est pas dans la bibliothèque."""
    conn = get_connection(db_path)
    cur = conn.execute(
        "SELECT ipa, verifie FROM name_phonetics WHERE nom_normalise = ?",
        (normaliser(nom),),
    )
    resultat = cur.fetchone()
    conn.close()
    return (resultat["ipa"], resultat["verifie"]) if resultat else None


def ajouter_nom(nom, ipa, langue_origine=None, verifie=1, notes=None, db_path=PHONETICS_DB_PATH):
    """Ajoute ou met à jour une entrée de la bibliothèque (ajout permanent après validation)."""
    conn = get_connection(db_path)
    conn.execute(
        """INSERT INTO name_phonetics (nom_normalise, nom_original, ipa, langue_origine, verifie, notes)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(nom_normalise) DO UPDATE SET
               nom_original = excluded.nom_original,
               ipa = excluded.ipa,
               langue_origine = excluded.langue_origine,
               verifie = excluded.verifie,
               notes = excluded.notes""",
        (normaliser(nom), nom, ipa, langue_origine, verifie, notes),
    )
    conn.commit()
    conn.close()


def recuperer_toutes_entrees(db_path=PHONETICS_DB_PATH):
    """Retourne [(nom_original, ipa), ...] pour toutes les entrées vérifiées — utilisé pour publier le lexique Polly."""
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT nom_original, ipa FROM name_phonetics WHERE verifie = 1 ORDER BY nom_normalise"
    ).fetchall()
    conn.close()
    return [(r["nom_original"], r["ipa"]) for r in rows]


def lister_non_verifies(db_path=PHONETICS_DB_PATH):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT * FROM name_phonetics WHERE verifie = 0 ORDER BY nom_normalise"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_phonetics_db()
    print(f"Base phonétique initialisée : {PHONETICS_DB_PATH}")
