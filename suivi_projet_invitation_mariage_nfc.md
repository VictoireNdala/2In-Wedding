# Suivi de projet — Système d'invitation NFC (Inspiration Infiniti)

*Dernière mise à jour : 03/07/2026 (v3 — couche données + outil de provisioning implémentés par Claude Code)*

Ce fichier centralise toutes les décisions techniques prises sur ce projet, quel que soit l'outil utilisé (Claude, Claude Code, Claude Design, DeepSeek...). Objectif : garder une trajectoire cohérente et ne rien perdre entre les sessions.

**Statut : architecture verrouillée, prêt pour implémentation par Claude Code.**

---

## 1. Objectif du projet

**Plateforme réutilisable pour tous les futurs événements couverts par Inspiration Infiniti** (mariages, soirées d'entreprise, etc.), pas un système à usage unique. Le **mariage de Ruben et Bénédicte** est le premier cas d'usage / pilote.

Fonctionnement visé :
- Chaque invité reçoit une **carte NFC imprimée et personnalisée** (design de l'événement + nom de l'invité) en guise d'invitation.
- À l'accueil, il pose sa carte sur un lecteur NFC.
- Le système identifie l'invité et affiche un message personnalisé à l'écran, ex : *« Bienvenue Mr Dauphin au mariage de Ruben et Bénédicte »*.
- Le message est aussi **lu à voix haute**, avec une **prononciation correcte des noms d'origine congolaise/africaine** (ex : Ilunga, Tshisekedi, Mbuyi, Kapinga...) — point d'attention central du projet.

---

## 2. Architecture générale — 6 couches, 2 modes

### Les 6 composants
1. **Couche matérielle** — Raspberry Pi + lecteur NFC + écran + haut-parleurs.
2. **Couche données** — base locale (SQLite) : événements, invités, cartes, bibliothèque phonétique.
3. **Couche logique métier** — service Python qui tourne le jour J : écoute lecteur → résolution invité → affichage + audio.
4. **Couche présentation** — ce qui s'affiche à l'écran.
5. **Couche audio** — lecture des fichiers pré-générés.
6. **Outil de provisioning** — utilisé *avant* l'événement : créer l'événement, importer les invités, résoudre/valider la phonétique, générer les audios, associer les cartes.

### Les 2 modes de fonctionnement
| Mode | Quand | Rôle |
|---|---|---|
| **Provisioning/Setup** | Avant l'événement | Configuration, import invités, validation phonétique, génération audio, association cartes |
| **Accueil/Jour J** | Pendant l'événement | Écoute passive, résolution instantanée, zéro configuration, **doit fonctionner 100% hors ligne** |

Cette séparation est ce qui rend le système fiable et réutilisable : le jour J, aucune dépendance réseau, aucune configuration manuelle.

---

## 3. Décisions par couche

### 3.1 Couche matérielle — ✅ VALIDÉ

**Raspberry Pi 5, 8GB RAM**
- CPU quad-core Cortex-A76 @ 2.4GHz, GPU VideoCore VII (dual 4Kp60) — suffisant pour faire tourner en simultané le service Python + un navigateur en mode kiosque.
- Stockage : **SSD via PCIe** recommandé plutôt qu'une carte microSD (fiabilité dans la durée, réutilisation multi-événements).
- Accessoires nécessaires : refroidissement actif (obligatoire sur Pi 5), alimentation officielle USB-C 5V/5A, boîtier avec ventilateur, adaptateur audio USB + enceintes amplifiées.

**Lecteur NFC : ACR122U (USB)**
- Retenu pour sa fiabilité terrain (débranchable/remplaçable facilement), sa large communauté/documentation Python (`pyscard`), et sa compatibilité totale avec les cartes NTAG213.
- Alternative moins chère envisageable plus tard (PN532 GPIO/SPI) une fois le système validé et l'achat en volume pertinent.
- Implémentation : boucle d'écoute Python, lecture UID via commande APDU, anti-rebond (voir script de référence en section 3.7).

**Cartes NFC : imprimées personnalisées, à usage unique**
- Choix motivé par le marketing (carte-cadeau au design de l'événement) et le coût maîtrisé par événement (pas de réutilisation).
- Puce : **NTAG213** (compatible ACR122U, standard du marché pour cartes imprimables, coût unitaire bas en volume).
- Principe : on ne réécrit jamais la carte — on lit son UID physique (gravé en usine) et on le fait correspondre à un invité en base. Ça reste vrai même en usage unique.
- **Point de vigilance** : synchroniser l'UID de chaque carte imprimée avec le bon invité en base — scan-et-validation carte par carte juste après impression, pas de pré-association.
- Production : sous-traiter à un prestataire (variable data printing) pour le mariage pilote ; réévaluer l'achat d'une imprimante dédiée (Evolis/Zebra, ~1500-3000€+) une fois le concept validé et le volume d'événements le justifiant.

### 3.2 Couche données — ✅ VALIDÉ

**Principe clé** : ne jamais écrire sur la carte, seulement lire son UID et le faire correspondre en base — résout naturellement la question de la réutilisation/non-réutilisation des cartes.

**Moteur : SQLite**, seule base utilisée pendant l'accueil (aucune dépendance réseau le jour J).

**Schéma (base unique pour tous les événements, historique + actif) :**
- `events` (id, name, event_type, event_date, message_template, status)
- `guests` (id, event_id, full_name, civility, card_uid, audio_file_path, arrival_status, arrived_at)
- `cards` (uid, current_guest_id, status)
- `name_phonetics` (nom_normalise, ipa, langue_origine, verifie, notes) — voir section 3.6

**Implémentation locale vs en ligne — approche en 2 phases :**
- **Phase 1 (maintenant, mariage pilote)** : 100% local. Outil de provisioning sur laptop → écrit le fichier SQLite → copié sur le Pi (clé USB/réseau local) avant l'événement. Aucun hébergement, aucun coût.
- **Phase 2 (plus tard, plusieurs événements/kits en parallèle)** : ajout d'une base en ligne (ex. Supabase/Postgres) comme source de vérité centrale. Le Pi ne s'y connecte QUE pendant le provisioning (télécharge sa copie locale SQLite) — jamais interrogée en direct pendant l'accueil. Connexion via API HTTPS, jamais de DB brute exposée sur internet.

### 3.3 Couche logique métier — ✅ VALIDÉ

Service Python en boucle continue le jour J :
1. Écoute du lecteur NFC.
2. Carte détectée → lecture UID.
3. Anti-rebond (ignorer un UID déjà traité il y a moins de X secondes).
4. Résolution SQLite (UID + événement actif) → invité correspondant.
   - Trouvé → construction message → file d'attente audio → affichage → `arrival_status = arrived`.
   - Pas trouvé → message/son de secours (« Merci de vous présenter à l'accueil »).
5. Retour à l'écoute (non-bloquant : la lecture continue pendant qu'un message précédent est encore traité).

**Robustesse requise** : démarrage auto au boot (`systemd`), redémarrage auto en cas de crash, logs locaux.

### 3.4 Couche présentation — ⏳ EN ATTENTE DE CONFIRMATION

- **Option A (recommandée)** : Web/kiosk — page HTML/CSS locale en Chromium plein écran, pilotée par un petit serveur Flask local. Permet à Claude Design de créer des templates visuels par type d'événement sans toucher au code Python.
- **Option B** : Pygame direct — plus simple à démarrer mais moins flexible visuellement.
- **→ Décision à confirmer par l'utilisateur avant de démarrer cette couche.**

### 3.5 Couche audio — ✅ VALIDÉ (sauf 1 point)

- **File d'attente** (pas d'interruption) : chaque arrivée annoncée dans l'ordre, jamais de message coupé.
- Stockage : `audio/{event_id}/{guest_id}.mp3`, lecture via `pygame.mixer` sur thread dédié.
- Normalisation du volume à la génération, fichier de secours pour carte inconnue.
- Messages courts visés (3-5 secondes) pour éviter le retard de la file en cas d'afflux d'invités.

**Fournisseur TTS neuronal : ✅ Amazon Polly retenu**
- Choisi principalement pour son système de **lexiques personnalisés (Custom Lexicons)** natif — la bibliothèque phonétique (section 3.6) peut être hébergée directement côté Polly, référencée par nom dans chaque appel, plutôt que de reconstruire une balise `<phoneme>` à chaque génération.
- **Coût** : facturation à l'usage (Standard 4$/M caractères, Neural 16$/M caractères). Free tier : 5M car./mois (Standard) ou 1M car./mois (Neural) pendant les 12 premiers mois du compte AWS. Le réécoute d'un audio déjà généré ne coûte rien (pas de resynthèse).
- **Estimation concrète** : ~30 000 caractères pour un événement de 300 invités → gratuit en free tier, sinon <0,50€/événement en voix Neural. Coût négligeable à l'échelle de l'entreprise.
- **Contraintes à connaître** : jusqu'à 100 lexiques par compte, **chaque lexique limité à 40 000 caractères** (~800-1000 noms), jusqu'à 5 lexiques combinables par requête (solution native si la bibliothèque dépasse la capacité d'un seul fichier — la scinder en plusieurs lexiques, par langue d'origine par exemple). Nécessite un compte AWS + gestion IAM. Amazon indique ne pas conserver le contenu des textes envoyés.

### 3.6 Bibliothèque phonétique (moteur de noms) — ✅ VALIDÉ

**Décision** : abandon de l'enregistrement humain par invité (ne scale pas). À la place, **bibliothèque phonétique réutilisable** (nom → transcription IPA) qui s'enrichit événement après événement et devient un actif durable de l'entreprise.

**Architecture** : module **séparé** du reste du projet (actif transversal, indépendant de tout événement particulier) :
- **Maintenant** : fichier local séparé (`phonetics.db`), pas d'API hébergée.
- **Plus tard** (plusieurs kits/événements en parallèle) : promu en priorité en service déployé avec API simple (`resoudre_noms`, `ajouter_nom`), toujours interrogé uniquement pendant le provisioning, jamais en live.
- **Portée** : démarrage ciblé sur les noms congolais, extension organique à d'autres origines africaines selon les besoins réels — pas de tentative de couverture exhaustive dès le départ.
- **Piste future non prioritaire** : ce moteur pourrait à terme devenir un service exposé à des tiers (API de prononciation de noms africains).

**Implémentation technique retenue** : la table SQLite `name_phonetics` reste la **source de vérité éditable** (facile à interroger, modifier, faire évoluer). Elle est **exportée vers un ou plusieurs lexiques Amazon Polly** (format PLS) via un script dédié, qui publie/synchronise le lexique hébergé côté Polly à chaque changement. C'est ce lexique Polly qui est référencé lors de la génération audio (voir `tts.py` en section 3.7).

**Recommandation de démarrage** : pré-peupler la bibliothèque avec ~200-300 prénoms/noms congolais courants avant le mariage pilote, pour une couverture large dès le premier événement.

### 3.7 Outil de provisioning — ✅ ARCHITECTURE VALIDÉE, prête pour implémentation

**Pipeline complet (étapes 1 à 6) :**
1. **Import** de la liste d'invités (CSV/Excel : prénom, nom, civilité).
2. **Résolution automatique** contre la bibliothèque phonétique (recherche prénom + nom séparément, normalisés).
3. **Traitement des noms inconnus** : interface de validation avec aperçu audio avant confirmation → ajout permanent à la bibliothèque.
4. **Génération audio en lot** pour tous les invités résolus (TTS + SSML/IPA).
5. **Écoute de contrôle** avant impression des cartes (peut être filtrée aux nouveaux noms uniquement).
6. **Association carte physique** : scan de chaque carte imprimée → association UID ↔ invité en base.

**Structure de projet proposée :**
```
provisioning/
├── db.py              # schéma SQLite + requêtes
├── phonetics.py        # normalisation + recherche dans la bibliothèque
├── tts.py               # appel à l'API TTS (génération audio)
├── app.py                # interface Flask de validation (avec aperçu audio)
├── import_invites.py     # étapes 1-2 : import CSV + résolution
├── generer_audio.py      # étape 4 : génération en lot
└── associer_cartes.py    # étape 6 : association carte physique ↔ invité
```

**Squelettes de code déjà esquissés** (à reprendre et compléter par Claude Code) :

`phonetics.py` :
```python
import unicodedata
import sqlite3

def normaliser(nom):
    nom = nom.lower().strip()
    nom = unicodedata.normalize('NFD', nom)
    return ''.join(c for c in nom if unicodedata.category(c) != 'Mn')

def chercher_ipa(nom, db_path="phonetics.db"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT ipa, verifie FROM name_phonetics WHERE nom_normalise = ?", (normaliser(nom),))
    resultat = cur.fetchone()
    conn.close()
    return resultat  # None si pas trouvé
```

`tts.py` (génération via Amazon Polly, avec référence au lexique hébergé) :
```python
import boto3

polly = boto3.client("polly", region_name="eu-west-1")  # région à fixer une bonne fois

def generer_audio_invite(invite, event, chemin_sortie, nom_lexique="bibliotheque_congolaise"):
    texte = event["message_template"].format(nom=invite["prenom"])
    response = polly.synthesize_speech(
        Text=texte,
        OutputFormat="mp3",
        VoiceId="Lea",          # voix française neurale, à confirmer/tester
        Engine="neural",
        LexiconNames=[nom_lexique]   # applique automatiquement la bonne prononciation
    )
    with open(chemin_sortie, "wb") as f:
        f.write(response["AudioStream"].read())
```

`generer_lexique.py` (publication de la bibliothèque phonétique comme lexique Polly, étape à lancer à chaque évolution de `name_phonetics`) :
```python
import boto3
from phonetics import recuperer_toutes_entrees  # SELECT nom_normalise, ipa FROM name_phonetics

polly = boto3.client("polly", region_name="eu-west-1")

def construire_pls(entrees):
    lignes = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<lexicon version="1.0" xmlns="http://www.w3.org/2005/01/pronunciation-lexicon" xml:lang="fr-FR">'
    ]
    for nom, ipa in entrees:
        lignes.append(f'  <lexeme><grapheme>{nom}</grapheme><phoneme>{ipa}</phoneme></lexeme>')
    lignes.append('</lexicon>')
    return "\n".join(lignes)

def publier_lexique(nom_lexique="bibliotheque_congolaise"):
    pls = construire_pls(recuperer_toutes_entrees())
    polly.put_lexicon(Name=nom_lexique, Content=pls)
    # Rappel : 40 000 caractères max par lexique — si dépassé, répartir en plusieurs
    # lexiques (ex. par langue d'origine) et les référencer tous dans LexiconNames (max 5).
```

`app.py` (interface de validation, extrait) :
```python
from flask import Flask, render_template, request, jsonify
from tts import generer_apercu, sauvegarder_dans_bibliotheque

app = Flask(__name__)

@app.route("/api/apercu", methods=["POST"])
def apercu():
    nom, ipa = request.json["nom"], request.json["ipa"]
    chemin_audio = generer_apercu(nom, ipa)
    return jsonify({"audio_url": f"/audio/{chemin_audio}"})

@app.route("/api/confirmer", methods=["POST"])
def confirmer():
    sauvegarder_dans_bibliotheque(request.json["nom"], request.json["ipa"])
    return jsonify({"status": "ok"})
```

`associer_cartes.py` (mode association, réutilise la boucle NFC du service principal) :
```python
def mode_association(invite_id):
    print(f"Approchez la carte pour l'invité #{invite_id}...")
    uid = lire_uid(connection)  # même fonction que le service principal
    cur.execute("UPDATE guests SET card_uid = ? WHERE id = ?", (uid, invite_id))
    print(f"Carte associée : {uid}")
```

**Boucle NFC de référence (service principal, mode Accueil) :**
```python
# Dépendance : pip install pyscard
from smartcard.System import readers
from smartcard.util import toHexString

def get_reader():
    r = readers()
    if not r:
        raise RuntimeError("Aucun lecteur NFC détecté")
    return r[0]

def lire_uid(connection):
    GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    response, sw1, sw2 = connection.transmit(GET_UID)
    if sw1 == 0x90:
        return toHexString(response).replace(" ", "")
    return None

def boucle_ecoute():
    reader = get_reader()
    connection = reader.createConnection()
    dernier_uid, dernier_temps = None, 0
    while True:
        try:
            connection.connect()
            uid = lire_uid(connection)
            if uid and (uid != dernier_uid or temps_ecoule_suffisant(dernier_temps)):
                traiter_arrivee(uid)   # → résolution SQLite, file audio, affichage
                dernier_uid, dernier_temps = uid, maintenant()
            connection.disconnect()
        except Exception:
            pass  # carte retirée ou absente, on continue la boucle
        attendre(0.3)
```

---

## 4. Points encore ouverts (à trancher avant/pendant l'implémentation)
- Confirmation du mode d'affichage : Option A web/kiosk (recommandée) vs Option B pygame direct.
- Choix de la voix Polly précise à utiliser (ex. "Lea" pour le français) — à tester à l'oreille une fois le compte AWS créé.
- Découpage définitif de la bibliothèque phonétique en un ou plusieurs lexiques Polly, selon sa taille réelle une fois peuplée.

---

## 5. Roadmap concrète — prochaines étapes, dans l'ordre recommandé

1. **Commander le matériel maintenant** (priorité absolue, délai de livraison + risque technique à lever en premier) : Raspberry Pi 5 8GB, lecteur ACR122U, un lot de test de cartes NTAG213 (pas besoin des cartes imprimées finales pour tester).
2. **En parallèle** : poser concrètement le schéma SQLite (`events`, `guests`, `cards`, `name_phonetics`) — ne dépend d'aucun matériel, débloque le développement du provisioning.
3. **Dès réception du matériel** : test isolé minimal — brancher le lecteur, poser une carte, afficher l'UID dans le terminal. Valider la chaîne physique avant de brancher quoi que ce soit d'autre dessus.
4. **Créer le compte AWS** (pour Amazon Polly) et configurer les accès IAM — rapide, ne dépend d'aucun matériel non plus.
5. **Construire l'outil de provisioning** (squelette déjà posé en section 3.7) : import CSV, résolution phonétique, interface de validation avec aperçu audio, publication du lexique Polly, génération en lot, association cartes.
6. **Pré-peupler la bibliothèque phonétique** (~200-300 noms congolais courants) avant le mariage pilote, puis publier le premier lexique Polly.
7. **Trancher** le mode d'affichage (section 3.4) et construire le service principal (couche logique métier + audio + affichage).
8. **Test de bout en bout** avec des données réelles avant le jour J.

---

## 6. État d'avancement

| Élément | Statut |
|---|---|
| Architecture générale (6 couches, 2 modes) | ✅ Validé |
| Couche matérielle (Pi 5, ACR122U, cartes NTAG213) | ✅ Validé |
| Couche données (schéma SQLite, phases local/en ligne) | ✅ Validé, ✅ implémentée (`provisioning/db.py`) |
| Couche logique métier (service Python) | ✅ Validé (conception), ⏳ à coder |
| Couche présentation (web/kiosk vs pygame) | ⏳ À trancher |
| Couche audio (file d'attente, stockage, normalisation) | ✅ Validé |
| Fournisseur TTS neuronal | ✅ Validé (Amazon Polly + Lexicons) |
| Bibliothèque phonétique (architecture + workflow) | ✅ Validé, ✅ implémentée (`phonetics.py`), ⏳ à peupler |
| Outil de provisioning (architecture + squelette de code) | ✅ Implémenté (voir section 7 — reste : tester avec compte AWS réel) |
| Achat du matériel | ⏳ À faire |
| Test NFC minimal | ⏳ À faire |
| Production des cartes imprimées | ⏳ À faire (après validation audio) |

---

## 7. Sections dédiées aux autres outils

*Chaque outil doit écrire ses mises à jour dans SA section, sans modifier les autres, pour garder une trace claire de qui a fait quoi.*

### 🔧 Section Claude Code
*(décisions d'implémentation, structure du repo, choix de librairies, bugs résolus, scripts écrits...)*

**03/07/2026 — Couche données (point 1) + Outil de provisioning (point 2) implémentés**

Structure créée sous `provisioning/` (à la racine du projet) :
```
provisioning/
├── config.py            # chemins partagés (data/app.db, data/phonetics.db, data/audio, data/apercu)
├── db.py                # schéma SQLite events/guests/cards + CRUD
├── phonetics.py          # bibliothèque phonétique (phonetics.db séparée) : normaliser, chercher_ipa, ajouter_nom
├── tts.py                 # Amazon Polly : generer_audio_invite (final, via lexique) + generer_apercu (SSML, validation)
├── generer_lexique.py     # publication PLS vers Polly (découpe auto si > 40 000 caractères)
├── import_invites.py      # étapes 1-2 : import CSV/Excel (pandas) + résolution phonétique prénom/nom
├── generer_audio.py       # étape 4 : génération audio en lot pour un événement
├── app.py + templates/validation.html  # étape 3 : interface Flask de validation avec aperçu audio
├── associer_cartes.py     # étape 6 : association carte physique (UID) ↔ invité (pyscard)
├── requirements.txt
└── data/                  # bases SQLite + fichiers audio générés (créé au runtime)
```

**Écarts assumés par rapport au schéma initialement décrit en section 3.2/3.7 :**
- Table `guests` étendue avec `first_name` et `last_name` en plus de `full_name` (celui-ci reste présent, calculé automatiquement). Nécessaire car la résolution phonétique et le TTS ont besoin de traiter prénom et nom séparément (ex : le message de bienvenue utilise `{civilite} {nom}`, où `nom` = nom de famille, cf. exemple "Bienvenue Mr Dauphin"). Sans ces colonnes, il aurait fallu re-découper `full_name` à chaque usage, plus fragile.
- `name_phonetics` a une colonne `nom_original` en plus de `nom_normalise`/`ipa`/`langue_origine`/`verifie`/`notes`, pour conserver la casse/accents d'origine (utile à l'affichage et à la génération du lexique PLS).
- `tts.construire_texte` utilise le gabarit `message_template` de l'événement avec les placeholders `{civilite}`, `{nom}`, `{event_name}` — gabarit par défaut posé dans `db.py` : `"Bienvenue {civilite} {nom} au mariage de {event_name}"`.

**Autres décisions d'implémentation :**
- `associer_cartes.py` duplique pour l'instant `get_reader`/`lire_uid` (boucle NFC) plutôt que de les importer d'un module commun, car le service principal (couche logique métier, mode Accueil) n'existe pas encore. À factoriser dans un module partagé quand cette couche sera construite.
- `generer_lexique.py` découpe automatiquement la bibliothèque en plusieurs lexiques Polly si elle dépasse 40 000 caractères, et lève une erreur explicite si plus de 5 lexiques seraient nécessaires (limite Polly par requête de synthèse).
- Import CSV/Excel géré via `pandas` (colonnes attendues : `prenom`, `nom`, `civilite`).

**Testé** : initialisation des deux bases SQLite (`db.init_db()`, `phonetics.init_phonetics_db()`), création d'événement, ajout d'invité, ajout/recherche phonétique (insensible à la casse/accents), association carte↔invité — scénario complet validé en local. Tous les fichiers compilent sans erreur de syntaxe.

**Non testé (bloqué sans les éléments correspondants)** : appels Amazon Polly réels (`tts.py`, `generer_lexique.py` — nécessite un compte AWS + credentials IAM, cf. roadmap §5 point 4), lecteur NFC réel (`associer_cartes.py` — nécessite le matériel ACR122U), interface Flask (`app.py` — non lancée en navigateur dans cette session).

**Dépendances** (`requirements.txt`) : `flask`, `boto3`, `pandas`, `openpyxl`, `pyscard` — aucune n'est encore installée dans l'environnement Python local ; à faire via `pip install -r provisioning/requirements.txt` avant de lancer les scripts pour de vrai.

**Prochaine étape suggérée** : créer le compte AWS/IAM pour Amazon Polly (roadmap §5 point 4) afin de pouvoir tester `tts.py` et `generer_lexique.py` en conditions réelles.

### 🎨 Section Claude Design
*(maquettes d'écran d'accueil, charte graphique, design des cartes imprimées, mise en page du message de bienvenue...)*

—

### 💬 Section Claude (discussions / stratégie)
*(décisions d'architecture globale, arbitrages, brainstorm — voir sections 1 à 6 ci-dessus pour l'historique déjà validé)*

—

---

## Notes d'usage de ce fichier
- Ce fichier est à re-uploader dans le projet à chaque mise à jour importante (aucun outil ne peut modifier automatiquement les fichiers du projet).
- Mise à jour du fichier faite uniquement sur demande explicite de l'utilisateur (pas automatique).
- Pour Claude Code et Claude Design : demande-leur explicitement d'ajouter leurs mises à jour dans leur section dédiée, sans toucher au reste du fichier.