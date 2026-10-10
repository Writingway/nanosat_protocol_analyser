# Analyseur de protocoles d'équipements satellite — Brief projet

> Document de référence pour comprendre le besoin et recréer une application similaire.
> Périmètre : **analyse du protocole (en-tête) uniquement**. Le contenu de la charge utile (DATA) n'est **pas** décodé.

---

## 1. Contexte

- Entreprise du spatial (nanosatellites). Un satellite embarque plusieurs **équipements** (capteurs, actionneurs) qui dialoguent via des **protocoles maison** (ex. NSP).
- Aujourd'hui : outils internes rustiques, utilisables seulement par les développeurs.
- Objectif : une **application web autonome**, inspirée de Wireshark (mais pas un plugin Wireshark), à usage interne, déployée sur un serveur/VM local accessible par URL.
- Utilisateurs : développeurs **et non-développeurs** (ingénieurs test, système).
- Attendu : une vraie application stable, le maximum de fonctionnalités qui marchent sans bug.

## 2. Ce que fait l'application

**Passive** : elle écoute et décode, elle n'envoie **jamais** rien aux équipements.

Deux sources de frames, même format :

1. **Import de fichiers de logs** (analyse après un test).
2. **Capture live MQTT** : abonnement à un broker, topics définis par **configuration** (suivi pendant un test).

Fonctions IHM (inspirées de Wireshark) :

