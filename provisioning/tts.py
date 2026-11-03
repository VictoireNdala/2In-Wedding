"""Génération audio via Amazon Polly.

Deux usages distincts :
- generer_audio_invite : génération finale, texte brut + référence au(x) lexique(s)
  Polly publiés (la prononciation est appliquée automatiquement par Polly pour tout
  mot présent dans le lexique référencé).
- generer_apercu : prévisualisation pendant la validation d'un nom pas encore
  publié dans un lexique — utilise une balise SSML <phoneme> inline avec l'IPA
  proposé, pour écouter le rendu avant confirmation.
"""
import os
import uuid

import boto3

from config import AWS_REGION, POLLY_VOICE_ID, POLLY_LEXICON_DEFAULT, APERCU_DIR, ensure_data_dirs

_polly = None


def get_polly_client():
    global _polly
    if _polly is None:
        _polly = boto3.client("polly", region_name=AWS_REGION)
    return _polly


def construire_texte(guest, event):
    """Construit le texte du message à partir du gabarit de l'événement.

    Gabarit attendu avec placeholders {civilite}, {nom}, {event_name}
    (ex: "Bienvenue {civilite} {nom} au mariage de {event_name}").
    """
    return event["message_template"].format(
        civilite=guest.get("civility") or "",
        nom=guest["last_name"],
        event_name=event["name"],
    ).strip()


def generer_audio_invite(guest, event, chemin_sortie, lexicon_names=None):
    """Génère l'audio final pour un invité et l'écrit dans chemin_sortie (mp3)."""
    lexicon_names = lexicon_names or [POLLY_LEXICON_DEFAULT]
    texte = construire_texte(guest, event)
    response = get_polly_client().synthesize_speech(
        Text=texte,
        OutputFormat="mp3",
        VoiceId=POLLY_VOICE_ID,
        Engine="neural",
        LexiconNames=lexicon_names,
    )
    os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)
    with open(chemin_sortie, "wb") as f:
        f.write(response["AudioStream"].read())
    return chemin_sortie


def generer_apercu(nom, ipa):
    """Génère un extrait audio de prévisualisation pour valider un couple (nom, IPA)
    avant de l'ajouter à la bibliothèque phonétique. Retourne le chemin du fichier généré.
    """
    ensure_data_dirs()
    ssml = f'<speak><phoneme alphabet="ipa" ph="{ipa}">{nom}</phoneme></speak>'
    response = get_polly_client().synthesize_speech(
        Text=ssml,
        TextType="ssml",
        OutputFormat="mp3",
        VoiceId=POLLY_VOICE_ID,
        Engine="neural",
    )
    nom_fichier = f"{uuid.uuid4().hex}.mp3"
    chemin_sortie = os.path.join(APERCU_DIR, nom_fichier)
    with open(chemin_sortie, "wb") as f:
        f.write(response["AudioStream"].read())
    return chemin_sortie, nom_fichier
