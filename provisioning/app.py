"""Interface Flask de validation phonétique (étape 3 du pipeline de provisioning).

Liste les prénoms/noms pas encore vérifiés dans la bibliothèque phonétique,
permet de proposer un IPA, d'en écouter un aperçu (SSML, sans lexique), puis
de confirmer l'ajout permanent à la bibliothèque.
"""
import os

from flask import Flask, render_template, request, jsonify, send_from_directory

import db
import phonetics
import tts
import generer_lexique
from config import APERCU_DIR

app = Flask(__name__)


def lister_a_valider(event_id=None):
    conn = db.get_connection()
    if event_id:
        rows = conn.execute(
            "SELECT DISTINCT first_name, last_name FROM guests WHERE event_id = ?", (event_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT DISTINCT first_name, last_name FROM guests").fetchall()
    conn.close()

    noms_vus = set()
    a_valider = []
    for row in rows:
        for nom in (row["first_name"], row["last_name"]):
            norm = phonetics.normaliser(nom)
            if not nom or norm in noms_vus:
                continue
            noms_vus.add(norm)
            trouve = phonetics.chercher_ipa(nom)
            if not trouve or not trouve[1]:
                a_valider.append({"nom": nom, "ipa_propose": trouve[0] if trouve else ""})
    return a_valider


@app.route("/")
def index():
    event_id = request.args.get("event_id", type=int)
    noms = lister_a_valider(event_id)
    events = db.list_events()
    return render_template("validation.html", noms=noms, events=events, event_id=event_id)


@app.route("/api/apercu", methods=["POST"])
def apercu():
    nom, ipa = request.json["nom"], request.json["ipa"]
    _chemin, nom_fichier = tts.generer_apercu(nom, ipa)
    return jsonify({"audio_url": f"/audio/{nom_fichier}"})


@app.route("/api/confirmer", methods=["POST"])
def confirmer():
    data = request.json
    phonetics.ajouter_nom(
        data["nom"], data["ipa"], langue_origine=data.get("langue_origine"), verifie=1
    )
    return jsonify({"status": "ok"})


@app.route("/api/publier", methods=["POST"])
def publier():
    noms_lexiques = generer_lexique.publier_lexique()
    return jsonify({"status": "ok", "lexiques": noms_lexiques})


@app.route("/audio/<path:nom_fichier>")
def audio(nom_fichier):
    return send_from_directory(APERCU_DIR, nom_fichier)


if __name__ == "__main__":
    db.init_db()
    phonetics.init_phonetics_db()
    app.run(debug=True, port=5000)
