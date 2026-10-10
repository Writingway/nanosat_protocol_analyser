from django.db import models


class ProtocolVersion(models.Model):
    """Photo immuable d'un fichier YAML de protocole.

    Chaque frame pointe vers la version qui a servi à la décoder : modifier le YAML
    ne change donc pas l'affichage des anciennes captures. Une même version n'est
    stockée qu'une fois (clé = empreinte sha256 du texte).
    """

    name = models.CharField(max_length=50)
    sha256 = models.CharField(max_length=64, unique=True)
    yaml_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "-created_at"]

    def __str__(self) -> str:
        return f"{self.name}@{self.sha256[:8]}"
