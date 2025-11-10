# academico/services.py
from decimal import Decimal, ROUND_HALF_UP

def calcular_promedio_final(inscripcion):
    criterios = (inscripcion.oferta.criterios
                 .filter(activo=True)
                 .order_by("orden"))
    califs = {c.criterio_id: c.valor or Decimal("0.0")
              for c in inscripcion.calificaciones.select_related("criterio")}
    total = Decimal("0.00")
    for crit in criterios:
        valor = Decimal(str(califs.get(crit.id, 0)))
        pondera = Decimal(str(crit.ponderacion or 0)) / Decimal("100")
        total += (valor * pondera)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


APROBATORIA = Decimal("70.00")  # ajusta a tu escala

def resultado_por_promedio(promedio):
    if promedio is None:
        return "NP"
    return "APROBADO" if Decimal(str(promedio)) >= APROBATORIA else "REPROBADO"
