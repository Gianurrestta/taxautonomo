import re
from decimal import Decimal
import datetime
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
import pdfplumber

# Ruta estándar de Tesseract en Windows (si usas Linux/Mac en producción, comenta esta línea)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def procesar_justificante_gasto(archivo_subido, nif_autonomo_receptor: str) -> dict:
    """
    Lee una imagen (JPG/PNG) o un PDF electrónico, extrae los datos fiscales clave
    y determina si es Factura Completa (con NIF del receptor) o Ticket simplificado.
    """
    nombre_archivo = archivo_subido.name.lower()
    texto_extraido = ""

    try:
        # 1. EXTRACCIÓN DE TEXTO SEGÚN FORMATO (PDF vs IMAGEN)
        if nombre_archivo.endswith('.pdf'):
            with pdfplumber.open(archivo_subido) as pdf:
                for pagina in pdf.pages:
                    texto_extraido += (pagina.extract_text() or "") + "\n"
        else:
            # Pre-procesamiento óptico para mejorar fotos de tickets arrugados o con poca luz
            imagen = Image.open(archivo_subido)
            imagen = ImageOps.exif_transpose(imagen)  # Corrige rotación del móvil
            imagen = imagen.convert('L')              # Escala de grises
            imagen = ImageEnhance.Contrast(imagen).enhance(2.0)  # Duplica contraste
            texto_extraido = pytesseract.image_to_string(imagen, lang='spa+eng')
    except Exception as e:
        print(f"Error leyendo documento OCR: {e}")

    # Regresamos el puntero del archivo al inicio para que Django lo guarde íntegro en la BD
    archivo_subido.seek(0)

    texto_limpio = texto_extraido.upper()

    # 2. DETECTAR SI ES FACTURA COMPLETA O TICKET
    # Si el NIF del autónomo aparece en el documento, es Factura Completa (deduce IVA)
    nif_receptor_limpio = (nif_autonomo_receptor or "").strip().upper().replace("-", "")
    es_factura_completa = bool(nif_receptor_limpio and nif_receptor_limpio in texto_limpio.replace("-", ""))
    tipo_documento = 'FACTURA' if es_factura_completa else 'TICKET'

    # 3. EXTRAER EL NIF/CIF DEL PROVEEDOR (excluyendo el del propio autónomo)
    nifs_encontrados = re.findall(r'\b[ABCDEFGHJKLMNPQRSUVWXYZ0-9]\d{7}[0-9A-JTRWAGMYFPDXBNJZSQVHLCKE]\b', texto_limpio.replace("-", ""))
    proveedor_nif = ""
    for n in nifs_encontrados:
        if n != nif_receptor_limpio:
            proveedor_nif = n
            break

    # 4. EXTRAER FECHA DEL DOCUMENTO (DD/MM/YYYY o DD-MM-YYYY)
    fecha_detectada = datetime.date.today()
    match_fecha = re.search(r'\b(\d{2})[/\-](\d{2})[/\-](20\d{2})\b', texto_limpio)
    if match_fecha:
        try:
            dia, mes, anio = map(int, match_fecha.groups())
            fecha_detectada = datetime.date(anio, mes, dia)
        except ValueError:
            pass

    # 5. EXTRAER IMPORTES (Total y Base Imponible)
    # Buscamos todos los números con 2 decimales (ej. 121,00 o 121.00)
    importes_str = re.findall(r'\b\d+[.,]\d{2}\b', texto_limpio)
    importes = []
    for imp in importes_str:
        try:
            importes.append(Decimal(imp.replace(',', '.')))
        except Exception:
            pass

    total_detectado = max(importes) if importes else Decimal('0.00')
    
    # Calculamos la base imponible estimada al 21% si no se desglosa explícitamente
    if total_detectado > 0:
        base_estimada = (total_detectado / Decimal('1.21')).quantize(Decimal('0.01'))
    else:
        base_estimada = Decimal('0.00')

    # 6. DEDUCCIÓN AUTOMÁTICA DE CATEGORÍA POR PALABRAS CLAVE
    if any(p in texto_limpio for p in ['IBERDROLA', 'ENDESA', 'NATURGY', 'VODAFONE', 'MOVISTAR', 'ORANGE', 'DIGI', 'AGUA', 'ELECTRICIDAD', 'INTERNET']):
        categoria = 'SUMINISTROS'
    elif any(p in texto_limpio for p in ['REPSOL', 'CEPSA', 'BP', 'GASOLINERA', 'CARBURANTE', 'DIESEL', 'GASOLINA', 'PEAJE']):
        categoria = 'VEHICULO'
    elif any(p in texto_limpio for p in ['RESTAURANTE', 'CAFETERIA', 'BAR ', 'MENU DEL DIA', 'COMIDA']):
        categoria = 'DIETAS'
    else:
        categoria = 'GENERAL'

    # Extraer primera línea legible como nombre sugerido del proveedor
    lineas_validas = [l.strip() for l in texto_extraido.splitlines() if len(l.strip()) > 3]
    proveedor_nombre = lineas_validas[:100] if lineas_validas else "Proveedor Detectado"

    return {
        'proveedor_nombre': proveedor_nombre,
        'proveedor_nif': proveedor_nif,
        'fecha_gasto': fecha_detectada.strftime('%Y-%m-%d'),
        'tipo_documento': tipo_documento,
        'categoria': categoria,
        'base_imponible': f"{base_estimada:.2f}",
        'total_gasto': f"{total_detectado:.2f}",
        'texto_crudo': texto_extraido[:500]  # Útil para depuración si se necesita
    }
