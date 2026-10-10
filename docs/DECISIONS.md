# Décisions d'architecture

Réponses aux points ouverts du brief (§8). Chaque décision : quoi, pourquoi.

## Version du YAML
Chaque version d'un YAML est figée en base (`ProtocolVersion`, identifiée par son sha256) et
chaque frame pointe vers la version qui l'a décodée. Modifier un YAML ne change donc pas
l'affichage des anciennes captures. Une version identique n'est stockée qu'une fois.

## Champs d'en-tête stockés en JSONB
Les valeurs décodées (`{"DST": 42, …}`) sont stockées avec la frame. C'est une donnée dérivée
(octets bruts + version figée), donc parfaitement déterministe, mais indispensable pour filtrer
en SQL sur de gros volumes (index GIN). L'arbre détaillé, lui, est recalculé à l'affichage.

## YAML invalide pendant le rechargement à chaud
Le fichier est validé en entier avant d'être pris en compte. S'il est invalide, la version
précédente reste active et l'erreur (en français, avec la clé ou la ligne fautive) est exposée
par l'API pour l'IHM. Via l'éditeur web, un YAML invalide n'est jamais écrit sur disque.
Le rechargement se fait par comparaison des dates de modification (au plus toutes les 2 s) :
pas de thread ni d'inotify, fonctionne aussi sur des dossiers montés.

## SLIP
Décrit dans le YAML (`framing: slip | none`). Les octets bruts sont stockés tels que dans le log
(avec les `c0`) ; le déframing est fait par le moteur. Les anomalies SLIP (`c0` final absent,
échappement invalide) sont signalées sans être corrigées.

## Statuts d'une frame
Une frame n'est jamais rejetée : elle est enregistrée avec un statut. Si plusieurs anomalies,
le statut est la plus grave, dans l'ordre : `malformed_line`, `unknown_protocol`, `empty`,
`too_long`, `framing_error`, `too_short`, `header_mismatch`, `length_mismatch`, `crc_error`, `ok`.
Le détail liste toutes les anomalies.

## Horodatage
Fait foi : la **date d'émission** écrite par le banc (2e colonne du log). On garde aussi la date
de réception notée par le banc et la date de réception par l'analyseur. Les dates sans fuseau
sont interprétées dans `LOG_TIMEZONE` (Europe/Paris par défaut), stockées en UTC.
Une ligne illisible prend la date de la ligne précédente de la même source.

## Ordre in / out
La liste est triée par date d'émission, pas par ordre d'arrivée : une réponse arrivée avant
sa demande (topics distincts) se retrouve à sa place.

## Ré-import d'un même fichier
L'empreinte sha256 des fichiers est gardée sur la capture. Un ré-import est refusé (HTTP 409,
avec le lien vers la capture existante) sauf si `force` est demandé.

## Pagination
Liste paginée par `offset/limit` avec le nombre total, triée sur l'index `(capture, ts, id)`.
Suffisant pour des captures de quelques centaines de milliers de frames ; l'IHM ne charge que
les pages visibles.

## Compteur de frames
`Capture.frame_count` est un compteur tenu à jour à chaque lot écrit, pour éviter un `COUNT(*)`
par capture dans la liste des captures.
