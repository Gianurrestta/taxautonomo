import re

def validar_documento_espanol(documento: str) -> tuple[bool, str]:
    """
    Valida matemáticamente un DNI/NIF, NIE o CIF español según la normativa oficial.
    Devuelve (True, 'OK') si es válido, o (False, 'Mensaje de error') si es falso o incorrecto.
    """
    if not documento:
        return False, "El NIF/NIE es obligatorio."

    doc = documento.strip().upper().replace("-", "").replace(" ", "")
    tabla_letras = "TRWAGMYFPDXBNJZSQVHLCKE"

    # 1. Validación de DNI / NIF estándar (8 números + 1 letra)
    if re.match(r"^\d{8}[A-Z]$", doc):
        numero = int(doc[:8])
        letra_calculada = tabla_letras[numero % 23]
        if doc[8] == letra_calculada:
            return True, "NIF válido"
        return False, f"El NIF {doc} no es válido. La letra de control no corresponde con los números."

    # 2. Validación de NIE (X, Y o Z + 7 números + 1 letra)
    if re.match(r"^[XYZ]\d{7}[A-Z]$", doc):
        reemplazo = {'X': '0', 'Y': '1', 'Z': '2'}
        numero_str = reemplazo[doc[0]] + doc[1:8]
        numero = int(numero_str)
        letra_calculada = tabla_letras[numero % 23]
        if doc[8] == letra_calculada:
            return True, "NIE válido"
        return False, f"El NIE {doc} no es válido. La letra de control es incorrecta."

    # 3. Validación de CIF de empresas/sociedades (Letra + 7 números + dígito/letra de control)
    if re.match(r"^[ABCDEFGHJKLMNPQRSUVW]\d{7}[0-9A-J]$", doc):
        letras_control_cif = "JABCDEFGHI"
        suma_pares = sum(int(doc[i]) for i in range(2, 7, 2))
        suma_impares = 0
        for i in range(1, 8, 2):
            doble = int(doc[i]) * 2
            suma_impares += (doble // 10) + (doble % 10)

        total = suma_pares + suma_impares
        digito_control = (10 - (total % 10)) % 10
        letra_control = letras_control_cif[digito_control]

        control_esperado = doc[8]
        # Algunas sociedades exigen letra (K, P, Q, S), otras número (A, B, E, H)
        if doc[0] in "KPQS":
            es_valido = (control_esperado == letra_control)
        elif doc[0] in "ABEH":
            es_valido = (control_esperado == str(digito_control))
        else:
            es_valido = (control_esperado in (str(digito_control), letra_control))

        if es_valido:
            return True, "CIF válido"
        return False, f"El CIF {doc} no es válido. El dígito de control es incorrecto."

    return False, "Formato no reconocido. Introduce un NIF (8 números y letra) o NIE (X/Y/Z, 7 números y letra) real."
