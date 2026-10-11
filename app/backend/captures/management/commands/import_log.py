from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from captures.importer import DuplicateImport, LogFile, guess_direction, import_logs


class Command(BaseCommand):
    help = "Importe un ou plusieurs fichiers de logs (le sens in/out est déduit du nom ou forcé)."

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+", help="fichiers de logs (ex. archive_EquipSerialIn.txt)")
        parser.add_argument("--equipment", required=True, help="nom de l'équipement")
        parser.add_argument("--protocol", required=True, help="nom du protocole YAML (ex. nsp)")
        parser.add_argument("--bench", default="", help="banc de test (optionnel)")
        parser.add_argument("--name", help="nom de la capture")
        parser.add_argument("--direction", choices=["in", "out"], help="force le sens (un seul fichier)")
        parser.add_argument("--force", action="store_true", help="ré-importe même si déjà importé")

    def handle(self, *args, **opts):
        handles, files = [], []
        try:
            for path in map(Path, opts["files"]):
                direction = opts["direction"] or guess_direction(path.name)
                if direction is None:
                    raise CommandError(f"{path.name} : sens in/out indéterminable, utilisez --direction")
                fh = path.open("rb")
                handles.append(fh)
                files.append(LogFile(path.name, fh, direction))
            capture = import_logs(files, equipment=opts["equipment"], protocol=opts["protocol"],
                                  bench=opts["bench"], name=opts["name"], force=opts["force"])
        except DuplicateImport as exc:
            raise CommandError(f"{exc} (id {exc.capture.pk}) — utilisez --force pour dupliquer") from None
        except OSError as exc:
            raise CommandError(str(exc)) from None
        finally:
            for fh in handles:
                fh.close()

        stats = capture.frames.values_list("status").order_by()
        counts: dict[str, int] = {}
        for (status,) in stats:
            counts[status] = counts.get(status, 0) + 1
        self.stdout.write(self.style.SUCCESS(f"Capture {capture.pk} « {capture.name} » : {capture.frame_count} frames"))
        for status, n in sorted(counts.items()):
            self.stdout.write(f"  {status:<18} {n}")
