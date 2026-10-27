from django.shortcuts import redirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied

class BloqueoAccesoAdminMiddleware:
    """
    Capa de Seguridad Estricta VERI*FACTU:
    Impide por completo que los usuarios autónomos comunes puedan acceder
    o visualizar el panel de administración (/admin/) de la plataforma.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Verificamos si la petición va dirigida hacia la zona del panel de administración
        if request.path.startswith('/admin/'):
            # Si el usuario ya inició sesión...
            if request.user.is_authenticated:
                # ...pero NO es el súper administrador general de la plataforma
                if not request.user.is_superuser:
                    # Expulsión inmediata por violación de políticas de inalterabilidad
                    return redirect('login_usuario')
            else:
                # Si ni siquiera está logueado, lo mandamos a la pantalla de acceso
                return redirect('login_usuario')

        response = self.get_response(request)
        return response
