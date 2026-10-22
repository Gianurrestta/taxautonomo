from decimal import Decimal
from .models import FacturaEmitida, GastoRecibido, PerfilAutonomo

def calcular_impuestos_trimestre(perfil: PerfilAutonomo, año: int, trimestre: int) -> dict:
    """
    Calcula estrictamente las liquidaciones de IVA (Modelo 303) e IRPF (Modelo 130)
    en base a la normativa de la Agencia Tributaria Española.
    """
    # Determinamos los meses de inicio y fin de manera directa y segura sin diccionarios
    if trimestre == 1:
        mes_inicio, mes_fin = 1, 3   # Enero a Marzo
    elif trimestre == 2:
        mes_inicio, mes_fin = 4, 6   # Abril a Junio
    elif trimestre == 3:
        mes_inicio, mes_fin = 7, 9   # Julio a Septiembre
    elif trimestre == 4:
        mes_inicio, mes_fin = 10, 12 # Octubre a Diciembre
    else:
        raise ValueError("Trimestre no válido. Debe ser del 1 al 4.")

    # 1. Obtener y sumar Ingresos (Facturas Emitidas) del periodo exacto
    ingresos = FacturaEmitida.objects.filter(
        autonomo=perfil,
        fecha_emision__year=año,
        fecha_emision__month__gte=mes_inicio,
        fecha_emision__month__lte=mes_fin
    )
    
    total_ingresos_base = Decimal('0.00')
    iva_devengado_total = Decimal('0.00')
    
    for f in ingresos:
        total_ingresos_base += f.base_imponible
        iva_devengado_total += f.total_iva

    # 2. Obtener y sumar Gastos Deducibles del periodo exacto
    gastos = GastoRecibido.objects.filter(
        autonomo=perfil,
        fecha_gasto__year=año,
        fecha_gasto__month__gte=mes_inicio,
        fecha_gasto__month__lte=mes_fin
    )
    
    total_gastos_base = Decimal('0.00')
    iva_deducible_total = Decimal('0.00')
    
    for g in gastos:
        total_gastos_base += g.base_imponible
        iva_deducible_total += g.total_iva_soportado

    # 3. EJECUCIÓN DE REGLAS FISCALES DETERMINISTAS
    
    # MODELO 303 (IVA): IVA Cobrado - IVA Pagado
    resultado_iva_303 = (iva_devengado_total - iva_deducible_total).quantize(Decimal('0.01'))
    
    # MODELO 130 (IRPF): 20% del rendimiento neto (Ingresos Base - Gastos Base)
    rendimiento_neto = total_ingresos_base - total_gastos_base
    
    if rendimiento_neto > 0:
        resultado_irpf_130 = (rendimiento_neto * Decimal('0.20')).quantize(Decimal('0.01'))
    else:
        resultado_irpf_130 = Decimal('0.00')

    return {
        "ejercicio": año,
        "trimestre": f"{trimestre}T",
        "resumen_ingresos": {
            "base_imponible_total": total_ingresos_base.quantize(Decimal('0.01')),
            "iva_repercutido": iva_devengado_total.quantize(Decimal('0.01')),
        },
        "resumen_gastos": {
            "base_imponible_total": total_gastos_base.quantize(Decimal('0.01')),
            "iva_deducible": iva_deducible_total.quantize(Decimal('0.01')),
        },
        "rendimiento_neto_actividad": rendimiento_neto.quantize(Decimal('0.01')),
        "modelo_303_iva_a_ingresar": resultado_iva_303,
        "modelo_130_irpf_a_ingresar": resultado_irpf_130
    }
