import datetime
import hashlib
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class PerfilAutonomo(models.Model):
    """Información fiscal y mercantil obligatoria del autónomo emisor en España"""
    REGIMENES = [
        ('EDV', 'Estimación Directa Simplificada'),
        ('EDN', 'Estimación Directa Normal'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    nif_nie = models.CharField(max_length=15, unique=True, verbose_name="NIF o NIE")
    nombre_fiscal = models.CharField(max_length=150)
    domicilio_fiscal = models.CharField(max_length=255, default='', help_text="Dirección obligatoria ante la AEAT")
    telefono = models.CharField(max_length=20, blank=True, null=True)
    actividad_profesional = models.CharField(max_length=100, help_text="Ej: Desarrollo Web, Asesoría Jurídica", blank=True, null=True)
    logo = models.ImageField(upload_to="logos_autonomos/", blank=True, null=True)
    regimen_fiscal = models.CharField(max_length=3, choices=REGIMENES, default='EDV')

    def obtener_siguiente_numero_factura(self, tipo_serie='ORDINARIA') -> str:
        """Regla de Oro 2: Generación automática correlativa y cronológica segmentada por Series"""
        año_actual = datetime.date.today().year
        prefijo = f"F-{año_actual}-" if tipo_serie == 'ORDINARIA' else f"R-{año_actual}-"
        
        facturas_serie = FacturaEmitida.objects.filter(
            autonomo=self,
            numero_factura__startswith=prefijo
        )
        
        numero_mas_alto = 0
        for f in facturas_serie:
            try:
                numero_str = f.numero_factura.replace(prefijo, "")
                numero_int = int(numero_str)
                if numero_int > numero_mas_alto:
                    numero_mas_alto = numero_int
            except ValueError:
                pass
        
        siguiente_numero = numero_mas_alto + 1
        return f"{prefijo}{siguiente_numero:04d}"

    def __str__(self):
        return f"{self.nombre_fiscal} ({self.nif_nie})"


class FacturaEmitida(models.Model):
    """Estructura de Facturación Ordinaria y Rectificativa adaptada a VERI*FACTU"""
    TIPOS_SERIE = [
        ('ORDINARIA', 'Serie F (Ordinaria / Venta)'),
        ('RECTIFICATIVA', 'Serie R (Rectificativa / Modificación)'),
    ]
    TIPOS_IVA = [
        (Decimal('0.21'), '21% (General)'),
        (Decimal('0.10'), '10% (Reducido)'),
        (Decimal('0.04'), '4% (Superreducido)'),
        (Decimal('0.00'), '0% (Exento)'),
    ]

    autonomo = models.ForeignKey(PerfilAutonomo, on_delete=models.CASCADE, related_name='facturas_emitidas')
    tipo_serie = models.CharField(max_length=15, choices=TIPOS_SERIE, default='ORDINARIA')
    numero_factura = models.CharField(max_length=50, help_text="Numeración correlativa anual (Ej: 2026-0001)")
    fecha_emision = models.DateField(auto_now_add=True, help_text="Día exacto en que se genera la factura")
    fecha_operacion = models.DateField(default=datetime.date.today, help_text="Día en que se prestó el servicio")
    
    cliente_nombre = models.CharField(max_length=150, verbose_name="Nombre / Razón Social Cliente")
    cliente_nif = models.CharField(max_length=15, verbose_name="NIF/NIE Cliente")
    cliente_domicilio = models.CharField(max_length=255, default='', verbose_name="Domicilio Fiscal Cliente")
    
    concepto = models.CharField(max_length=250, default="Servicios profesionales prestados")
    base_imponible = models.DecimalField(max_digits=12, decimal_places=2)
    porcentaje_iva = models.DecimalField(max_digits=4, decimal_places=2, choices=TIPOS_IVA, default=Decimal('0.21'))
    hash_verifactu = models.CharField(max_length=64, blank=True, help_text="Huella de encadenamiento inalterable")

    class Meta:
        unique_together = ('autonomo', 'numero_factura')
        ordering = ['fecha_emision', 'numero_factura']

    @property
    def total_iva(self) -> Decimal:
        return (self.base_imponible * self.porcentaje_iva).quantize(Decimal('0.01'))

    @property
    def total_factura(self) -> Decimal:
        return (self.base_imponible + self.total_iva).quantize(Decimal('0.01'))

    def clean(self):
        super().clean()
        if self.fecha_operacion > datetime.date.today():
            raise ValidationError({"fecha_operacion": "La fecha de la operación no puede ser una fecha futura."})

        ultima_factura = FacturaEmitida.objects.filter(
            autonomo=self.autonomo,
            tipo_serie=self.tipo_serie
        ).order_by('-id').first()

        if ultima_factura and self.fecha_emision:
            if self.fecha_emision < ultima_factura.fecha_emision:
                raise ValidationError(
                    f"Incumplimiento Cronológico AEAT: No puedes emitir la factura con fecha {self.fecha_emision} "
                    f"porque la última factura de la serie ({ultima_factura.numero_factura}) tiene fecha {ultima_factura.fecha_emision}."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.hash_verifactu:
            ultima = FacturaEmitida.objects.filter(autonomo=self.autonomo).order_by('-id').first()
            hash_anterior = ultima.hash_verifactu if ultima else "INICIO_SERIE_VERIFACTU"
            cadena_datos = f"{self.numero_factura}|{self.fecha_emision}|{self.base_imponible}|{self.total_factura}|{hash_anterior}"
            self.hash_verifactu = hashlib.sha256(cadena_datos.encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.tipo_serie}] {self.numero_factura} - {self.cliente_nombre}"


class Cotizacion(models.Model):
    """Presupuestos comerciales identificados por nombre y con datos de contacto del cliente"""
    ESTADOS = [
        ('BORRADOR', 'Borrador / En edición'),
        ('ENVIADO', 'Enviado al Cliente'),
        ('ACEPTADO', 'Aceptado (Listo para facturar)'),
        ('FACTURADO', 'Convertido en Factura'),
    ]

    autonomo = models.ForeignKey(PerfilAutonomo, on_delete=models.CASCADE, related_name='cotizaciones')
    titulo_proyecto = models.CharField(max_length=250, help_text="Nombre de la cotización que identificará el proyecto")
    cliente_nombre = models.CharField(max_length=150, verbose_name="Consumidor Final")
    cliente_nif = models.CharField(max_length=15, verbose_name="NIF/NIE del Cliente")
    cliente_telefono = models.CharField(max_length=20, default='', help_text="Formato internacional, ej: +34600000000")
    cliente_email = models.EmailField(default='')
    estado = models.CharField(max_length=10, choices=ESTADOS, default='BORRADOR')
    fecha_creacion = models.DateField(auto_now_add=True)

    @property
    def total_base_imponible(self) -> Decimal:
        total = sum(linea.coste_total for linea in self.lineas.all())
        return Decimal(total).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.titulo_proyecto} - {self.cliente_nombre} ({self.total_base_imponible}€)"


class LineaCotizacion(models.Model):
    """Elementos o rubros individuales incluidos en una cotización específica"""
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='lineas')
    descripcion_elemento = models.CharField(max_length=250)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def coste_total(self) -> Decimal:
        return (Decimal(self.cantidad) * self.precio_unitario).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.descripcion_elemento} x {self.cantidad}"


class GastoRecibido(models.Model):
    """Gastos soportados vinculados obligatoriamente a un documento digitalizado"""
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

    def __str__(self):
        return f"[{self.estado_pago}] {self.proveedor_nombre} - {self.total_gasto}€"
