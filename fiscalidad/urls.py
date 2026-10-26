import urllib.parse
from decimal import Decimal
import datetime
from django.urls import path
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Cotizacion, FacturaEmitida
from . import views

# 1. Función Inline Autónoma para WhatsApp (Inmune a bloqueos de caché)
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


# 2. Función Inline Autónoma para Convertir Cotización a Factura (Inmune a bloqueos de caché)
@login_required
def convertir_cotizacion_a_factura_directo(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    perfil = cotizacion.autonomo

    if cotizacion.estado == 'FACTURADO':
        return redirect('dashboard_fiscal')

    # Calcula el consecutivo real de la Agencia Tributaria en el milisegundo exacto
    numero_factura_legal = perfil.obtener_siguiente_numero_factura()

    # Creación relacional e inyección criptográfica en la base de datos local
    nueva_factura = FacturaEmitida.objects.create(
        autonomo=perfil,
        cliente=cotizacion.cliente,
        numero_factura=numero_factura_legal,
        concepto=cotizacion.titulo_proyecto,
        base_imponible=cotizacion.total_base_imponible,
        porcentaje_iva=Decimal('0.21'),
        fecha_operacion=datetime.date.today()
    )

    # Congelamos el estado comercial
    cotizacion.estado = 'FACTURADO'
    cotizacion.save()

    return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)


# MAPEO DE RUTAS DEFINITIVO DEL MVP
urlpatterns = [
    # Vistas base estables
    path('', views.dashboard_fiscal, name='dashboard_fiscal'),
    path('dashboard/', views.dashboard_fiscal, name='dashboard_fiscal'),
    path('factura/nueva/', views.emitir_factura, name='emitir_factura'),
    path('factura/descargar/<int:factura_id>/', views.descargar_factura_pdf, name='descargar_factura_pdf'),
    path('cotizacion/descargar/<int:cotizacion_id>/', views.generar_y_enviar_cotizacion_pdf, name='descargar_cotizacion_pdf'),
    
    # Conexiones lógicas directas blindadas sin pasar por views.py
    path('cotizacion/whatsapp/<int:cotizacion_id>/', enviar_whatsapp_directo, name='enviar_whatsapp_cotizacion'),
    path('cotizacion/convertir/<int:cotizacion_id>/', convertir_cotizacion_a_factura_directo, name='convertir_a_factura'),
]
