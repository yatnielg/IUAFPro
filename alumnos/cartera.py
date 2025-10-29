# utils/cartera.py
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Q
from alumnos.models import Cargo, PagoDiario

DIN = Decimal('0.01')

def _money(x):
    if x is None:
        return Decimal('0.00')
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(DIN, rounding=ROUND_HALF_UP)

def _q_pagos_del_alumno(alumno):
    q = Q(alumno=alumno)
    if getattr(alumno, 'curp', None):
        q |= Q(curp__iexact=alumno.curp)
    if getattr(alumno, 'numero_estudiante', None):
        q |= Q(numero_alumno=alumno.numero_estudiante)
    return q

def _keywords_concepto(concepto):
    # intenta usar codigo y nombre del concepto
    vals = set()
    if getattr(concepto, 'codigo', None):
        vals.add(str(concepto.codigo))
    if getattr(concepto, 'nombre', None):
        vals.add(str(concepto.nombre))
    # añade sin tildes / variantes básicas
    base = set()
    for v in list(vals):
        vv = v.lower()
        base.add(vv)
        base.add(vv.replace('í','i').replace('ó','o').replace('á','a').replace('é','e').replace('ú','u'))
    return [v for v in base if v]

def _filtro_pagos_por_concepto(concepto):
    kws = _keywords_concepto(concepto)
    q = Q()
    for w in kws:
        q |= Q(concepto__icontains=w) | Q(pago_detalle__icontains=w)
    return q

from decimal import Decimal
from django.db import transaction

def calcular_cargos_con_saldo(alumno, restar_pagos_mas_recientes=True):
    """
    Devuelve una lista por cada Cargo del alumno con:
      cargo_id, concepto, fecha_cargo, monto_original, monto_aplicado, monto_restante,
      is_overdue, is_due_today, dias_mora.

    Además, ACTUALIZA Cargo.pagado en BD:
      - True  si el cargo queda totalmente cubierto (monto_restante == 0.00)
      - False si aún hay saldo pendiente (> 0.00)
    """
    # 1) Trae cargos del alumno (incluye concepto)
    cargos_qs = (
        Cargo.objects
        .select_related('concepto')
        .filter(alumno=alumno)
        .order_by('-fecha_cargo', '-id')
    )
    cargos = list(cargos_qs)
    if not cargos:
        return []

    # Diccionario rápido id->objeto para actualizar luego
    cargos_by_id = {c.id: c for c in cargos}

    # 2) Estructura de trabajo por cargo
    detalle = [{
        'cargo_id': c.id,
        'concepto_codigo': getattr(c.concepto, 'codigo', ''),
        'concepto_nombre': getattr(c.concepto, 'nombre', ''),
        'fecha_cargo': c.fecha_cargo,
        'fecha_vencimiento': c.fecha_vencimiento,
        'monto_original': _money(c.monto),
        'monto_aplicado': Decimal('0.00'),
        'monto_restante': _money(c.monto),
        'is_overdue': False,
        'is_due_today': False,
        'dias_mora': 0,
    } for c in cargos]

    # 3) Agrupa cargos por concepto y calcula flags básicos
    cargos_por_concepto = {}
    hoy = date.today()
    for ci in detalle:
        fv = ci.get('fecha_vencimiento') or ci.get('fecha_cargo')
        if fv and ci['monto_restante'] > 0:
            ci['is_overdue']  = fv < hoy
            ci['is_due_today'] = fv == hoy
            ci['dias_mora']    = (hoy - fv).days if fv < hoy else 0

        key = (ci['concepto_codigo'] or '').upper()
        cargos_por_concepto.setdefault(key, []).append(ci)

    # 4) Aplica pagos por concepto
    for concepto_key, lista_cargos in cargos_por_concepto.items():
        concepto_obj = next(
            (c.concepto for c in cargos if (getattr(c.concepto, 'codigo', '') or '').upper() == concepto_key),
            None
        )

        pagos_qs = (
            PagoDiario.objects
            .filter(_q_pagos_del_alumno(alumno) & _filtro_pagos_por_concepto(concepto_obj))
            .exclude(monto__isnull=True)
            .exclude(monto=0)
        )
        pagos_qs = (pagos_qs.order_by('-fecha', '-creado_en')
                    if restar_pagos_mas_recientes
                    else pagos_qs.order_by('fecha', 'creado_en'))

        pagos = [{'id': p.id, 'monto_restante': _money(p.monto)} for p in pagos_qs]

        # Orden de cargos: por fecha_cargo y luego id (sin invertir, para estabilidad)
        lista_cargos.sort(key=lambda x: (x['fecha_cargo'] or x['cargo_id'], x['cargo_id']))

        for pago in pagos:
            if pago['monto_restante'] <= 0:
                continue
            for ci in lista_cargos:
                if pago['monto_restante'] <= 0:
                    break
                if ci['monto_restante'] <= 0:
                    continue

                aplica = min(ci['monto_restante'], pago['monto_restante'])
                ci['monto_aplicado'] = _money(ci['monto_aplicado'] + aplica)
                ci['monto_restante'] = _money(ci['monto_restante'] - aplica)
                pago['monto_restante'] = _money(pago['monto_restante'] - aplica)

    # 5) Persistir Cargo.pagado según saldo resultante
    to_update = []
    for ci in detalle:
        cargo_obj = cargos_by_id[ci['cargo_id']]
        pagado_nuevo = (ci['monto_restante'] == Decimal('0.00'))
        if cargo_obj.pagado != pagado_nuevo:
            cargo_obj.pagado = pagado_nuevo
            to_update.append(cargo_obj)

    if to_update:
        # Agrupa en una transacción y actualiza en bloque solo el campo pagado
        with transaction.atomic():
            Cargo.objects.bulk_update(to_update, ['pagado'])

    return detalle
