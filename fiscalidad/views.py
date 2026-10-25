import datetime
from decimal import Decimal
import urllib.parse

# Importaciones nativas de Django
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

# Importaciones para la generación de PDFs (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Importaciones de tu propia aplicación fiscal (CORREGIDO)
from .models import PerfilAutonomo, FacturaEmitida, GastoRecibido, Cotizacion, Cliente
from .services import calcular_impuestos_trimestre


@login_required
def dashboard_fiscal(request):
    """Pantalla principal donde el cliente ve sus impuestos, gastos y sus presupuestos comerciales"""
    try:
        perfil = request.user.perfil
    except PerfilAutonomo.DoesNotExist:
        return render(request, 'fiscalidad/no_perfil.html')

    hoy = datetime.date.today()
    trimestre_actual = (hoy.month - 1) // 3 + 1
    
    from .services import calcular_impuestos_trimestre
    datos_fiscales = calcular_impuestos_trimestre(perfil, hoy.year, trimestre_actual)
    
    gastos_mes = GastoRecibido.objects.filter(autonomo=perfil, fecha_gasto__year=hoy.year, fecha_gasto__month=hoy.month)
    facturas_mes = FacturaEmitida.objects.filter(autonomo=perfil, fecha_emision__year=hoy.year, fecha_emision__month=hoy.month)
    
    # NUEVA CONSULTA: Extraemos todos los presupuestos de este autónomo para el seguimiento
    cotizaciones_usuario = Cotizacion.objects.filter(autonomo=perfil).order_by('-fecha_creacion')

    context = {
        'datos_fiscales': datos_fiscales,
        'gastos_mes': gastos_mes,
        'facturas_mes': facturas_mes,
        'cotizaciones_usuario': cotizaciones_usuario, # <--- ENVIADO AL HTML
    }
    return render(request, 'fiscalidad/dashboard.html', context)


@login_required
def emitir_factura(request):
    """Formulario seguro conectado directamente a la base de datos de Clientes CRM"""
    try:
        perfil = request.user.perfil
    except PerfilAutonomo.DoesNotExist:
        return render(request, 'fiscalidad/no_perfil.html')

    numero_provisional = perfil.obtener_siguiente_numero_factura()
    # Obtenemos todos los clientes registrados por este autónomo en su CRM
    mis_clientes = Cliente.objects.filter(autonomo=perfil).order_by('nombre_o_razon_social')

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        concepto = request.POST.get('concepto', 'Servicios profesionales')
        base = request.POST.get('base_imponible', '0.00')
        iva = request.POST.get('porcentaje_iva', '0.21')
        fecha_op = request.POST.get('fecha_operacion')
        
        # Recuperamos la ficha del cliente desde el CRM unificado
        cliente_instancia = get_object_or_404(Cliente, id=cliente_id, autonomo=perfil)
        numero_definitivo = perfil.obtener_siguiente_numero_factura()
        
        nueva_factura = FacturaEmitida.objects.create(
            autonomo=perfil,
            cliente=cliente_instancia, # Vinculación relacional directa
            numero_factura=numero_definitivo,
            concepto=concepto,
            base_imponible=Decimal(base),
            porcentaje_iva=Decimal(iva),
            fecha_operacion=datetime.datetime.strptime(fecha_op, '%Y-%m-%d').date() if fecha_op else datetime.date.today()
        )
        return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)

    context = {
        'siguiente_numero': numero_provisional,
        'mis_clientes': mis_clientes # Enviado para el select en el HTML
    }
    return render(request, 'fiscalidad/emitir_factura.html', context)

