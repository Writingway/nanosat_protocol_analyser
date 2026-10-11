import argparse
import sys


def count_data_lines_file(path: str) -> int:
    # CHANGEMENT : docstring (""" en 1re ligne de la fonction) au lieu d'un commentaire.
    # C'est la façon standard de documenter une fonction : l'éditeur l'affiche au survol
    # et help(count_data_lines_file) la montre. Le type de retour "-> int" dit ce qu'on récupère.
    """Compte les lignes du fichier qui contiennent « data= » (une ligne = une frame)."""
    # CHANGEMENT : le compteur est créé AVANT d'ouvrir le fichier, et le return est sorti du
    # "with". Résultat identique, mais plus lisible : le "with" ne sert plus qu'à lire le fichier,
    # et on voit d'un coup d'œil où commence et finit le travail.
    compteur = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "data=" in line:
                compteur += 1
    return compteur


def main():
    parser = argparse.ArgumentParser(description="Compter les lignes contenant 'data=' dans un fichier.")
    parser.add_argument("file", help="Chemin vers le fichier à analyser.")
    args = parser.parse_args()

    # CHANGEMENT : le "try" n'entoure plus que la ligne qui peut lever l'erreur (le open caché
    # dans la fonction). Le print du résultat est sorti du "try" : s'il plantait un jour, on ne
    # veut pas que ce soit confondu avec « fichier introuvable ».
    try:
        compteur = count_data_lines_file(args.file)
    except FileNotFoundError:
        # CHANGEMENT : file=sys.stderr → le message part sur la sortie d'ERREUR.
        # Avec « python3 0x01.py x.txt > resultat.txt », le résultat va dans le fichier
        # mais l'erreur reste visible à l'écran.
        print(f"Erreur : le fichier '{args.file}' n'a pas été trouvé.", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        # CHANGEMENT (nouveau cas trouvé en testant) : passer un DOSSIER ou un fichier sans droit
        # de lecture levait IsADirectoryError / PermissionError → trace d'erreur.
        # Ces erreurs sont toutes des « enfants » d'OSError (FileNotFoundError aussi).
        # L'ordre compte : Python prend le PREMIER except qui correspond, donc on met le cas
        # précis (FileNotFoundError) avant le cas général (OSError).
        # e.strerror = la raison donnée par le système (ex. « Is a directory »).
        print(f"Erreur : impossible de lire '{args.file}' ({e.strerror}).", file=sys.stderr)
        sys.exit(1)

    print(f"Nombre de lignes contenant 'data=' : {compteur}")


if __name__ == "__main__":
    main()
