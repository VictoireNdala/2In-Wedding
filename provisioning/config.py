"""Chemins et constantes partagés par tous les scripts du provisioning."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

APP_DB_PATH = os.path.join(DATA_DIR, "app.db")
PHONETICS_DB_PATH = os.path.join(DATA_DIR, "phonetics.db")

AUDIO_DIR = os.path.join(DATA_DIR, "audio")        # audio final par événement/invité
APERCU_DIR = os.path.join(DATA_DIR, "apercu")       # audio de prévisualisation (validation phonétique)

AWS_REGION = "eu-west-1"
POLLY_VOICE_ID = "Lea"          # voix française neurale, à confirmer à l'oreille
POLLY_LEXICON_MAX_CHARS = 40_000
POLLY_LEXICON_DEFAULT = "bibliotheque_congolaise"


def ensure_data_dirs():
    for path in (DATA_DIR, AUDIO_DIR, APERCU_DIR):
        os.makedirs(path, exist_ok=True)
