# -*- coding: utf-8 -*-
from django.core.management.base import BaseCommand
from academico.models import Profesor


# Lista “quemada” de profesores tomada del Excel
PROFESORES_BASE = [
    {
        "nombre_completo": "Larissa Estefania Esparza Fuentes",
        "grado": "Doctora",
        "email_institucional": "larissaa@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Gualterio Diaz Jarquín",
        "grado": "Doctor",
        "email_institucional": "gualterio@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Marisela Dolores Cifuentes López",
        "grado": "Doctora",
        "email_institucional": "marisela.cifuentes@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Martha Zaragoza González",
        "grado": "Maestra",
        "email_institucional": "dra.martha.zaragoza@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Gilberto Santa Rosa",
        "grado": "Doctor",
        "email_institucional": "gilberto.santa@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Isaac Muñoz Alatorre",
        "grado": "Doctor",
        "email_institucional": "isaact@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Jorge Luis Lujano Uribe",
        "grado": "M. en D",
        "email_institucional": "jorge.lujano@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Silvia Patricia Rasgado López",
        "grado": "Doctora",
        "email_institucional": "silviarasgado22@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Oralia Contreras Guzmán",
        "grado": "Doctora",
        "email_institucional": "oralia.contreras@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Francisco Rojo Núñez",
        "grado": "Doctor",
        "email_institucional": "franciscorojo22@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Iris del Roció Cureño Hernández",
        "grado": "Doctora",
        "email_institucional": "iris.chdz@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Maria Guadalupe Bernal Luna",
        "grado": "Maestra",
        "email_institucional": "guadalupe.bernal1@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Luis Fernando Sánchez Hernández",
        "grado": "Maestro",
        "email_institucional": "LuisSanchez@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Mario Rafael Acosta Villanueva",
        "grado": "Maestro",
        "email_institucional": "mario.acosta@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Anaid Campos Galindo",
        "grado": "Doctora",
        "email_institucional": "anaid.campos@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Adrián Polanco Polanco",
        "grado": "Doctor",
        "email_institucional": "adrian.polanco@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Ana María Ramírez Sánchez",
        "grado": "Doctora",
        "email_institucional": "ana.ramirez@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Héctor Rivera NavaA",
        "grado": "Doctor",
        "email_institucional": "hectorrnava@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Martina Arroyo Diaz",
        "grado": "Doctora",
        "email_institucional": "arroyom@iuaf.edu.mx",
    },
    {
        "nombre_completo": "María José Ríos Hurtado",
        "grado": "Doctora",
        "email_institucional": "marijoser@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Erika Muñoz Salazar",
        "grado": "Doctora",
        "email_institucional": "rectoria@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Homero Rodríguez Figueroa",
        "grado": "Doctor",
        "email_institucional": "homero.rod@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Alberto Fabián Mondragón Pedrero",
        "grado": "Doctor",
        "email_institucional": "fabian.mondragon@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Ana Selene Medina Cevallos",
        "grado": "Doctora",
        "email_institucional": "anamedina@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Vinicius Covas Alves",
        "grado": "Doctor",
        "email_institucional": "vinicius.covas@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Yasmín Rubí Campos Cohuo",
        "grado": "Doctora",
        "email_institucional": "dgeneral@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Maria Esther Zavala Ramirez",
        "grado": "Doctora",
        "email_institucional": "dramirezesther@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Maria Luisa Ocampo Rodriguez",
        "grado": "Doctora",
        "email_institucional": "mluisao@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Graciela Jiménez Islas",
        "grado": "Doctora",
        "email_institucional": "grajimenez@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Luz María Lemus Campuzano",
        "grado": "Doctora",
        "email_institucional": "luzlemus@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Guadalupe Jimenez Topete",
        "grado": "Doctora",
        "email_institucional": "gjimenez@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Nery Sofía Huerta Pacheco",
        "grado": "Doctora",
        "email_institucional": "sofiah@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Sergio Leonel de la Cruz Santizo",
        "grado": "Maestro",
        "email_institucional": "sergio.santizo@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Nancy Roberta Martinez Barrios",
        "grado": "Doctora",
        "email_institucional": "martinez.nancy.dd2cb@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Hector Eduardo Velez Yañez",
        "grado": "Maestro",
        "email_institucional": "eduardovelez@iuaf.edu.mx",
    },
    {
        "nombre_completo": "Aliuska Jimenez González",
        "grado": "Doctora",
        "email_institucional": "aliuska.jimenez@iuaf.edu.mx",
    },
]


def partir_nombre_completo(nombre_completo: str):
    """
    Parte un nombre completo en:
    - nombre
    - apellido paterno
    - apellido materno

    Lógica simple:
    - 1 palabra: todo en nombre
    - 2 palabras: nombre, apellido_p
    - 3 palabras: nombre, apellido_p, apellido_m
    - 4+ palabras: todo menos las 2 últimas = nombre;
                   penúltima = apellido_p; última = apellido_m
    """
    if not nombre_completo:
        return "", "", ""

    partes = [p.strip() for p in str(nombre_completo).split() if p.strip()]
    if len(partes) == 0:
        return "", "", ""
    if len(partes) == 1:
        return partes[0], "", ""
    if len(partes) == 2:
        return partes[0], partes[1], ""
    if len(partes) == 3:
        return partes[0], partes[1], partes[2]

    nombre = " ".join(partes[:-2])
    apellido_p = partes[-2]
    apellido_m = partes[-1]
    return nombre, apellido_p, apellido_m


class Command(BaseCommand):
    help = "Crea/actualiza el listado base de profesores IUAF en el modelo Profesor."

    def handle(self, *args, **options):
        creados = 0
        actualizados = 0

        for data in PROFESORES_BASE:
            nombre_completo = data["nombre_completo"]
            grado = data.get("grado", "").strip()
            email_inst = data.get("email_institucional", "").strip()

            nombre, apellido_p, apellido_m = partir_nombre_completo(nombre_completo)

            if email_inst:
                profesor, created = Profesor.objects.update_or_create(
                    email_institucional=email_inst,
                    defaults={
                        "nombre": nombre,
                        "apellido_p": apellido_p,
                        "apellido_m": apellido_m,
                        "grado_academico": grado,
                        "activo": True,
                    },
                )
            else:
                profesor, created = Profesor.objects.update_or_create(
                    nombre=nombre,
                    apellido_p=apellido_p,
                    apellido_m=apellido_m,
                    defaults={
                        "grado_academico": grado,
                        "activo": True,
                    },
                )

            if created:
                creados += 1
                self.stdout.write(self.style.SUCCESS(f"Creado: {profesor}"))
            else:
                actualizados += 1
                self.stdout.write(self.style.WARNING(f"Actualizado: {profesor}"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Profesores creados: {creados}"))
        self.stdout.write(self.style.SUCCESS(f"Profesores actualizados: {actualizados}"))
