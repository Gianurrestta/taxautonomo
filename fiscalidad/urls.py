from django.urls import path
from . import views

urlpatterns = [
    # Si entran a la raíz o a /dashboard/, van al panel fiscal
    path('', views.dashboard_fiscal, name='dashboard_fiscal'),
    path('dashboard/', views.dashboard_fiscal, name='dashboard_fiscal'),
    
    # Formulario para emitir la factura oficial
    path('factura/nueva/', views.emitir_factura, name='emitir_factura'),
    
    # Ruta crítica: Descarga del documento PDF (Corregido el parámetro exacto)
    path('factura/descargar/<int:factura_id>/', views.descargar_factura_pdf, name='descargar_factura_pdf'),
    path('cotizacion/descargar/<int:cotizacion_id>/', views.generar_y_enviar_cotizacion_pdf, name='descargar_cotizacion_pdf'),
    path('cotizacion/whatsapp/<int:cotizacion_id>/', views.disparar_whatsapp_cotizacion, name='enviar_whatsapp_cotizacion'),
    path('cotizacion/convertir/<int:cotizacion_id>/', views.convertir_cotizacion_a_factura, name='convertir_a_factura'),
]
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_fiscal, name='dashboard_fiscal'),
    path('dashboard/', views.dashboard_fiscal, name='dashboard_fiscal'),
    path('factura/nueva/', views.emitir_factura, name='emitir_factura'),
    path('factura/descargar/<int:factura_id>/', views.descargar_factura_pdf, name='descargar_factura_pdf'),
    
    # Rutas para presupuestos y automatizaciones
    path('cotizacion/descargar/<int:cotizacion_id>/', views.generar_y_enviar_cotizacion_pdf, name='descargar_cotizacion_pdf'),
    path('cotizacion/whatsapp/<int:cotizacion_id>/', views.disparar_whatsapp_cotizacion, name='enviar_whatsapp_cotizacion'),
    path('cotizacion/convertir/<int:cotizacion_id>/', views.convertir_cotizacion_a_factura, name='convertir_a_factura'),
]
