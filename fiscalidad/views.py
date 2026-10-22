import datetime
from decimal import Decimal

# Importaciones nativas de Django (Seguridad, Atajos y Vistas)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

# Importaciones para la generación matemática de PDFs (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Importaciones de tu propia aplicación fiscal determinista
from .models import PerfilAutonomo, FacturaEmitida, GastoRecibido, Cotizacion
from .services import calcular_impuestos_trimestre


@login_required
def dashboard_fiscal(request):
    """Pantalla principal donde el cliente ve sus impuestos e imágenes de facturas del mes"""
    try:
        perfil = request.user.perfil
    except PerfilAutonomo.DoesNotExist:
        return render(request, 'fiscalidad/no_perfil.html')

    hoy = datetime.date.today()
    # Cálculo automatizado del trimestre fiscal actual en España
    trimestre_actual = (hoy.month - 1) // 3 + 1
    
    # Motor fiscal de Python puro sin interpretaciones de IA
    datos_fiscales = calcular_impuestos_trimestre(perfil, hoy.year, trimestre_actual)
    
    # Consultas controladas a la base de datos local
    gastos_mes = GastoRecibido.objects.filter(
        autonomo=perfil, 
        fecha_gasto__year=hoy.year, 
        fecha_gasto__month=hoy.month
    )
    facturas_mes = FacturaEmitida.objects.filter(
        autonomo=perfil, 
        fecha_emision__year=hoy.year, 
        fecha_emision__month=hoy.month
    )

    context = {
        'datos_fiscales': datos_fiscales,
        'gastos_mes': gastos_mes,
        'facturas_mes': facturas_mes,
    }
    return render(request, 'fiscalidad/dashboard.html', context)


@login_required
def emitir_factura(request):
    """Formulario seguro con cálculo automático de número correlativo legal en tiempo de guardado"""
    try:
        perfil = request.user.perfil
    except PerfilAutonomo.DoesNotExist:
        return render(request, 'fiscalidad/no_perfil.html')

    # Para mostrar en pantalla de forma orientativa antes de enviar
    numero_provisional = perfil.obtener_siguiente_numero_factura()

    if request.method == 'POST':
        cliente = request.POST.get('cliente_nombre')
        nif = request.POST.get('cliente_nif')
        concepto = request.POST.get('concepto', 'Servicios profesionales')
        base = request.POST.get('base_imponible', '0.00')
        iva = request.POST.get('porcentaje_iva', '0.21')
        
        # FIJACIÓN EN MILISEGUNDO DE GUARDADO: Evita colisiones de concurrencia y duplicados
        numero_definitivo = perfil.obtener_siguiente_numero_factura()
        
        nueva_factura = FacturaEmitida.objects.create(
            autonomo=perfil,
            numero_factura=numero_definitivo, # Se asigna el número real disponible
            cliente_nombre=cliente,
            cliente_nif=nif,
            concepto=concepto,
            base_imponible=Decimal(base),
            porcentaje_iva=Decimal(iva)
        )
        return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)

    return render(request, 'fiscalidad/emitir_factura.html', {'siguiente_numero': numero_provisional})

@login_required
def descargar_factura_pdf(request, factura_id):
    """Tarea 1: Generación de PDF profesional descargable estructurado por rubros"""
    factura = get_object_or_404(FacturaEmitida, id=factura_id, autonomo__user=request.user)
    autonomo = factura.autonomo

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Factura_{factura.numero_factura}.pdf"'

    # Inicialización del lienzo del documento
    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()

    # Estilos visuales del documento comercial
    titulo_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#2c3e50'), spaceAfter=20)
    normal_style = styles['Normal']
    bold_style = ParagraphStyle('BoldStyle', parent=normal_style, fontName='Helvetica-Bold')

    story.append(Paragraph(f"FACTURA OFICIAL: {factura.numero_factura}", titulo_style))
    story.append(Spacer(1, 15))

    # Bloque organizativo: Datos del Autónomo Emisor frente al Cliente
    datos_emisor = [
        [Paragraph("<strong>EMISOR (Autónomo):</strong>", normal_style), Paragraph("<strong>CLIENTE:</strong>", normal_style)],
        [Paragraph(f"{autonomo.nombre_fiscal}", normal_style), Paragraph(f"{factura.cliente_nombre}", normal_style)],
        [Paragraph(f"NIF/NIE: {autonomo.nif_nie}", normal_style), Paragraph(f"NIF/NIE: {factura.cliente_nif}", normal_style)],
        [Paragraph(f"Teléfono: {autonomo.telefono or 'N/A'}", normal_style), Paragraph("", normal_style)],
        [Paragraph(f"Actividad: {autonomo.actividad_profesional or 'Servicios Profesionales'}", normal_style), Paragraph("", normal_style)],
    ]
    
    # Anchos fijos en puntos para el bloque de datos (260pt por columna)
    table_datos = Table(datos_emisor, colWidths=[260, 260])
    table_datos.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(table_datos)
    story.append(Spacer(1, 30))

       # Tabla Desglosada del Cobro por Rubros (Versión blindada contra textos largos)
    headers_tabla = [
        [Paragraph("<strong>Concepto / Rubro</strong>", bold_style), 
         Paragraph("<strong>Base Imponible</strong>", bold_style), 
         Paragraph("<strong>IVA %</strong>", bold_style), 
         Paragraph("<strong>Cuota IVA</strong>", bold_style), 
         Paragraph("<strong>Total Neto</strong>", bold_style)]
    ]
    
    cuerpo_tabla = [
        [Paragraph(factura.concepto, normal_style), 
         Paragraph(f"{factura.base_imponible} €", normal_style), 
         Paragraph(f"{factura.porcentaje_iva * 100:.0f}%", normal_style), 
         Paragraph(f"{factura.total_iva} €", normal_style), 
         Paragraph(f"{factura.total_factura} €", normal_style)]
    ]
    
    # Dimensiones exactas de la rejilla (220, 75, 55, 80, 90)
    tabla_factura = Table(headers_tabla + cuerpo_tabla, colWidths=[220, 75, 55, 80, 90])
    tabla_factura.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))

    
    story.append(tabla_factura)
    doc.build(story)
    return response

@login_required
def convertir_cotizacion_a_factura(request, cotizacion_id):
    """Transforma una cotización en una factura oficial con coste final acumulado"""
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    perfil = cotizacion.autonomo

    if cotizacion.estado == 'FACTURADO':
        # Evitamos que se duplique la factura por seguridad si recargan la página
        return redirect('dashboard_fiscal')

    # 1. Determinamos matemáticamente el siguiente consecutivo legal en el milisegundo exacto
    numero_factura_legal = perfil.obtener_siguiente_numero_factura()

    # 2. Inyección estricta en la tabla de Facturas Emitidas
    nueva_factura = FacturaEmitida.objects.create(
        autonomo=perfil,
        numero_factura=numero_factura_legal,
        cliente_nombre=cotizacion.cliente_nombre,
        cliente_nif=cotizacion.cliente_nif,
        concepto=cotizacion.titulo_proyecto,               # El título comercial pasa a ser el concepto fiscal
        base_imponible=cotizacion.total_base_imponible,   # Coste final acumulado del desglose
        porcentaje_iva=Decimal('0.21')                    # IVA estándar español por defecto
    )

    # 3. Actualizamos el estado comercial de la cotización para congelarla
    cotizacion.estado = 'FACTURADO'
    cotizacion.save()

    # Redirigimos instantáneamente a la descarga segura del PDF oficial de la factura
    return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)

