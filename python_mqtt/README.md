# Banc de test MQTT — logs NSP synthétiques

Reproduit sur un PC perso la setup du stage : des fichiers de logs NSP, un script qui les **rejoue** sur MQTT et un script qui **observe** les frames en hexa.

> ⚠️ Données **inventées** (adresses, CTRL, valeurs). Ce ne sont pas les fichiers de l'entreprise. Adapte les constantes de `gen_logs.py` à ton ICD.

## Contenu

| Fichier | Rôle |
|---|---|
| `gen_logs.py` | génère `archive_EquipSerialIn.txt` (demandes) et `archive_EquipSerialOut.txt` (réponses) |
| `replay.py` | publie chaque ligne des logs sur MQTT, au rythme d'origine ou accéléré |
| `observe_mqtt.py` | s'abonne et affiche les frames in/out en hexa (aucun décodage) |
| `archive_Equip*.txt` | logs déjà générés (100 paires + quelques lignes cassées à la fin du fichier out) |

## Format des logs

Une frame par ligne :

```
temps | date_emission | date_reception | data=c0 DST SRC CTRL DATA... CRC_lo CRC_hi c0
```

- `c0` = délimiteur SLIP (`c0` dans les données → `db dc`, `db` → `db dd`)
- En-tête : DST, SRC, CTRL (1 octet chacun)
- CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF) de DST à la fin de DATA, stocké little-endian
- Le message MQTT = **la ligne entière**, même format que le fichier

Topics : `equip/serial/in` et `equip/serial/out` (préfixe modifiable avec `--prefix`).

## Installation (Ubuntu)

```bash
sudo apt install mosquitto mosquitto-clients python3-paho-mqtt
# ou dans un venv : pip install paho-mqtt
```

Les scripts marchent avec paho-mqtt 1.x (apt) et 2.x (pip).

## Utilisation

```bash
# 1. (optionnel) regénérer les logs ; --broken ajoute des frames invalides
python3 gen_logs.py 500 --broken

# 2. terminal A : observer
python3 observe_mqtt.py

# 3. terminal B : rejouer
python3 replay.py --in archive_EquipSerialIn.txt --out archive_EquipSerialOut.txt
python3 replay.py --in ... --out ... --speed 20   # 20x plus vite
python3 replay.py --in ... --out ... --speed 0    # rafale (test de charge)
```

Vérif rapide sans script : `mosquitto_sub -t 'equip/serial/#' -v`

## Tests utiles pour l'analyseur

- **Robustesse** : `gen_logs.py --broken` → lignes vides, frames trop courtes, CRC faux, frame énorme, ligne hors format. L'analyseur ne doit jamais planter.
- **Charge** : `--speed 0` avec beaucoup de frames. Si des frames se perdent, regarder `max_queued_messages` dans la config Mosquitto.
- **Nouveau protocole** : modifier `ADDR_*`, `CTRL_*` ou la taille de l'en-tête dans `gen_logs.py` pour vérifier que ton YAML suffit sans toucher au code.
