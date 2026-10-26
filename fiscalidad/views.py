import datetime
from decimal import Decimal
import urllib.parse

# Importaciones nativas de Django
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

# Importaciones para la generación de PDFs (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Importaciones de tu propia aplicación relacional CRM
from .models import PerfilAutonomo, FacturaEmitida, GastoRecibido, Cotizacion, Cliente


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
    
    # Extraemos todos los presupuestos de este autónomo para el seguimiento CRM
    cotizaciones_usuario = Cotizacion.objects.filter(autonomo=perfil).order_by('-fecha_creacion')

    context = {
        'datos_fiscales': datos_fiscales,
        'gastos_mes': gastos_mes,
        'facturas_mes': facturas_mes,
        'cotizaciones_usuario': cotizaciones_usuario,
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
    mis_clientes = Cliente.objects.filter(autonomo=perfil).order_by('nombre_o_razon_social')

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente_id')
        concepto = request.POST.get('concepto', 'Servicios profesionales')
        base = request.POST.get('base_imponible', '0.00')
        iva = request.POST.get('porcentaje_iva', '0.21')
        fecha_op = request.POST.get('fecha_operacion')
        
        cliente_instancia = get_object_or_404(Cliente, id=cliente_id, autonomo=perfil)
        numero_definitivo = perfil.obtener_siguiente_numero_factura()
        
        nueva_factura = FacturaEmitida.objects.create(
            autonomo=perfil,
            cliente=cliente_instancia,
            numero_factura=numero_definitivo,
            concepto=concepto,
            base_imponible=Decimal(base),
            porcentaje_iva=Decimal(iva),
            fecha_operacion=datetime.datetime.strptime(fecha_op, '%Y-%m-%d').date() if fecha_op else datetime.date.today()
        )
        return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)

    context = {
        'siguiente_numero': numero_provisional,
        'mis_clientes': mis_clientes
    }
    return render(request, 'fiscalidad/emitir_factura.html', context)


@login_required
def descargar_factura_pdf(request, factura_id):
    """Generación de PDF profesional conforme al RD 1619/2012 y VERI*FACTU"""
    factura = get_object_or_404(FacturaEmitida, id=factura_id, autonomo__user=request.user)
    autonomo = factura.autonomo

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Factura_{factura.numero_factura}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#1a252f'), spaceAfter=15)
    normal_style = styles['Normal']
    bold_style = ParagraphStyle('BoldStyle', parent=normal_style, fontName='Helvetica-Bold')
    aviso_legal_style = ParagraphStyle('Legal', parent=normal_style, fontSize=9, textColor=colors.HexColor('#7f8c8d'), alignment=1, spaceBefore=25)

    story.append(Paragraph(f"FACTURA OFICIAL: {factura.numero_factura}", titulo_style))
    story.append(Paragraph(f"Fecha de Emisión: <strong>{factura.fecha_emision}</strong> | Fecha de Operación: <strong>{factura.fecha_operacion}</strong>", normal_style))
    story.append(Spacer(1, 20))

    datos_completos = [
        [Paragraph("<strong>EMISOR (Autónomo):</strong>", normal_style), Paragraph("<strong>RECEPTOR (Cliente):</strong>", normal_style)],
        [Paragraph(f"{autonomo.nombre_fiscal}", normal_style), Paragraph(f"{factura.cliente_nombre}", normal_style)],
        [Paragraph(f"NIF/NIE: {autonomo.nif_nie}", normal_style), Paragraph(f"NIF/NIE: {factura.cliente_nif}", normal_style)],
        [Paragraph(f"Domicilio: {autonomo.domicilio_fiscal or 'No asignado'}", normal_style), Paragraph(f"Domicilio: {factura.cliente_domicilio}", normal_style)],
    ]
    
    table_datos = Table(datos_completos, colWidths=[260, 260])
    table_datos.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 5)]))
    story.append(table_datos)
    story.append(Spacer(1, 30))

    headers_tabla = [
        [Paragraph("<strong>Concepto / Descripción detallada</strong>", bold_style), 
         Paragraph("<strong>Base Imponible</strong>", bold_style), 
         Paragraph("<strong>IVA %</strong>", bold_style), 
         Paragraph("<strong>Cuota IVA</strong>", bold_style), 
         Paragraph("<strong>Importe Total</strong>", bold_style)]
    ]
    
    cuerpo_tabla = [
        [Paragraph(factura.concepto, normal_style), 
         f"{factura.base_imponible} €", 
         f"{factura.porcentaje_iva * 100:.0f}%", 
         f"{factura.total_iva} €", 
         f"{factura.total_factura} €"]
    ]
    
    tabla_factura = Table(headers_tabla + cuerpo_tabla, colWidths=[220, 75, 55, 80, 90])
    tabla_factura.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(tabla_factura)

    story.append(Spacer(1, 40))
    story.append(Paragraph(f"Huella Digital de Registro (VERI*FACTU ID): <font fontName='Courier' size='7'>{factura.hash_verifactu}</font>", normal_style))
    story.append(Paragraph("<strong>Factura verificable en la sede electrónica de la AEAT o VERI*FACTU</strong>", aviso_legal_style))

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

    t_desglosada = Table(headers + lineas_tabla, colWidths=[260, 60, 100, 100])
    t_desglosada.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.lightgrey),
        ('PADDING', (0,0), (-1,-1), 6),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT')
    ]))
    story.append(t_desglosada)
    story.append(Spacer(1, 15))
    story.append(Paragraph(f"TOTAL PRESUPUESTO ESTIMADO: {cotizacion.total_base_imponible} € (Impuestos no incluidos)", normal_style))
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
    f"Te adjunto el presupuesto para el proyecto: {cotizacion.titulo_proyecto}.\n"
    f"Importe estimado: {cotizacion.total_base_imponible} €.\n\n"
    f"Puedes revisarlo y confirmar la aceptación respondiendo a este mensaje."
    )
    mensaje_url = urllib.parse.quote(mensaje)
    whatsapp_url = f"whatsapp.com{cotizacion.cliente_telefono}&text={mensaje_url}"
    return redirect(whatsapp_url)
    @login_required
    def convertir_cotizacion_a_factura(request, cotizacion_id):
        """Fase 3: Transforma una cotización aceptada en factura oficial definitiva unificada"""
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    perfil = cotizacion.autonomo
    if cotizacion.estado == 'FACTURADO':
        return redirect('dashboard_fiscal')
    numero_factura_legal = perfil.obtener_siguiente_numero_factura()
    # Creación relacional limpia de la Factura Oficial
    nueva_factura = FacturaEmitida.objects.create(
    autonomo=perfil,
    cliente=cotizacion.cliente,
    numero_factura=numero_factura_legal,
    concepto=cotizacion.titulo_proyecto,
    base_imponible=cotizacion.total_base_imponible,
    porcentaje_iva=Decimal('0.21'),
    fecha_operacion=datetime.date.today()
    )
    cotizacion.estado = 'FACTURADO'
    cotizacion.save()
    return redirect('descargar_factura_pdf', factura_id=nueva_factura.id)

