import datetime
from decimal import Decimal
from .models import FacturaEmitida, GastoRecibido, PerfilAutonomo

def calcular_impuestos_trimestre(perfil: PerfilAutonomo, año: int, trimestre: int) -> dict:
    """
    Calcula estrictamente las liquidaciones de IVA (Modelo 303) e IRPF (Modelo 130)
    en base a los ingresos reales y los gastos justificados con documento digital.
    """
    # Determinamos los meses del trimestre de forma segura
    if trimestre == 1:
        mes_inicio, mes_fin = 1, 3
    elif trimestre == 2:
        mes_inicio, mes_fin = 4, 6
    elif trimestre == 3:
        mes_inicio, mes_fin = 7, 9
    elif trimestre == 4:
        mes_inicio, mes_fin = 10, 12
    else:
        raise ValueError("Trimestre no válido. Debe ser del 1 al 4.")

    # 1. Sumatorio estricto de Ingresos (Facturas Emitidas de la Serie F)
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

    # 2. Sumatorio estricto de Gastos Deducibles (Con factura digital obligatoria)
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

    # 3. REGLAS DETERMINISTAS DE LA AGENCIA TRIBUTARIA (AEAT)
    
    # MODELO 303: IVA Repercutido (Cobrado) - IVA Soportado (Pagado)
    resultado_iva_303 = (iva_devengado_total - iva_deducible_total).quantize(Decimal('0.01'))
    
    # MODELO 130: Rendimiento Neto de la Actividad (Ingresos - Gastos)
    rendimiento_neto = total_ingresos_base - total_gastos_base
    
    # Si hay beneficio, se anticipa el 20% a cuenta. Si hay pérdidas, es 0.00€
    if rendimiento_neto > 0:
        resultado_irpf_130 = (rendimiento_neto * Decimal('0.20')).quantize(Decimal('0.01'))
    else:
        resultado_irpf_130 = Decimal('0.00')

    return {
        "ejercicio": año,
        "trimestre": f"{trimestre}º Trimestre",
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
