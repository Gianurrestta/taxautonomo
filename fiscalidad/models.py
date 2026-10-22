from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import datetime

class PerfilAutonomo(models.Model):
    """Información fiscal y comercial completa del autónomo"""
    REGIMENES = [
        ('EDV', 'Estimación Directa Simplificada'),
        ('EDN', 'Estimación Directa Normal'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    nif_nie = models.CharField(max_length=15, unique=True, verbose_name="NIF o NIE")
    nombre_fiscal = models.CharField(max_length=150)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    actividad_profesional = models.CharField(max_length=100, help_text="Ej: Desarrollo Web, Asesoría Jurídica", blank=True, null=True)
    logo = models.ImageField(upload_to="logos_autonomos/", blank=True, null=True)
    regimen_fiscal = models.CharField(max_length=3, choices=REGIMENES, default='EDV')
    es_nuevo_autonomo = models.BooleanField(default=False)

    def obtener_siguiente_numero_factura(self) -> str:
        """Genera de forma matemática estricta el siguiente consecutivo ignorando textos corruptos"""
        año_actual = datetime.date.today().year
        prefijo = f"F-{año_actual}-"
        
        # Buscamos todas las facturas de este año para este autónomo
        facturas_año = FacturaEmitida.objects.filter(
            autonomo=self,
            numero_factura__startswith=prefijo
        )
        
        numero_mas_alto = 0
        
        # Recorremos las facturas para encontrar el número matemático más alto real
        for f in facturas_año:
            try:
                # Extraemos solo la parte numérica final despues del prefijo
                numero_str = f.numero_factura.replace(prefijo, "")
                numero_int = int(numero_str)
                if numero_int > numero_mas_alto:
                    numero_mas_alto = numero_int
            except ValueError:
                # Si hay una factura corrupta con texto manual, la ignora para no romper el sistema
                pass
        
        # El siguiente número será el más alto encontrado + 1
        siguiente_numero = numero_mas_alto + 1
        return f"{prefijo}{siguiente_numero:04d}"

    def __str__(self):
        return f"{self.nombre_fiscal} - {self.actividad_profesional or 'Autónomo'}"

class FacturaEmitida(models.Model):
    """Facturas emitidas por el autónomo (Ingresos)"""
    TIPOS_IVA = [
        (Decimal('0.21'), '21% (General)'),
        (Decimal('0.10'), '10% (Reducido)'),
        (Decimal('0.04'), '4% (Superreducido)'),
        (Decimal('0.00'), '0% (Exento)'),
    ]
    
    autonomo = models.ForeignKey(PerfilAutonomo, on_delete=models.CASCADE, related_name='facturas_emitidas')
    numero_factura = models.CharField(max_length=50)
    fecha_emision = models.DateField(auto_now_add=True)
    cliente_nombre = models.CharField(max_length=150)
    cliente_nif = models.CharField(max_length=15)
    concepto = models.CharField(max_length=250, default="Servicios profesionales prestados")
    
    base_imponible = models.DecimalField(max_digits=12, decimal_places=2)
    porcentaje_iva = models.DecimalField(max_digits=4, decimal_places=2, choices=TIPOS_IVA, default=Decimal('0.21'))

    class Meta:
        unique_together = ('autonomo', 'numero_factura')

    @property
    def total_iva(self) -> Decimal:
        return (self.base_imponible * self.porcentaje_iva).quantize(Decimal('0.01'))

    @property
    def total_factura(self) -> Decimal:
        return (self.base_imponible + self.total_iva).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.numero_factura} - {self.cliente_nombre}"


class GastoRecibido(models.Model):
    """Gastos soportados vinculados a un documento digitalizado"""
    CATEGORIAS_HACIENDA = [
        ('ALM', 'Arrendamientos y cánones (Alquileres)'),
        ('CON', 'Conservación y reparación'),
        ('SPS', 'Servicios de profesionales independientes'),
        ('SUR', 'Suministros (Agua, Luz, Gas, Internet)'),
        ('TRA', 'Transportes y desplazamientos públicos'),
        ('PBL', 'Publicidad y relaciones públicas'),
        ('OEX', 'Otros gastos fiscalmente deducibles'),
    ]
    ESTADOS_PAGO = [('PENDIENTE', 'Por Pagar'), ('PAGADO', 'Pagada')]

    autonomo = models.ForeignKey(PerfilAutonomo, on_delete=models.CASCADE, related_name='gastos_recibidos')
    proveedor_nombre = models.CharField(max_length=150)
    proveedor_nif = models.CharField(max_length=15)
    numero_factura_recibida = models.CharField(max_length=50)
    fecha_gasto = models.DateField()
    categoria = models.CharField(max_length=3, choices=CATEGORIAS_HACIENDA, default='OEX')
    base_imponible = models.DecimalField(max_digits=12, decimal_places=2)
    porcentaje_iva = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0.21'))
    estado_pago = models.CharField(max_length=10, choices=ESTADOS_PAGO, default='PENDIENTE')
    fecha_pago_real = models.DateField(null=True, blank=True)
    factura_digital = models.FileField(upload_to="facturas_proveedores/", null=True, blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    @property
    def total_iva_soportado(self) -> Decimal:
        return (self.base_imponible * self.porcentaje_iva).quantize(Decimal('0.01'))

    @property
    def total_gasto(self) -> Decimal:
        return (self.base_imponible + self.total_iva_soportado).quantize(Decimal('0.01'))