- **Liste chronologique** des frames (horodatage, source, DST, SRC, CTRL, longueur, statut).
- **Arbre des champs** de la frame sélectionnée (champs de l'en-tête).
- **Vue hexadécimale** avec surlignage du champ sélectionné.
- **Filtres / recherche** (par DST, SRC, CTRL, source, statut, période).
- **Live** : nouvelles frames qui arrivent en direct.
- **Rejouer / revoir** une frame ou une capture.
- Identifier **d'où vient** chaque frame (topic MQTT / équipement / banc de test).

Hypothèse actuelle : **un équipement par log ou par flux**.

## 3. Le protocole de référence : NSP

Structure d'une frame (champs d'en-tête à 1 octet entier, pas de champs de bits pour l'instant) :

| Champ | Rôle |
|---|---|
| DST | adresse destinataire |
| SRC | adresse source |
| CTRL | octet de contrôle (sens défini par l'ICD de l'entreprise) |
| DATA | charge utile, longueur variable — **non décodée** |
| CRC | somme de contrôle sur 2 octets, en fin de frame |

Règles importantes :

- La **source de vérité est l'ICD de l'entreprise** (Interface Control Document), pas la spec publique NSP.
- CRC : CRC-16/CCITT-FALSE, calculé de DST à la fin de DATA, stocké little-endian. **Vérification du CRC reportée** dans le planning (prévoir l'emplacement dans le moteur).
- Une réponse inverse en général DST et SRC de la demande.
- Les logs ont deux sens : **in** (demandes) et **out** (réponses), en fichiers séparés et en topics MQTT séparés (`<equipement>/serial/in` et `<equipement>/serial/out`).
- Format d'une ligne de log : `temps | date | date | data=<octets hexa>` — une frame par ligne. Les messages MQTT ont le **même format** que les lignes de log.
- D'autres protocoles maison existent (ex. ewc31, emea) : l'architecture doit les accueillir.

## 4. Exigence clé : ajouter un protocole sans recompiler

- Un non-développeur doit pouvoir ajouter/modifier un protocole.
- Donc : **pas de plugin compilé** (.so). Les protocoles sont décrits dans des **fichiers YAML**.
- Chaque YAML décrit l'**en-tête** d'un protocole : nom, position et taille des champs (DST, SRC, CTRL…), position et type du CRC, endianness.
- **Rechargement à chaud** du YAML (sans redémarrer l'application).
- Une documentation sera fournie aux non-devs pour écrire ces YAML.

## 5. Architecture et technos retenues

```
[Fichier log] ─┐
               ├─> Lecteur (pont) ─> Moteur YAML (en-tête) ─> PostgreSQL ─> API Django ─> IHM React
[Broker MQTT] ─┘
```

| Brique | Techno | Pourquoi |
|---|---|---|
| Backend / API | **Python + Django** | le décodage n'est pas le goulot ; apprécié du tuteur ; productif |
| Base | **PostgreSQL seul** | besoin relationnel (captures, sources, frames) ; une seule base à maintenir (InfluxDB écarté) |
| Description protocoles | **YAML** | pas de recompilation, lisible par un non-dev |
| Live | **MQTT** (broker Mosquitto en test) | c'est le moyen de diffusion du banc de test |
| IHM | **React** | interface type Wireshark |
| Déploiement | VM / serveur local | usage interne |

Choix écartés : bibliothèque C existante (inutile pour l'analyseur), plugins compilés, InfluxDB, Rust.

Contraintes de développement : code **écrit à la main**, simplicité d'abord (rien sans besoin réel).

## 6. Données en base

Principe : **rien de redondant, aucun champ inutile**.

- **Source** : d'où vient la frame (topic MQTT, fichier, équipement / IP du banc).
- **Capture** : une session (import d'un fichier ou session live), horodatée.
- **Frame** : octets bruts, horodatage, sens (in/out), lien vers capture et source, statut.
- Pas de comptes utilisateurs.
- Écrire en base **par paquets** (et non une frame = un commit) quand le flux monte.

## 7. Robustesse (leçons des tests)

- Une frame invalide ne doit **jamais** faire planter l'application : elle est enregistrée et **signalée** avec un statut (vide, trop courte, trop grande, CRC faux…).
- Décoder **fidèlement**, même les données qui ne respectent pas l'ICD : afficher et signaler, ne pas corriger.
- Refuser au-delà d'une **taille maximale** (définie par protocole).
- La **file d'attente du broker** peut déborder si le lecteur est lent → frames perdues. Lecteur rapide + config du broker adaptée.
- Afficher chaque frame en direct coûte cher → n'afficher que ce qui est visible.
- Le banc publie en **QoS 0** (pas de garantie de livraison).

## 8. Points à ne pas oublier (pas encore traités)

- **Erreurs de YAML** : que se passe-t-il si un non-dev enregistre un YAML invalide pendant le rechargement à chaud ? → valider avant d'appliquer, garder l'ancienne version, afficher l'erreur clairement.
- **Version du YAML** : si l'en-tête est décodé à la volée depuis les octets bruts, un YAML modifié change l'affichage des anciennes captures. Décider : décoder à la lecture (rien de redondant) ou mémoriser la version utilisée.
- **SLIP / délimiteur** : le recadrage dit « plus de SLIP », mais les lignes de log contiennent encore les octets `c0`. Clarifier si le lecteur doit les retirer ou si le YAML le décrit.
- **Horodatage** : quelle heure fait foi ? Celle du log, du banc, ou de réception par l'app ? Fuseau horaire ?
- **Reconnexion MQTT** : coupure du broker → reconnexion automatique et indication visible « live interrompu » (les frames perdues pendant la coupure ne reviennent pas en QoS 0).
- **Ordre in/out** : en live, une réponse peut arriver avant sa demande (deux topics distincts).
- **Ré-import d'un même fichier** : doublons ou détection ?
- **Push vers l'IHM en live** : WebSocket (Django Channels) ou SSE à choisir.
- **Volume dans le temps** : pagination de la liste, index sur les colonnes filtrées, politique de purge/archivage.
- **Mémoire sur longue durée** : test de durée encore à faire.
- **Sécurité minimale** : sans comptes, l'app reste exposée à tout le réseau interne ; au moins limiter l'accès réseau.
- **Plusieurs équipements à la fois** : hors V1, mais ne pas fermer la porte dans le modèle de données.
- **Export** d'une capture (fichier brut, CSV) pour partage.

## 9. Hors périmètre

- Décodage de la charge utile DATA (mesures capteurs, conversions physiques).
- Envoi de commandes aux équipements.
- Gestion des utilisateurs.
