"""Sécurité minimale : sans comptes utilisateurs, on limite l'accès par réseau source."""
import ipaddress

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from django.http import HttpResponseForbidden


class AllowedNetworksMiddleware:
    # Compatible sync et async : le flux SSE (vue async) n'est pas forcé dans un thread.
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = [ipaddress.ip_network(n, strict=False) for n in settings.ALLOWED_NETS]
        self.is_async = iscoroutinefunction(get_response)
        if self.is_async:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.is_async:
            return self._acall(request)
        return self._forbidden(request) or self.get_response(request)

    async def _acall(self, request):
        return self._forbidden(request) or await self.get_response(request)

    def _forbidden(self, request):
        if self.networks and not self._is_allowed(request.META.get("REMOTE_ADDR", "")):
            return HttpResponseForbidden("Accès refusé depuis ce réseau.")
        return None

    def _is_allowed(self, addr: str) -> bool:
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False
        return any(ip in net for net in self.networks)
