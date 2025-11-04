# utils/servicios.py
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Q, Sum
from alumnos.models import Cargo, PagoDiario, Alumno

DINERO = Decimal('0.01')

# Palabras clave por concepto para detectar pagos relacionados desde PagoDiario
CONCEPTO_KEYWORDS = {
    # puedes ajustar/expandir
    'COLEGIATURA': ['colegiatura', 'mensualidad', 'tuition', 'pago mensual'],
    'INSCRIPCION': ['inscripción', 'inscripcion', 'matrícula', 'matricula'],
    'REINSCRIPCION': ['reinscripción', 'reinscripcion'],
    'TITULACION': ['titulación', 'titulacion'],
    'EQV': ['equivalencia'],
}

def _money(x) -> Decimal:
    if x is None:
        return Decimal('0.00')
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(DINERO, rounding=ROUND_HALF_UP)

def _q_pagos_por_concepto(concepto_codigo: str) -> Q:
    """
    Construye un Q para filtrar PagoDiario por concepto/pago_detalle con palabras clave del concepto.
    Si no hay keywords para el código, cae a un match por 'concepto__icontains'.
    """
    code = (concepto_codigo or '').upper().strip()
    kws = CONCEPTO_KEYWORDS.get(code, None)

    q = Q()
    if kws:
        sub = Q()
        for w in kws:
            sub |= Q(concepto__icontains=w) | Q(pago_detalle__icontains=w)
        q &= sub
    else:
        # Fallback: intenta por el código en texto
        q &= (Q(concepto__icontains=code) | Q(pago_detalle__icontains=code))

    return q

def _q_pagos_del_alumno(alumno: Alumno) -> Q:
    """
    Considera pagos enlazados por FK alumno y, como respaldo, por CURP o número de alumno si existen.
    """
    q = Q(alumno=alumno)
    if getattr(alumno, 'curp', None):
        q |= Q(curp__iexact=alumno.curp)
    if getattr(alumno, 'numero_estudiante', None):
        q |= Q(numero_alumno=alumno.numero_estudiante)
    return q

def _ordenar_pagos_recientes(pagos_qs):
    # más recientes primero, y luego por creado_en si la fecha empata
    return pagos_qs.order_by('-fecha', '-creado_en')

def _ordenar_cargos_para_descuento(cargos_qs, restar_mas_recientes=True):
    """
    Si restar_mas_recientes=True => aplicamos pagos empezando por cargos más nuevos.
    """
    return cargos_qs.order_by('-fecha_cargo' if restar_mas_recientes else 'fecha_cargo', 'id')

def calcular_saldos_por_concepto(alumno: Alumno, concepto_codigo: str, restar_mas_recientes: bool = True):
    """
    Retorna un dict con el detalle de cargos (monto original, aplicado, restante) para el concepto.
    NO escribe nada en DB; solo calcula en memoria.
    - Aplica pagos de PagoDiario que coincidan con el concepto (por keywords), en orden más reciente -> más antiguo.
    - Permite pagos parciales.
    """
    # 1) Cargos del concepto (aunque estén marcados como pagados, se recalcula “virtualmente”)
    cargos_qs = Cargo.objects.select_related('concepto').filter(
        alumno=alumno, concepto__codigo__iexact=concepto_codigo
    )
    cargos = list(_ordenar_cargos_para_descuento(cargos_qs, restar_mas_recientes))

    # 2) Pagos que matchean concepto y pertenecen al alumno (FK o curp/numero_alumno)
    pagos_qs = PagoDiario.objects.filter(
        _q_pagos_del_alumno(alumno) & _q_pagos_por_concepto(concepto_codigo)
    ).exclude(monto__isnull=True).exclude(monto=0)

    pagos = list(_ordenar_pagos_recientes(pagos_qs))

    # 3) Inicializa estructuras
    cargos_info = []
    for c in cargos:
        cargos_info.append({
            'cargo_id': c.id,
            'fecha_cargo': c.fecha_cargo,
            'concepto': getattr(c.concepto, 'codigo', str(c.concepto_id)),
            'monto_original': _money(c.monto),
            'monto_aplicado': Decimal('0.00'),
            'monto_restante': _money(c.monto),
        })

    # 4) Aplica pagos (más recientes primero) contra cargos según orden solicitado
    pagos_restantes = []
    for p in pagos:
        saldo_pago = _money(p.monto)
        if saldo_pago <= 0:
            continue

        # Intenta cubrir cargos en orden
        for ci in cargos_info:
            if saldo_pago <= 0:
                break
            if ci['monto_restante'] <= 0:
                continue

            aplica = min(ci['monto_restante'], saldo_pago)
            ci['monto_aplicado'] = _money(ci['monto_aplicado'] + aplica)
            ci['monto_restante'] = _money(ci['monto_restante'] - aplica)
            saldo_pago = _money(saldo_pago - aplica)

        # si sobró del pago tras cubrir todos los cargos de este concepto
        if saldo_pago > 0:
            pagos_restantes.append({
                'pago_id': p.id,
                'fecha': p.fecha,
                'folio': p.folio,
                'concepto_txt': p.concepto,
                'pago_detalle': p.pago_detalle,
                'monto_sobrante': saldo_pago,
            })

    # 5) Totales
    total_cargos = _money(sum(ci['monto_original'] for ci in cargos_info))
    total_aplicado = _money(sum(ci['monto_aplicado'] for ci in cargos_info))
    total_restante = _money(sum(ci['monto_restante'] for ci in cargos_info))

    # 6) Devuelve solo cargos con saldo pendiente si quieres “mostrar solo lo que falta”
    cargos_pendientes = [ci for ci in cargos_info if ci['monto_restante'] > 0]

    return {
        'alumno_id': alumno.id,
        'concepto': concepto_codigo.upper(),
        'totales': {
            'cargos': total_cargos,
            'aplicado': total_aplicado,
            'pendiente': total_restante,
        },
        'cargos_pendientes': cargos_pendientes,   # cada uno con parcial si aplica
        'pagos_sobrantes': pagos_restantes,       # por si se pagó de más en ese concepto
    }
