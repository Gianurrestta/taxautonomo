import datetime
from decimal import Decimal
import urllib.parse
import random
import string
import os


# Importaciones nativas de Django
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User

# Importaciones para la generación de PDFs y Gráficos Nativos (ReportLab)
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
# Módulo crítico para dibujar el código QR oficial de VERI*FACTU
from reportlab.graphics.barcode.qr import QrCode
from reportlab.graphics.shapes import Drawing

# Importaciones de tu propia aplicación relacional CRM
from .models import PerfilAutonomo, FacturaEmitida, GastoRecibido, Cotizacion, LineaCotizacion, Cliente

def landing_page(request):
    """Muestra la Landing Page de presentación comercial de la plataforma"""
    if request.user.is_authenticated:
        return redirect('dashboard_fiscal')
    return render(request, 'fiscalidad/index.html')

@login_required
def dashboard_fiscal(request):
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
    try:
        perfil = request.user.perfil
    except PerfilAutonomo.DoesNotExist:
        return render(request, 'fiscalidad/no_perfil.html')

    numero_provisional = perfil.obtener_siguiente_numero_factura()
    mis_clientes = Cliente.objects.filter(autonomo=perfil).order_by('nombre_o_razon_social')

    if request.method == 'POST':
        modo_cliente = request.POST.get('modo_cliente', 'existente')
        titulo = request.POST.get('titulo_proyecto', 'Presupuesto de Servicios')

        if modo_cliente == 'nuevo':
            # Guardamos el nuevo cliente en la base de datos CRM para futuras ocasiones
            cliente_instancia = Cliente.objects.create(
                autonomo=perfil,
                nombre_o_razon_social=request.POST.get('nuevo_nombre', '').strip(),
                nif_nie=request.POST.get('nuevo_nif', '').strip().upper(),
                telefono=request.POST.get('nuevo_telefono', '').strip(),
                email=request.POST.get('nuevo_email', '').strip(),
                domicilio_fiscal=request.POST.get('nuevo_domicilio', '').strip()
            )
        else:
            cliente_id = request.POST.get('cliente_id')
            cliente_instancia = get_object_or_404(Cliente, id=cliente_id, autonomo=perfil)



@login_required
def descargar_factura_pdf(request, factura_id):
    """Generación de PDF profesional conforme al RD 1619/2012 y VERI*FACTU con Código QR Oficial Centrado y Alineado"""
    factura = get_object_or_404(FacturaEmitida, id=factura_id, autonomo__user=request.user)
    autonomo = factura.autonomo

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Factura_{factura.numero_factura}.pdf"'

    # Dejamos bottomMargin=120 para asegurar que el contenido de la factura jamás choque con el QR ni el pie de página
    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=120)
    story = []
    styles = getSampleStyleSheet()

    titulo_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#1a252f'), spaceAfter=15)
    normal_style = styles['Normal']
    bold_style = ParagraphStyle('BoldStyle', parent=normal_style, fontName='Helvetica-Bold')

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

    # FUNCIÓN DE LIENZO AVANZADA: Dibuja de forma fija el Pie de Página y el Código QR de Hacienda
    def agregar_elementos_verifactu(canvas, doc):
        canvas.saveState()
        
        # 1. CONSTRUCCIÓN DEL CÓDIGO QR OFICIAL (Versión Directa e Infalible VERI*FACTU)
        importe_limpio = str(factura.total_factura).replace(" €", "").strip()
        fecha_limpia = str(factura.fecha_emision).strip()
        
        url_sucia = (
            f"https://agenciatributaria.es?"
            f"nif={factura.autonomo.nif_nie}&"
            f"num={factura.numero_factura}&"
            f"fecha={fecha_limpia}&"
            f"importe={importe_limpio}"
        )
        
        # Codificación segura de URL para evitar que las cámaras se confundan
        url_aeat = urllib.parse.quote(url_sucia, safe=':/?&=')
        
        # Generamos el QR fijando sus dimensiones métricas exactas (65x65 píxeles)
        qr_code = QrCode(url_aeat, width=65, height=65)
        
        # SOLUCIÓN INDESTRUCTIBLE: Forzamos al canvas a dibujar el código de barras en su posición exacta
        # Coordenadas en la esquina inferior derecha: X=505, Y=45 del borde de la hoja
        qr_code.drawOn(canvas, 505, 45)


        # 2. DIBUJO DEL PIE DE PÁGINA TRADICIONAL PERFECTAMENTE CENTRADO
        canvas.setStrokeColor(colors.lightgrey)
        canvas.setLineWidth(0.5)
        canvas.line(40, 42, 572, 42) # Línea divisoria gris
        
        centro_hoja = 306 # Eje central de la página letter
        
        # Texto del Hash VERI*FACTU en Negrita Centrado (Posición Y=28)
        texto_hash = f"Huella Digital de Registro (VERI*FACTU ID): {factura.hash_verifactu}"
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawCentredString(centro_hoja, 28, texto_hash)
        
        # Leyenda legal oficial obligatoria Centrada (Posición Y=15)
        texto_legal = "Factura verificable en la sede electrónica de la AEAT o VERI*FACTU"
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor('#7f8c8d'))
        canvas.drawCentredString(centro_hoja, 15, texto_legal)
        
        canvas.restoreState()

    # Compilamos forzando a pintar el pie de página y el QR oficial en cada hoja generada
    doc.build(story, onFirstPage=agregar_elementos_verifactu, onLaterPages=agregar_elementos_verifactu)
    return response


