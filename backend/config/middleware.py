"""Sécurité minimale : sans comptes utilisateurs, on limite l'accès par réseau source."""
import ipaddress

from django.conf import settings
from django.http import HttpResponseForbidden


class AllowedNetworksMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = [ipaddress.ip_network(n, strict=False) for n in settings.ALLOWED_NETS]

    def __call__(self, request):
        if self.networks and not self._is_allowed(request.META.get("REMOTE_ADDR", "")):
            return HttpResponseForbidden("Accès refusé depuis ce réseau.")
        return self.get_response(request)

    def _is_allowed(self, addr: str) -> bool:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in net for net in self.networks)
