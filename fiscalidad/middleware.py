from django.shortcuts import redirect
from django.urls import reverse

class BloqueoAccesoAdminMiddleware:
    """
    Capa de Seguridad Avanzada VERI*FACTU:
    1. Bloquea el panel /admin/ a los usuarios comunes.
    2. Congela el /dashboard/ y fuerza la verificación de doble factor (SMS/Email).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ruta_actual = request.path

        if request.user.is_authenticated:
            perfil = getattr(request.user, 'perfil', None)
            
            if perfil:
                # REGLA 1: Si no está verificado, SOLO puede estar en la pantalla de meter códigos
                if not perfil.cuenta_verificada and ruta_actual != reverse('verificar_cuenta_view') and not ruta_actual.startswith('/admin/'):
                    return redirect('verificar_cuenta_view')
                
                # REGLA 2: Si intenta entrar al /admin/ sin ser Súper Usuario, lo regresa a su Dashboard
                if ruta_actual.startswith('/admin/') and not request.user.is_superuser:
                    return redirect('dashboard_fiscal')
        else:
            # Si no está logueado e intenta forzar rutas privadas, al login
            if ruta_actual.startswith('/admin/') or ruta_actual.startswith('/dashboard/') or ruta_actual == reverse('verificar_cuenta_view'):
                return redirect('login_usuario')

        response = self.get_response(request)
        return response