@login_required
def generar_y_enviar_cotizacion_pdf(request, cotizacion_id):
    cotizacion = get_object_or_404(Cotizacion, id=cotizacion_id, autonomo__user=request.user)
    autonomo = cotizacion.autonomo

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Presupuesto_{cotizacion.id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos tipográficos modernos (equivalentes al CSS)
    titulo_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=20, textColor=colors.HexColor('#1e293b'), spaceAfter=4)
    subtitulo_style = ParagraphStyle('SubTitle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#64748b'), spaceAfter=20)
    normal_style = ParagraphStyle('CustomNormal', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor('#334155'))
    bold_style = ParagraphStyle('Bold', parent=normal_style, fontName='Helvetica-Bold', textColor=colors.HexColor('#0f172a'))
    header_table_style = ParagraphStyle('HeaderTable', parent=normal_style, fontName='Helvetica-Bold', textColor=colors.white)

    # 1. Preparar el logotipo o el nombre del autónomo con el mismo tamaño del título
    if autonomo.logo and os.path.exists(autonomo.logo.path):
        elemento_logo = Image(autonomo.logo.path, width=110, height=55, kind='proportional')
    else:
        # Usamos directamente titulo_style para que tenga exactamente el mismo tamaño (20pt) y color
        nombre_cabecera_style = ParagraphStyle('NombreCabecera', parent=titulo_style, alignment=0, spaceAfter=0)
        elemento_logo = Paragraph(f"{autonomo.nombre_fiscal.upper()}", nombre_cabecera_style)


    # 2. Preparar el título y datos del presupuesto alineados a la derecha (columna derecha)
    titulo_derecha_style = ParagraphStyle('TituloDerecha', parent=titulo_style, alignment=2, spaceAfter=2)
    subtitulo_derecha_style = ParagraphStyle('SubtituloDerecha', parent=subtitulo_style, alignment=2, spaceAfter=0)

    bloque_titulo = [
        Paragraph(f"PRESUPUESTO #{cotizacion.id:04d}", titulo_derecha_style),
        Paragraph(f"Proyecto: <strong>{cotizacion.titulo_proyecto}</strong>", subtitulo_derecha_style),
        Paragraph(f"Fecha: {cotizacion.fecha_creacion.strftime('%d/%m/%Y')}", subtitulo_derecha_style),
    ]

    # 3. Unir ambos elementos en una tabla de cabecera de 2 columnas (ancho total = 532pt)
    
    tabla_cabecera = Table([[elemento_logo, bloque_titulo]], colWidths=(200, 332))
    tabla_cabecera.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
    ]))
    story.append(tabla_cabecera)

    # Bloque de Emisor y Cliente en tarjeta con fondo suave
    datos_contacto = [
        [Paragraph("<strong>DATOS DEL EMISOR</strong>", bold_style), Paragraph("<strong>PREPARADO PARA (CLIENTE)</strong>", bold_style)],
        [Paragraph(f"{autonomo.nombre_fiscal}", normal_style), Paragraph(f"{cotizacion.cliente_nombre}", normal_style)],
        [Paragraph(f"NIF/NIE: {autonomo.nif_nie}", normal_style), Paragraph(f"NIF/NIE: {cotizacion.cliente_nif}", normal_style)],
        [Paragraph(f"Actividad: {autonomo.actividad_profesional or 'Servicios Profesionales'}", normal_style), Paragraph(f"Tel: {cotizacion.cliente_telefono or 'No indicado'}", normal_style)],
        [Paragraph(f"Domicilio: {autonomo.domicilio_fiscal or ''}", normal_style), Paragraph(f"Email: {cotizacion.cliente_email or 'No indicado'}", normal_style)],
    ]
    
    t_contacto = Table(datos_contacto, colWidths=(266, 266))
    t_contacto.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, -1), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(t_contacto)
    story.append(Spacer(1, 25))

    # Tabla desglosada de conceptos
    headers = [[
        Paragraph("Descripción del Servicio / Concepto", header_table_style),
        Paragraph("Cant.", header_table_style),
        Paragraph("Precio Unit.", header_table_style),
        Paragraph("Subtotal", header_table_style)
    ]]
    
    lineas_tabla = []
    for linea in cotizacion.lineas.all():
        lineas_tabla.append([
            Paragraph(linea.descripcion_elemento, normal_style),
            f"{linea.width:g}",
            f"{linea.precio_unitario:.2f} €",
            f"{linea.coste_total:.2f} €"
        ])

    t_desglosada = Table(headers + lineas_tabla, colWidths=(282, 60, 95, 95))
    t_desglosada.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t_desglosada)
    story.append(Spacer(1, 20))

    # Recuadro destacado para el Total
    # Cálculo matemático exacto del IVA (21%) y Total Final
    base_imponible = cotizacion.total_base_imponible
    porcentaje_iva = Decimal('0.21')
    cuota_iva = (base_imponible * porcentaje_iva).quantize(Decimal('0.01'))
    total_con_iva = base_imponible + cuota_iva

    # Estilos alineados a la derecha para los importes
    num_normal_style = ParagraphStyle('NumNormal', parent=normal_style, alignment=2)
    num_total_style = ParagraphStyle('NumTotal', parent=bold_style, fontSize=12, alignment=2, textColor=colors.HexColor('#065f46'))

    # Tabla desglosada de Base Imponible + IVA + Total a Pagar
    datos_total = [
        [
            Paragraph("Base Imponible:", normal_style),
            Paragraph(f"{base_imponible:.2f} €", num_normal_style)
        ],
        [
            Paragraph("IVA (21%):", normal_style),
            Paragraph(f"{cuota_iva:.2f} €", num_normal_style)
        ],
        [
            Paragraph("<strong>TOTAL PRESUPUESTO (IVA Incluido):</strong>", ParagraphStyle('LabelTotal', parent=bold_style, fontSize=11, textColor=colors.HexColor('#065f46'))),
            Paragraph(f"<strong>{total_con_iva:.2f} €</strong>", num_total_style)
        ]
    ]

    t_total = Table(datos_total, colWidths=(380, 152))
    t_total.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#ecfdf5')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#10b981')),
        ('LINEABOVE', (0, 2), (-1, 2), 1, colors.HexColor('#10b981')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(t_total)
    story.append(Spacer(1, 8))
    story.append(Paragraph("<font size='8' color='#64748b'>* Precios expresados en Euros (€). Validez de la oferta: 15 días naturales.</font>", normal_style))
    
    doc.build(story)
    return response

def login_usuario(request):
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
            error = "Usuario o contraseña incorrectos."
    return render(request, 'fiscalidad/login.html', {'error': error})

def registro_autonomo(request):
    """Automatiza el registro completo generando los códigos aleatorios obligatorios de identidad"""
    if request.user.is_authenticated:
        return redirect('dashboard_fiscal')
        
    error = None
    if request.method == 'POST':
        u = request.POST.get('username')
        em = request.POST.get('email')
        p = request.POST.get('password')
        nf = request.POST.get('nombre_fiscal')
        nif = request.POST.get('nif_nie')
        df = request.POST.get('domicilio_fiscal')
        tel = request.POST.get('telefono_registro') # <--- SINCRO: Nombre exacto del input HTML
        
        if User.objects.filter(username=u).exists():
            error = "El nombre de usuario ya está registrado."
        elif PerfilAutonomo.objects.filter(nif_nie=nif).exists():
            error = "Este NIF/NIE ya está registrado."
        else:
            nuevo_user = User.objects.create_user(username=u, email=em, password=p)
            
            # MATEMÁTICA PURA DE SEGURIDAD: Generamos dos códigos secretos de 6 dígitos independientes
            cod_email = f"{random.randint(100000, 999999)}"
            cod_sms = f"{random.randint(100000, 999999)}"
            
            perfil = PerfilAutonomo.objects.create(
                user=nuevo_user,
                nif_nie=nif,
                nombre_fiscal=nf,
                domicilio_fiscal=df,
                telefono=tel, # <--- SINCRO: Guarda la variable tel en la columna de la base de datos
                cuenta_verificada=False,
                codigo_verificacion_email=cod_email,
                codigo_verificacion_sms=cod_sms
            )
            
            # SIMULACIÓN TÉCNICA: Despachamos las alertas directamente hacia tu terminal de comandos
            print("\n" + "="*60)
            print(f" SIMULADOR DE PASARELA DE SEGURIDAD DE DOBLE FACTOR")
            print(f" Enviando SMS al número: {tel} -> CÓDIGO SECRETO: [{cod_sms}]")
            print(f" Enviando Email al correo: {em} -> CÓDIGO SECRETO: [{cod_email}]")
            print("="*60 + "\n")
            
            login(request, nuevo_user)
            return redirect('verificar_cuenta_view')
            
    return render(request, 'fiscalidad/registro.html', {'error': error})

def logout_usuario(request):
    logout(request)
    return redirect('login_usuario')

@login_required
def verificar_cuenta_view(request):
    """Módulo de Identidad: Valida los códigos de 6 dígitos obligatorios para desbloquear la plataforma"""
    perfil = request.user.perfil
    
    # Si la cuenta ya está verificada por seguridad, lo mandamos directo al panel
    if perfil.cuenta_verificada:
        return redirect('dashboard_fiscal')
        
    error = None
    if request.method == 'POST':
        c_email = request.POST.get('codigo_email', '').strip()
        c_sms = request.POST.get('codigo_sms', '').strip()
        
        # Validación exacta céntimo a céntimo de las variables de identidad
        if perfil.codigo_verificacion_email == c_email and perfil.codigo_verificacion_sms == c_sms:
            perfil.cuenta_verificada = True
            # Limpiamos los códigos de la base de datos por seguridad de un solo uso
            perfil.codigo_verificacion_email = None
            perfil.codigo_verificacion_sms = None
            perfil.save()
            return redirect('dashboard_fiscal')
        else:
            error = "Los códigos introducidos no coinciden con los enviados. Inténtalo de nuevo."

    context = {
        'error': error,
        'correo_destino': request.user.email,
        'telefono_destino': perfil.telefono or 'No registrado'
    }
    return render(request, 'fiscalidad/verificar_cuenta.html', context)

    # ==============================================================================
    # PROCESO DE TRAMITACIÓN DE ALTA DE AUTÓNOMOS (manual)
    # ==============================================================================

from django.shortcuts import render, redirect
from django.contrib import messages
from .models import SolicitudAlta

# Reemplaza la función asistente_alta_autonomo por esta versión corregida en fiscalidad/views.py

def asistente_alta_autonomo(request):
    """
    Asistente de alta express paso a paso.
    Estructura robusta ante peticiones GET y POST para evitar retornos None.
    """
    if request.user.is_authenticated:
        solicitud, created = SolicitudAlta.objects.get_or_create(
            usuario=request.user,
            defaults={'estado': 'BORRADOR', 'paso_actual': 1}
        )
        paso = solicitud.paso_actual
    else:
        paso = request.session.get('alta_paso_actual', 1)

    if request.method == 'POST':
        accion = request.POST.get('accion')
        
        # --- LÓGICA DE NAVEGACIÓN HACIA ATRÁS ---
        if accion == 'retroceder' and paso > 1:
            if request.user.is_authenticated:
                solicitud.paso_actual -= 1
                solicitud.save()
            else:
                request.session['alta_paso_actual'] = paso - 1
            return redirect('asistente_alta')
            
        # --- PROCESAMIENTO DEL PASO 1 ---
        if paso == 1:
            nif_nie = request.POST.get('nif_nie', '').strip().upper()
            nombre = request.POST.get('nombre', '').strip().upper()
            apellidos = request.POST.get('apellidos', '').strip().upper()
            fecha_nacimiento = request.POST.get('fecha_nacimiento', '')
            telefono = request.POST.get('telefono', '').strip()

            if not nif_nie or not nombre or not apellidos or not telefono:
                messages.error(request, "Por favor, rellena todos los campos obligatorios (*).")
                return redirect('asistente_alta')

            if not request.user.is_authenticated:
                request.session['alta_nif_nie'] = nif_nie
                request.session['alta_nombre'] = nombre
                request.session['alta_apellidos'] = apellidos
                request.session['alta_fecha_nacimiento'] = fecha_nacimiento
                request.session['alta_telefono'] = telefono
                request.session['alta_paso_actual'] = 2
            else:
                solicitud.nif_nie = nif_nie
                solicitud.nombre = nombre
                solicitud.apellidos = apellidos
                solicitud.telefono = telefono
                if fecha_nacimiento:
                    solicitud.fecha_nacimiento = fecha_nacimiento
                solicitud.paso_actual = 2
                solicitud.save()

            messages.success(request, "Datos personales guardados correctamente.")
            return redirect('asistente_alta')

        # --- PROCESAMIENTO DEL PASO 2 ---
        elif paso == 2:
            direccion = request.POST.get('direccion_fiscal', '').strip()
            cp = request.POST.get('codigo_postal', '').strip()
            localidad = request.POST.get('localidad', '').strip()
            provincia = request.POST.get('provincia', '').strip()

            if not direccion or not cp or not localidad or not provincia:
                messages.error(request, "Por favor, completa todos los campos de tu dirección.")
                return redirect('asistente_alta')

            if not request.user.is_authenticated:
                request.session['alta_direccion_fiscal'] = direccion
                request.session['alta_codigo_postal'] = cp
                request.session['alta_localidad'] = localidad
                request.session['alta_provincia'] = provincia
                request.session['alta_paso_actual'] = 3
            else:
                solicitud.direccion_fiscal = direccion
                solicitud.codigo_postal = cp
                solicitud.localidad = localidad
                solicitud.provincia = provincia
                solicitud.paso_actual = 3
                solicitud.save()

            messages.success(request, "Domicilio fiscal guardado correctamente.")
            return redirect('asistente_alta')

        # --- PROCESAMIENTO DEL PASO 3 ---
        elif paso == 3:
            iae_codigo = request.POST.get('iae_codigo', '').strip()
            descripcion_actividad = request.POST.get('descripcion_actividad', '').strip()
            fecha_inicio = request.POST.get('fecha_inicio', '')

            if not iae_codigo or not descripcion_actividad or not fecha_inicio:
                messages.error(request, "Por favor, rellena todos los campos obligatorios sobre tu actividad.")
                return redirect('asistente_alta')

            cnae_calculado = deducir_cnae_desde_iae(iae_codigo)

            if not request.user.is_authenticated:
                request.session['alta_iae_codigo'] = iae_codigo
                request.session['alta_cnae_codigo'] = cnae_calculado
                request.session['alta_descripcion_actividad'] = descripcion_actividad
                request.session['alta_fecha_inicio'] = fecha_inicio
                request.session['alta_paso_actual'] = 4
            else:
                solicitud.iae_codigo = iae_codigo
                solicitud.cnae_codigo = cnae_calculado
                solicitud.descripcion_actividad = descripcion_actividad
                solicitud.fecha_inicio = fecha_inicio
                solicitud.paso_actual = 4
                solicitud.save()

            messages.success(request, "Actividad económica registrada con éxito.")
            return redirect('asistente_alta')
        
        # --- PASO 4: SEGURIDAD SOCIAL Y COBERTURAS (AÑADIR ESTE BLOQUE) ---
        elif paso == 4:
            mutua = request.POST.get('mutua', '').strip()
            aplica_tarifa_plana = 'aplica_tarifa_plana' in request.POST

            if not mutua:
                messages.error(request, "Por favor, debes seleccionar una Mutua Colaboradora para tus coberturas.")
                return redirect('asistente_alta')

            # Guardamos las decisiones de protección social en la sesión o base de datos
            if not request.user.is_authenticated:
                request.session['alta_mutua'] = mutua
                request.session['alta_aplica_tarifa_plana'] = aplica_tarifa_plana
                request.session['alta_paso_actual'] = 5
            else:
                solicitud.mutua = mutua
                solicitud.aplica_tarifa_plana = aplica_tarifa_plana
                solicitud.paso_actual = 5
                solicitud.save()

            messages.success(request, "Configuración de Seguridad Social guardada correctamente.")
            return redirect('asistente_alta')

               # --- PASO 5: DOMICILIACIÓN Y ALTA INSTANTÁNEA (VERSIÓN CORREGIDA) ---
        elif paso == 5:
            iban_cuenta = request.POST.get('iban_cuenta', '').replace(" ", "").upper()

            if not iban_cuenta or len(iban_cuenta) < 20:
                messages.error(request, "Por favor, introduce un número de cuenta IBAN válido para domiciliar tus cuotas.")
                return redirect('asistente_alta')

            # 1. Extraemos los datos temporales de la sesión ANTES de que login() la reinicie
            username_alta = request.session.get('alta_nif_nie')
            email_alta = f"{username_alta.lower()}@plataforma.com"
            
            import string
            import random
            caracteres = string.ascii_letters + string.digits
            password_aleatoria = ''.join(random.choice(caracteres) for i in range(12))

            # 2. Creamos el usuario en Django
            username_alta = request.session.get('alta_nif_nie')
            email_alta = f"{username_alta.lower()}@plataforma.com"
            
            nuevo_usuario, created_user = User.objects.get_or_create(
                username=username_alta,
                defaults={
                    'email': email_alta,
                }
            )
            
            # Si el usuario es nuevo, le asignamos su contraseña aleatoria segura
            if created_user:
                import string
                import random
                caracteres = string.ascii_letters + string.digits
                password_aleatoria = ''.join(random.choice(caracteres) for i in range(12))
                nuevo_usuario.set_password(password_aleatoria)
                nuevo_usuario.save()

            # 3. Consolidamos o actualizamos el registro de SolicitudAlta en la Base de Datos
            solicitud_oficial, created_solicitud = SolicitudAlta.objects.get_or_create(
                usuario=nuevo_usuario,
                defaults={
                    'paso_actual': 5,
                    'estado': 'COMPLETADO',
                    'nif_nie': username_alta,
                    'nombre': request.session.get('alta_nombre'),
                    'apellidos': request.session.get('alta_apellidos'),
                    'telefono': request.session.get('alta_telefono'),
                    'direccion_fiscal': request.session.get('alta_direccion_fiscal'),
                    'codigo_postal': request.session.get('alta_codigo_postal'),
                    'localidad': request.session.get('alta_localidad'),
                    'provincia': request.session.get('alta_provincia'),
                    'iae_codigo': request.session.get('alta_iae_codigo'),
                    'cnae_codigo': request.session.get('alta_cnae_codigo'),
                    'descripcion_actividad': request.session.get('alta_descripcion_actividad'),
                    'mutua': request.session.get('alta_mutua'),
                    'aplica_tarifa_plana': request.session.get('alta_aplica_tarifa_plana', True),
                    'iban_cuenta': iban_cuenta
                }
            )
            
            # Si la solicitud ya existía, simplemente actualizamos sus datos finales
            if not created_solicitud:
                solicitud_oficial.estado = 'COMPLETADO'
                solicitud_oficial.iban_cuenta = iban_cuenta
                solicitud_oficial.save()

            # 4. Iniciar sesión de forma segura en el navegador
            login(request, nuevo_usuario)

            # 5. Limpiamos las variables temporales de la sesión
            claves_sesion = ['alta_nif_nie', 'alta_nombre', 'alta_apellidos', 'alta_telefono', 
                             'alta_direccion_fiscal', 'alta_codigo_postal', 'alta_localidad', 
                             'alta_provincia', 'alta_iae_codigo', 'alta_cnae_codigo', 
                             'alta_descripcion_actividad', 'alta_mutua', 'alta_aplica_tarifa_plana', 
                             'alta_paso_actual', 'alta_iban_cuenta']
            for clave in claves_sesion:
                if clave in request.session:
                    del request.session[clave]

            messages.success(request, f"¡Enhorabuena, {solicitud_oficial.nombre}! Tu alta telemática ha sido procesada con éxito.")
            
            # Forzamos el renderizado directo de tu archivo independiente para evitar conflictos de rutas base
            return render(request, 'fiscalidad/dashboard.html', {'solicitud': solicitud_oficial})


    # --- FLUJO GET: RECOMPOSICIÓN DE CONTEXTO SEGURO Y LIMPIO ---
    if request.user.is_authenticated:
        datos_formulario = {
            'telefono': solicitud.telefono,
            'nif_nie': solicitud.nif_nie,
            'nombre': solicitud.nombre,
            'apellidos': solicitud.apellidos,
            'fecha_nacimiento': str(solicitud.fecha_nacimiento) if solicitud.fecha_nacimiento else '',
            'direccion_fiscal': solicitud.direccion_fiscal,
            'codigo_postal': solicitud.codigo_postal,
            'localidad': solicitud.localidad,
            'provincia': solicitud.provincia,
            'iae_codigo': solicitud.iae_codigo,
            'descripcion_actividad': solicitud.descripcion_actividad,
            'fecha_inicio': str(solicitud.fecha_inicio) if solicitud.fecha_inicio else '',
            'mutua': solicitud.mutua,
            'aplica_tarifa_plana': solicitud.aplica_tarifa_plana,
            'iban_cuenta': request.session.get('alta_iban_cuenta', ''),
        }
    else:
        datos_formulario = {
            'telefono': request.session.get('alta_telefono', ''),
            'nif_nie': request.session.get('alta_nif_nie', ''),
            'nombre': request.session.get('alta_nombre', ''),
            'apellidos': request.session.get('alta_apellidos', ''),
            'fecha_nacimiento': request.session.get('alta_fecha_nacimiento', ''),
            'direccion_fiscal': request.session.get('alta_direccion_fiscal', ''),
            'codigo_postal': request.session.get('alta_codigo_postal', ''),
            'localidad': request.session.get('alta_localidad', ''),
            'provincia': request.session.get('alta_provincia', ''),
            'iae_codigo': request.session.get('alta_iae_codigo', ''),
            'descripcion_actividad': request.session.get('alta_descripcion_actividad', ''),
            'fecha_inicio': request.session.get('alta_fecha_inicio', ''),
            'mutua': request.session.get('alta_mutua', ''),
            'aplica_tarifa_plana': request.session.get('alta_aplica_tarifa_plana', True),
        }

    context = {
        'paso': paso,
        'solicitud': datos_formulario,
        'mutuas': SolicitudAlta.MUTUAS_CHOICES
    }
    # Obligatorio: Garantizamos que en cualquier petición GET se retorne una respuesta válida
    return render(request, f'fiscalidad/alta_paso_{paso}.html', context)

def simular_extraccion_ocr_api(ruta_archivo):
    """
    Simulación del servicio API de lectura e identidad segura (Signaturit/Ivnosys).
    Devuelve los datos estructurados del DNI de forma instantánea.
    """
    # En producción, aquí harías un requests.post() enviando el archivo DNI binario
    return {
        "status": "success",
        "documento_identidad": "12345678Z",
        "nombre": "Juan",
        "apellidos": "García Pérez",
        "fecha_nacimiento": "1990-05-15",
    }

# Añade este bloque al final de fiscalidad/views.py

def deducir_cnae_desde_iae(sector_codigo):
    """
    Asigna un código CNAE base de la Seguridad Social según el sector 
    de actividad seleccionado por el usuario en el paso 3.
    """
    mapeo_universal = {
        # Empresariales
        'EMP_GAN': '0141',   # Ganadería
        'EMP_IND': '2011',   # Industria química
        'EMP_MET': '2511',   # Fabricación estructuras metálicas
        'EMP_FAB': '1392',   # Fabricación textiles
        'EMP_CON': '4120',   # Construcción de edificios
        'EMP_COM_M': '4619',  # Intermediarios del comercio
        'EMP_COM_D': '4711',  # Comercio al por menor / Tiendas
        'EMP_HOS': '5610',   # Restaurantes y puestos de comida
        'EMP_TRA': '4941',   # Transporte de mercancías por carretera
        'EMP_TEL': '6110',   # Telecomunicaciones de cable
        'EMP_FIN': '6419',   # Otra intermediación financiera
        'EMP_SER': '9602',   # Peluquería y otros tratamientos de belleza
        
        # Profesionales
        'PROF_AGR': '0161',  # Actividades de apoyo a la agricultura
        'PROF_TEC': '7111',  # Servicios de arquitectura
        'PROF_COM': '4611',  # Intermediarios comercio materias primas
        'PROF_SAN': '8621',  # Actividades de medicina general
        'PROF_LEG': '6910',  # Actividades jurídicas
        'PROF_ECO': '6920',  # Actividades de contabilidad, teneduría y auditoría
        'PROF_EDU': '8559',  # Otra educación n.c.o.p.
        'PROF_REC': '6201',  # Actividades de programación informática / Diseño
        
        # Artísticas
        'ART_ESPECT': '9001', # Artes escénicas
        'ART_DEPOR': '9319',  # Otras actividades deportivas
        'ART_TAUR': '9004',   # Gestión de salas de espectáculos
    }
    return mapeo_universal.get(sector_codigo, '9609')

@login_required
def configurar_perfil_logo(request):
    """
    Vista segura para que el autónomo suba el logo de su empresa.
    El logo queda almacenado permanentemente en el servidor y en la base de datos.
    """
    # CORREGIDO: Cambiamos 'usuario' por 'user' tal como exige tu modelo original
    perfil = get_object_or_404(PerfilAutonomo, user=request.user)

    if request.method == 'POST':
        logo_subido = request.FILES.get('logo_empresa')

        if logo_subido:
            perfil.logo = logo_subido
            perfil.save() # Django almacena físicamente el archivo en media/logos_autonomos/
            messages.success(request, "¡Logo de empresa guardado y sincronizado correctamente en tu perfil!")
            return redirect('dashboard_fiscal') # Asegúrate de que 'dashboard_fiscal' es el name correcto de tu vista
        else:
            messages.error(request, "Por favor, selecciona un archivo de imagen válido.")

    return render(request, 'fiscalidad/configurar_logo.html', {'perfil': perfil})

@login_required
def crear_cotizacion(request):
    """Permite crear un presupuesto detallado con cliente existente o nuevo"""
    perfil = get_object_or_404(PerfilAutonomo, user=request.user)
    mis_clientes = Cliente.objects.filter(autonomo=perfil).order_by('nombre_o_razon_social')

    if request.method == 'POST':
        modo_cliente = request.POST.get('modo_cliente', 'existente')
        nuevo_nombre = request.POST.get('nuevo_nombre', '').strip()
        cliente_id = request.POST.get('cliente_id', '').strip()
        titulo = request.POST.get('titulo_proyecto', 'Presupuesto de Servicios')

        # 1. Determinar o crear el cliente de forma segura
        if modo_cliente == 'nuevo' or nuevo_nombre:
            cliente_instancia = Cliente.objects.create(
                autonomo=perfil,
                nombre_o_razon_social=nuevo_nombre,
                nif_nie=request.POST.get('nuevo_nif', '').strip().upper(),
                telefono=request.POST.get('nuevo_telefono', '').strip(),
                email=request.POST.get('nuevo_email', '').strip(),
                domicilio_fiscal=request.POST.get('nuevo_domicilio', '').strip()
            )
        elif cliente_id.isdigit():
            # Solo buscamos en la base de datos si cliente_id es realmente un número
            cliente_instancia = get_object_or_404(Cliente, id=int(cliente_id), autonomo=perfil)
        else:
            # Si no eligió cliente ni llenó uno nuevo, regresamos con aviso claro
            return render(request, 'fiscalidad/crear_cotizacion.html', {
                'mis_clientes': mis_clientes,
                'error': 'Debes seleccionar un cliente de la lista o rellenar los datos del cliente nuevo.'
            })

        # 2. Crear la cabecera del presupuesto (sin pasar total_base_imponible)
        nueva_cotizacion = Cotizacion.objects.create(
            autonomo=perfil,
            cliente=cliente_instancia,
            titulo_proyecto=titulo,
            cliente_nombre=cliente_instancia.nombre_o_razon_social,
            cliente_nif=cliente_instancia.nif_nie,
            cliente_telefono=getattr(cliente_instancia, 'telefono', ''),
            cliente_email=getattr(cliente_instancia, 'email', '')
        )

                # 3. Procesar las líneas del presupuesto
        descripciones = request.POST.getlist('descripcion[]')
        cantidades = request.POST.getlist('cantidad[]')
        precios = request.POST.getlist('precio[]')

        for desc, cant, prec in zip(descripciones, cantidades, precios):
            if desc.strip() and cant and prec:
                LineaCotizacion.objects.create(
                    cotizacion=nueva_cotizacion,
                    descripcion_elemento=desc.strip(),
                    width=Decimal(cant),
                    precio_unitario=Decimal(prec)
                )

        return redirect('dashboard_fiscal')


    return render(request, 'fiscalidad/crear_cotizacion.html', {'mis_clientes': mis_clientes})


