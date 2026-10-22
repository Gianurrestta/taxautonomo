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
    path('cotizacion/convertir/<int:cotizacion_id>/', views.convertir_cotizacion_a_factura, name='convertir_a_factura'),
]
