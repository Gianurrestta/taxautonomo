from django.contrib import admin
from .models import PerfilAutonomo, FacturaEmitida, GastoRecibido
from .models import Cotizacion, LineaCotizacion

# Registramos tus modelos con configuraciones limpias para el panel
@admin.register(PerfilAutonomo)
class PerfilAutonomoAdmin(admin.ModelAdmin):
    list_display = ('nombre_fiscal', 'nif_nie', 'regimen_fiscal')
    search_fields = ('nombre_fiscal', 'nif_nie')

@admin.register(FacturaEmitida)
class FacturaEmitidaAdmin(admin.ModelAdmin):
    # CORREGIDO: Eliminamos 'porcentaje_irpf' porque ya no forma parte del modelo
    list_display = ('numero_factura', 'autonomo', 'cliente_nombre', 'base_imponible', 'porcentaje_iva')
    list_filter = ('porcentaje_iva', 'fecha_emision')
    search_fields = ('numero_factura', 'cliente_nombre')

@admin.register(GastoRecibido)
class GastoRecibidoAdmin(admin.ModelAdmin):
    list_display = ('numero_factura_recibida', 'autonomo', 'proveedor_nombre', 'categoria', 'base_imponible', 'porcentaje_iva')
    list_filter = ('categoria', 'fecha_gasto')
    search_fields = ('proveedor_nombre', 'numero_factura_recibida')

class LineaCotizacionInline(admin.TabularInline):
    model = LineaCotizacion
    extra = 1 # Te permite añadir filas dinámicas de elementos cómodamente

@admin.register(Cotizacion)
class CotizacionAdmin(admin.ModelAdmin):
    # CORREGIDO: Eliminamos 'numero_cotizacion' y añadimos teléfono y email para el seguimiento continuo
    list_display = ('titulo_proyecto', 'autonomo', 'cliente_nombre', 'cliente_telefono', 'cliente_email', 'total_base_imponible', 'estado')
    list_filter = ('estado', 'fecha_creacion')
    search_fields = ('titulo_proyecto', 'cliente_nombre', 'cliente_email')
    inlines = [LineaCotizacionInline]

