def analizar_situacion_alta(descripcion_actividad: str, ya_fue_autonomo: str, hace_mas_dos_anos: str, trabaja_cuenta_ajena: str, trabaja_desde_casa: str) -> dict:
    """
    Motor inteligente que deduce el Epígrafe IAE, impuestos aplicables
    y detecta conflictos legales antes de tramitar el alta ante la AEAT y Seguridad Social.
    """
    texto = descripcion_actividad.lower()
    alertas = []
    recomendaciones = []

    # 1. Detección inteligente de Epígrafe IAE por palabras clave
    if any(p in texto for p in ['programador', 'software', 'web', 'informatica', 'desarrollo', 'app', 'datos']):
        epigrafe = '763'
        nombre_epigrafe = '763 - Programadores y Analistas de Informática'
        tipo_actividad = 'PROFESIONAL'
        iva_defecto = '21%'
        irpf_defecto = '7% (primeros 3 años) / 15% general'
    elif any(p in texto for p in ['marketing', 'publicidad', 'redes', 'seo', 'diseño', 'fotografia', 'video']):
        epigrafe = '844'
        nombre_epigrafe = '844 - Publicidad, Relaciones Públicas y Diseño'
        tipo_actividad = 'PROFESIONAL'
        iva_defecto = '21%'
        irpf_defecto = '7% (primeros 3 años) / 15% general'
    elif any(p in texto for p in ['clase', 'profesor', 'formacion', 'academia', 'ingles', 'tutor', 'curso']):
        epigrafe = '821'
        nombre_epigrafe = '821 - Enseñanza y Formación'
        tipo_actividad = 'PROFESIONAL'
        iva_defecto = '0% (Exento si es materia reglada)'
        irpf_defecto = '7% (primeros 3 años) / 15% general'
    elif any(p in texto for p in ['fisio', 'psicologo', 'medico', 'nutricionista', 'salud', 'dentista']):
        epigrafe = '836'
        nombre_epigrafe = '836 - Profesionales Sanitarios'
        tipo_actividad = 'PROFESIONAL'
        iva_defecto = '0% (Exento por servicios sanitarios)'
        irpf_defecto = '7% (primeros 3 años) / 15% general'
    elif any(p in texto for p in ['reforma', 'fontanero', 'electricista', 'aire', 'pintor', 'obra', 'instalacion']):
        epigrafe = '504'
        nombre_epigrafe = '504 - Instalaciones y Reformas'
        tipo_actividad = 'EMPRESARIAL'
        iva_defecto = '21% (o 10% en reformas de vivienda particular)'
        irpf_defecto = '0% (Actividad empresarial, sin retención en factura)'
    elif any(p in texto for p in ['tienda', 'venta', 'comercio', 'ecommerce', 'ropa', 'producto']):
        epigrafe = '659'
        nombre_epigrafe = '659 - Comercio al por Menor'
        tipo_actividad = 'EMPRESARIAL'
        iva_defecto = '21% (Recargo de equivalencia aplicable)'
        irpf_defecto = '0% (Actividad empresarial, sin retención en factura)'
    else:
        epigrafe = '751'
        nombre_epigrafe = '751 - Consultoría y Servicios Técnicos Generales'
        tipo_actividad = 'PROFESIONAL'
        iva_defecto = '21%'
        irpf_defecto = '7% / 15%'

    # 2. Detección de conflictos de historial censal y Tarifa Plana
    if ya_fue_autonomo == 'si_activo':
        alertas.append("CONFLICTO CRÍTICO: Si ya tienes un alta activa en Hacienda/RETA, no debes tramitar un alta nueva, sino una 'Modificación Censal (Modelo 036/037)' para añadir este nuevo epígrafe sin duplicar cuotas.")
    elif ya_fue_autonomo == 'si_baja':
        if hace_mas_dos_anos == 'no':
            alertas.append("AVISO DE BONIFICACIÓN: Al haber estado de baja hace menos de 2 años, Hacienda y la Seguridad Social NO te aplicarán la Tarifa Plana de 80 €/mes. Cotizarás según tu tramo de ingresos reales desde el primer día.")
        else:
            recomendaciones.append("Cumples el plazo legal tras tu baja anterior: puedes solicitar la Tarifa Plana de 80 €/mes.")
    else:
        recomendaciones.append("Como nuevo autónomo, tienes derecho a solicitar la Tarifa Plana reducida en la Seguridad Social.")

    # 3. Detección de Pluriactividad
    if trabaja_cuenta_ajena == 'si':
        alertas.append("PLURIACTIVIDAD DETECTADA: Al tener contrato por cuenta ajena, debes elegir entre la Tarifa Plana o la bonificación por pluriactividad (ambas son incompatibles por ley).")

    # 4. Configuración de vivienda afecta
    if trabaja_desde_casa == 'si':
        recomendaciones.append("Declararemos un 30% de tu vivienda habitual afecta a la actividad en el Modelo 036/037 para que puedas deducir legalmente parte de tus facturas de luz, agua e internet.")

    return {
        'epigrafe': epigrafe,
        'nombre_epigrafe': nombre_epigrafe,
        'tipo_actividad': tipo_actividad,
        'iva_defecto': iva_defecto,
        'irpf_defecto': irpf_defecto,
        'alertas': alertas,
        'recomendaciones': recomendaciones,
    }
