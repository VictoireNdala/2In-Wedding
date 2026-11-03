"""Publie la bibliothèque phonétique (table name_phonetics) comme lexique(s) Amazon Polly.

À relancer à chaque évolution de la bibliothèque (nouveaux noms validés).
Un lexique Polly est limité à 40 000 caractères : si la bibliothèque dépasse cette
taille, elle est répartie en plusieurs lexiques (bibliotheque_congolaise_1, _2, ...),
combinables jusqu'à 5 par requête de synthèse (voir tts.py).
"""
import boto3

from config import AWS_REGION, POLLY_LEXICON_DEFAULT, POLLY_LEXICON_MAX_CHARS
from phonetics import recuperer_toutes_entrees

PLS_HEADER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<lexicon version="1.0" xmlns="http://www.w3.org/2005/01/pronunciation-lexicon" xml:lang="fr-FR">\n'
)
PLS_FOOTER = '</lexicon>'


def _ligne_lexeme(nom, ipa):
    return f'  <lexeme><grapheme>{nom}</grapheme><phoneme>{ipa}</phoneme></lexeme>\n'


def construire_pls(entrees):
    return PLS_HEADER + "".join(_ligne_lexeme(nom, ipa) for nom, ipa in entrees) + PLS_FOOTER


def decouper_en_lots(entrees, max_chars=POLLY_LEXICON_MAX_CHARS):
    """Répartit les entrées en lots dont le PLS généré reste sous max_chars."""
    lots, lot_courant, taille_courante = [], [], len(PLS_HEADER) + len(PLS_FOOTER)
    for nom, ipa in entrees:
        taille_ligne = len(_ligne_lexeme(nom, ipa))
        if lot_courant and taille_courante + taille_ligne > max_chars:
            lots.append(lot_courant)
            lot_courant, taille_courante = [], len(PLS_HEADER) + len(PLS_FOOTER)
        lot_courant.append((nom, ipa))
        taille_courante += taille_ligne
    if lot_courant:
        lots.append(lot_courant)
    return lots


def publier_lexique(nom_prefix=POLLY_LEXICON_DEFAULT):
    """Publie la bibliothèque phonétique complète vers Polly. Retourne la liste des
    noms de lexiques publiés (à passer dans LexiconNames lors de la synthèse)."""
    entrees = recuperer_toutes_entrees()
    lots = decouper_en_lots(entrees)
    polly = boto3.client("polly", region_name=AWS_REGION)

    noms_lexiques = []
    for i, lot in enumerate(lots, start=1):
        nom_lexique = nom_prefix if len(lots) == 1 else f"{nom_prefix}_{i}"
        pls = construire_pls(lot)
        polly.put_lexicon(Name=nom_lexique, Content=pls)
        noms_lexiques.append(nom_lexique)

    if len(noms_lexiques) > 5:
        raise RuntimeError(
            f"{len(noms_lexiques)} lexiques nécessaires, mais Polly n'en accepte que 5 "
            "par requête de synthèse. Il faut revoir le découpage (par langue d'origine par ex.)."
        )
    return noms_lexiques


if __name__ == "__main__":
    noms = publier_lexique()
    print(f"Lexique(s) publié(s) : {', '.join(noms)}")
