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


class Cliente(models.Model):
    """MÓDULO 1: Directorio y Base de Datos CRM de Clientes del Autónomo"""
    autonomo = models.ForeignKey(PerfilAutonomo, on_delete=models.CASCADE, related_name='clientes_crm')
    nombre_o_razon_social = models.CharField(max_length=150, verbose_name="Nombre o Razón Social")
    nif_nie = models.CharField(max_length=15, verbose_name="NIF / NIE")
    domicilio_fiscal = models.CharField(max_length=255, verbose_name="Domicilio Fiscal")
    telefono = models.CharField(max_length=20, help_text="Formato internacional, ej: +34600000000 para WhatsApp")
    email = models.EmailField(verbose_name="Correo Electrónico")
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('autonomo', 'nif_nie') # Evita duplicar el mismo cliente para un mismo autónomo

    def __str__(self):
        return f"{self.nombre_o_razon_social} ({self.nif_nie})"


class FacturaEmitida(models.Model):
    """Estructura de Facturación adaptada a VERI*FACTU vinculada al CRM"""
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
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='facturas', null=True, help_text="Cliente desde la base de datos CRM")
    tipo_serie = models.CharField(max_length=15, choices=TIPOS_SERIE, default='ORDINARIA')
    numero_factura = models.CharField(max_length=50)
    fecha_emision = models.DateField(auto_now_add=True)
    fecha_operacion = models.DateField(default=datetime.date.today)
    
    # Mantenemos los campos de texto como copia estática histórica (Exigencia legal si el cliente cambia de dirección)
    cliente_nombre = models.CharField(max_length=150, blank=True)
    cliente_nif = models.CharField(max_length=15, blank=True)
    cliente_domicilio = models.CharField(max_length=255, blank=True)
    
    concepto = models.CharField(max_length=250, default="Servicios profesionales prestados")
    base_imponible = models.DecimalField(max_digits=12, decimal_places=2)
    porcentaje_iva = models.DecimalField(max_digits=4, decimal_places=2, choices=TIPOS_IVA, default=Decimal('0.21'))
    hash_verifactu = models.CharField(max_length=64, blank=True)

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

        ultima_factura = FacturaEmitida.objects.filter(autonomo=self.autonomo, tipo_serie=self.tipo_serie).order_by('-id').first()
        if ultima_factura and self.fecha_emision and self.fecha_emision < ultima_factura.fecha_emision:
            raise ValidationError(f"Incumplimiento Cronológico AEAT.")

    def save(self, *args, **kwargs):
        # Al guardar, si se seleccionó un cliente del CRM, congelamos sus datos fiscales actuales en la factura
        if self.cliente:
            self.cliente_nombre = self.cliente.nombre_o_razon_social
            self.cliente_nif = self.cliente.nif_nie
            self.cliente_domicilio = self.cliente.domicilio_fiscal
            
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
    """Presupuestos vinculados de forma directa a la tabla unificada de Clientes"""
    ESTADOS = [
        ('BORRADOR', 'Borrador / En edición'),
        ('ENVIADO', 'Enviado al Cliente'),
        ('ACEPTADO', 'Aceptado (Listo para facturar)'),
        ('FACTURADO', 'Convertido en Factura'),
    ]

    autonomo = models.ForeignKey(PerfilAutonomo, on_delete=models.CASCADE, related_name='cotizaciones')
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='cotizaciones', null=True)
    titulo_proyecto = models.CharField(max_length=250)
    
    # Copias estáticas para resguardo comercial rápido
    cliente_nombre = models.CharField(max_length=150, blank=True)
    cliente_nif = models.CharField(max_length=15, blank=True)
    cliente_telefono = models.CharField(max_length=20, blank=True)
    cliente_email = models.EmailField(blank=True)
    
    estado = models.CharField(max_length=10, choices=ESTADOS, default='BORRADOR')
    fecha_creacion = models.DateField(auto_now_add=True)

    @property
    def total_base_imponible(self) -> Decimal:
        total = sum(linea.coste_total for linea in self.lineas.all())
        return Decimal(total).quantize(Decimal('0.01'))

    def save(self, *args, **kwargs):
        if self.cliente:
            self.cliente_nombre = self.cliente.nombre_o_razon_social
            self.cliente_nif = self.cliente.nif_nie
            self.cliente_telefono = self.cliente.telefono
            self.cliente_email = self.cliente.email
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titulo_proyecto} - {self.cliente_nombre}"


class LineaCotizacion(models.Model):
    cotizacion = models.ForeignKey(Cotizacion, on_delete=models.CASCADE, related_name='lineas')
    descripcion_elemento = models.CharField(max_length=250)
    width = models.PositiveIntegerField(default=1) # Cantidad
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def coste_total(self) -> Decimal:
        return (Decimal(self.width) * self.precio_unitario).quantize(Decimal('0.01'))


class GastoRecibido(models.Model):
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