@login_required
def descargar_factura_pdf(request, factura_id):
    """Generación de PDF profesional descargable estructurado por rubros"""
    factura = get_object_or_404(FacturaEmitida, id=factura_id, autonomo__user=request.user)
    autonomo = factura.autonomo

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Factura_{factura.numero_factura}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#2c3e50'), spaceAfter=20)
    normal_style = styles['Normal']
    bold_style = ParagraphStyle('BoldStyle', parent=normal_style, fontName='Helvetica-Bold')

    story.append(Paragraph(f"FACTURA OFICIAL: {factura.numero_factura}", titulo_style))
    story.append(Spacer(1, 15))

    datos_emisor = [
        [Paragraph("<strong>EMISOR (Autónomo):</strong>", normal_style), Paragraph("<strong>CLIENTE:</strong>", normal_style)],
        [Paragraph(f"{autonomo.nombre_fiscal}", normal_style), Paragraph(f"{factura.cliente_nombre}", normal_style)],
        [Paragraph(f"NIF/NIE: {autonomo.nif_nie}", normal_style), Paragraph(f"NIF/NIE: {factura.cliente_nif}", normal_style)],
        [Paragraph(f"Teléfono: {autonomo.telefono or 'N/A'}", normal_style), Paragraph("", normal_style)],
        [Paragraph(f"Actividad: {autonomo.actividad_profesional or 'Servicios Profesionales'}", normal_style), Paragraph("", normal_style)],
    ]
    
    table_datos = Table(datos_emisor, colWidths=[260, 260])
    table_datos.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
    story.append(table_datos)
    story.append(Spacer(1, 30))

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
def generar_y_enviar_cotizacion_pdf(request, cotizacion_id):
    """Fase 1: Descarga el PDF desglosado comercial de la Cotización"""
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    autonomo = cotizacion.autonomo

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Presupuesto_{cotizacion.id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    
    titulo_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#2c3e50'), spaceAfter=20)
    normal_style = styles['Normal']
    bold_style = ParagraphStyle('Bold', parent=normal_style, fontName='Helvetica-Bold')

    story.append(Paragraph(f"PRESUPUESTO COMERCIAL: {cotizacion.titulo_proyecto}", titulo_style))
    story.append(Spacer(1, 15))

    datos_contacto = [
        [Paragraph("<strong>EMISOR:</strong>", normal_style), Paragraph("<strong>CLIENTE (Consumidor Final):</strong>", normal_style)],
        [Paragraph(f"{autonomo.nombre_fiscal}", normal_style), Paragraph(f"{cotizacion.cliente_nombre}", normal_style)],
        [Paragraph(f"NIF/NIE: {autonomo.nif_nie}", normal_style), Paragraph(f"NIF/NIE: {cotizacion.cliente_nif}", normal_style)],
        [Paragraph(f"Actividad: {autonomo.actividad_profesional or 'Servicios'}", normal_style), Paragraph(f"Teléfono: {cotizacion.cliente_telefono}", normal_style)],
        [Paragraph("", normal_style), Paragraph(f"Email: {cotizacion.cliente_email}", normal_style)],
    ]
    
    t_contacto = Table(datos_contacto, colWidths=[260, 260])
    t_contacto.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 4)]))
    story.append(t_contacto)
    story.append(Spacer(1, 25))

    headers = [[Paragraph("<strong>Descripción Elemento</strong>", bold_style), Paragraph("<strong>Cant.</strong>", bold_style), Paragraph("<strong>Precio Unitario</strong>", bold_style), Paragraph("<strong>Total</strong>", bold_style)]]
    
    lineas_tabla = []
    for linea in cotizacion.lineas.all():
        lineas_tabla.append([
            Paragraph(linea.descripcion_elemento, normal_style),
            str(linea.cantidad),
            Paragraph(f"{linea.precio_unitario} €", normal_style),
            Paragraph(f"{linea.coste_total} €", normal_style)
        ])

    t_desglosada = Table(headers + lineas_tabla, colWidths=[240, 50, 110, 120])
    t_desglosada.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT')
    ]))
    story.append(t_desglosada)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph(f"<strong>TOTAL PRESUPUESTO ESTIMADO: {cotizacion.total_base_imponible} €</strong> (Impuestos no incluidos)", normal_style))
    
    doc.build(story)

    if cotizacion.estado == 'BORRADOR':
        cotizacion.estado = 'ENVIADO'
        cotizacion.save()

    return response


@login_required
def disparar_whatsapp_cotizacion(request, cotizacion_id):
    """Abre la API oficial de WhatsApp Web con el texto estructurado del cliente"""
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    
    mensaje = (
        f"Hola {cotizacion.cliente_nombre},\n\n"
        f"Te adjunto el presupuesto para el proyecto: *{cotizacion.titulo_proyecto}*.\n"
        f"Importe estimado: *{cotizacion.total_base_imponible} €*.\n\n"
        f"Puedes revisarlo y confirmar la aceptación respondiendo a este mensaje."
    )
    
    mensaje_url = urllib.parse.quote(mensaje)

@login_required
def convertir_cotizacion_a_factura(request, cotizacion_id):
    """Fase 3: Transforma una cotización aceptada en factura oficial definitiva"""
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    perfil = cotizacion.autonomo

    if cotizacion.estado == 'FACTURADO':
        return redirect('dashboard_fiscal')

    numero_factura_legal = perfil.obtener_siguiente_numero_factura()

    nueva_factura = FacturaEmitida.objects.create(
        autonomo=perfil,
        numero_factura=numero_factura_legal,
        cliente_nombre=cotizacion.cliente_nombre,
        cliente_nif=cotizacion.cliente_nif,
        concepto=cotizacion.titulo_proyecto,
        base_imponible=cotizacion.total_base_imponible,
        porcentaje_iva=Decimal('0.21')
    )

    cotizacion.estado = 'FACTURADO'
    cotizacion.save()

    return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)
