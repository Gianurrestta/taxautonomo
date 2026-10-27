import urllib.parse
from decimal import Decimal
import datetime
from django.urls import path
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Cotizacion, FacturaEmitida
from . import views

# Funciones Inline Autónomas para WhatsApp y conversión (Se mantienen idénticas)
@login_required
def enviar_whatsapp_directo(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    mensaje = (
        f"Hola {cotizacion.cliente_nombre},\n\n"
        f"Te adjunto el presupuesto para el proyecto: *{cotizacion.titulo_proyecto}*.\n"
        f"Importe estimado: *{cotizacion.total_base_imponible} €*.\n\n"
        f"Puedes revisarlo y confirmar la aceptación respondiendo a este mensaje."
    )
    mensaje_url = urllib.parse.quote(mensaje)
    return redirect(f"https://whatsapp.com{cotizacion.cliente_telefono}&text={mensaje_url}")

@login_required
def convertir_cotizacion_a_factura_directo(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    perfil = cotizacion.autonomo
    if cotizacion.estado == 'FACTURADO':
        return redirect('dashboard_fiscal')
    numero_factura_legal = perfil.obtener_siguiente_numero_factura()
    nueva_factura = FacturaEmitida.objects.create(
        autonomo=perfil,
        cliente=cotizacion.cliente,
        numero_factura=numero_factura_legal,
        concepto=cotizacion.titulo_proyecto,
        base_imponible=cotizacion.total_base_imponible,
        porcentaje_iva=Decimal('0.21'),
        fecha_operacion=datetime.date.today()
    )
    cotizacion.estado = 'FACTURADO'
    cotizacion.save()
    return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)


# MAPEO GLOBAL DE RUTAS (VERIFICACIÓN INTEGRADA)
urlpatterns = [
    # Módulo de Autenticación Multiusuario
    path('login/', views.login_usuario, name='login_usuario'),
    path('registro/', views.registro_autonomo, name='registro_autonomo'),
    path('logout/', views.logout_usuario, name='logout_usuario'),
    
    # NUEVA RUTA: Pantalla intermedia de verificación doble factor
    path('verificar-cuenta/', views.verificar_cuenta_view, name='verificar_cuenta_view'),

    # Vistas de Gestión Principal protegidas por @login_required
    path('', views.dashboard_fiscal, name='dashboard_fiscal'),
    path('dashboard/', views.dashboard_fiscal, name='dashboard_fiscal'),
    path('factura/nueva/', views.emitir_factura, name='emitir_factura'),
    path('factura/descargar/<int:factura_id>/', views.descargar_factura_pdf, name='descargar_factura_pdf'),
    path('cotizacion/descargar/<int:cotizacion_id>/', views.generar_y_enviar_cotizacion_pdf, name='descargar_cotizacion_pdf'),
    
    # Automatizaciones comerciales
    path('cotizacion/whatsapp/<int:cotizacion_id>/', enviar_whatsapp_directo, name='enviar_whatsapp_cotizacion'),
    path('cotizacion/convertir/<int:cotizacion_id>/', convertir_cotizacion_a_factura_directo, name='convertir_a_factura'),
]