def login_usuario(request):
    """Procesa el acceso seguro controlando las credenciales"""
    if request.user.is_authenticated:
        return redirect('dashboard_fiscal')
        
    error = None
    if request.method == 'POST':
        u = request.POST.get('username')
        p = request.POST.get('password')
        
        user = authenticate(request, username=u, password=p)
        if user is not None:
            login(request, user)
            return redirect('dashboard_fiscal')
        else:
            error = "Usuario o contraseña incorrectos. Por favor, verifica de nuevo."
            
    return render(request, 'fiscalidad/login.html', {'error': error})


def registro_autonomo(request):
    """Automatiza el registro completo creando el User y su Perfil Fiscal obligatorio"""
    if request.user.is_authenticated:
        return redirect('dashboard_fiscal')
        
    error = None
    if request.method == 'POST':
        u = request.POST.get('username')
        em = request.POST.get('email')
        p = request.POST.get('password')
        
        # Datos fiscales
        nf = request.POST.get('nombre_fiscal')
        nif = request.POST.get('nif_nie')
        df = request.POST.get('domicilio_fiscal')
        
        # Validamos de forma preventiva que el usuario o el NIF no estén repetidos
        if User.objects.filter(username=u).exists():
            error = "El nombre de usuario ya está registrado en el sistema."
        elif PerfilAutonomo.objects.filter(nif_nie=nif).exists():
            error = "Este NIF/NIE ya se encuentra registrado con otra cuenta."
        else:
            # 1. Creamos el usuario base cifrando la contraseña
            nuevo_user = User.objects.create_user(username=u, email=em, password=p)
            
            # 2. Creamos de golpe su perfil fiscal inyectando sus datos obligatorios
            PerfilAutonomo.objects.create(
                user=nuevo_user,
                nif_nie=nif,
                nombre_fiscal=nf,
                domicilio_fiscal=df
            )
            
            # 3. Lo logueamos de forma directa para máxima comodidad
            login(request, nuevo_user)
            return redirect('dashboard_fiscal')
            
    return render(request, 'fiscalidad/registro.html', {'error': error})


def logout_usuario(request):
    """Cierra la sesión destruyendo de forma segura los identificadores"""
    logout(request)
    return redirect('login_usuario')