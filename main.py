from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from datetime import datetime
import os
import csv
import io

app = Flask(__name__)

ACCOUNT_SID = os.environ.get("ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
SANDBOX_NUMBER = "whatsapp:+14155238886"

client = Client(ACCOUNT_SID, AUTH_TOKEN)

# ─── BASE DE DATOS EN MEMORIA ───
facturas = []
rancheros = {}
usuarios_conocidos = set()
transferencias_pendientes = {}
registro_en_proceso = {}

# ─── PASOS DEL REGISTRO ───
PASOS_REGISTRO = [
    ("nombre",    "Nombre completo del proveedor:"),
    ("empresa",   "Nombre de la empresa o rancho:"),
    ("rfc",       "RFC de la empresa:"),
    ("telefono",  "Numero de WhatsApp (formato +521XXXXXXXXXX):"),
    ("banco",     "Banco (BBVA, Banorte, HSBC, Banamex, Santander, etc.):"),
    ("clabe",     "CLABE interbancaria (18 digitos):"),
    ("tipo",      "Tipo de proveedor (Ganado, Insumos, Transporte, Veterinaria, Servicios):"),
]

# ─── BASE DE DATOS INICIAL (15 proveedores) ───
PROVEEDORES_INICIALES = [
    {"nombre": "Juan Ramirez",    "empresa": "Rancho El Nogal",       "rfc": "RAJM800101XXX", "telefono": "+526141123456", "banco": "BBVA",      "clabe": "012180001234567890", "tipo": "Ganado"},
    {"nombre": "Pedro Gutierrez", "empresa": "Ganaderia Los Pinos",   "rfc": "GUPE750515XXX", "telefono": "+526141234567", "banco": "Banorte",   "clabe": "072180002345678901", "tipo": "Ganado"},
    {"nombre": "Carlos Mendoza",  "empresa": "Rancho San Jose",       "rfc": "MECC820320XXX", "telefono": "+526141345678", "banco": "HSBC",      "clabe": "021180003456789012", "tipo": "Ganado"},
    {"nombre": "Maria Flores",    "empresa": "Proveedora del Norte",  "rfc": "FOCM900210XXX", "telefono": "+526141456789", "banco": "Santander", "clabe": "014180004567890123", "tipo": "Insumos"},
    {"nombre": "Roberto Soto",    "empresa": "Rancho Las Palmas",     "rfc": "SORR771105XXX", "telefono": "+526141567890", "banco": "BBVA",      "clabe": "012180005678901234", "tipo": "Ganado"},
    {"nombre": "Ana Torres",      "empresa": "Transportes Torres",    "rfc": "TOAA850630XXX", "telefono": "+526141678901", "banco": "Banamex",   "clabe": "002180006789012345", "tipo": "Transporte"},
    {"nombre": "Luis Herrera",    "empresa": "Rancho El Mezquite",    "rfc": "HELL791225XXX", "telefono": "+526141789012", "banco": "Banorte",   "clabe": "072180007890123456", "tipo": "Ganado"},
    {"nombre": "Patricia Vega",   "empresa": "Veterinaria del Valle", "rfc": "VEPP881010XXX", "telefono": "+526141890123", "banco": "BBVA",      "clabe": "012180008901234567", "tipo": "Veterinaria"},
    {"nombre": "Miguel Castro",   "empresa": "Rancho La Esperanza",   "rfc": "CAMM830415XXX", "telefono": "+526141901234", "banco": "HSBC",      "clabe": "021180009012345678", "tipo": "Ganado"},
    {"nombre": "Sofia Ruiz",      "empresa": "Alimentos Ruiz",        "rfc": "RUSS920808XXX", "telefono": "+526141012345", "banco": "Santander", "clabe": "014180000123456789", "tipo": "Insumos"},
    {"nombre": "Fernando Lopez",  "empresa": "Rancho Los Alamos",     "rfc": "LOFF760918XXX", "telefono": "+526142123456", "banco": "Banamex",   "clabe": "002180001234567891", "tipo": "Ganado"},
    {"nombre": "Carmen Diaz",     "empresa": "Servicios Agro Diaz",   "rfc": "DICC870212XXX", "telefono": "+526142234567", "banco": "BBVA",      "clabe": "012180002345678902", "tipo": "Servicios"},
    {"nombre": "Jorge Morales",   "empresa": "Rancho El Potrero",     "rfc": "MOJJ810730XXX", "telefono": "+526142345678", "banco": "Banorte",   "clabe": "072180003456789013", "tipo": "Ganado"},
    {"nombre": "Laura Jimenez",   "empresa": "Forrajes Jimenez",      "rfc": "JILL940325XXX", "telefono": "+526142456789", "banco": "HSBC",      "clabe": "021180004567890124", "tipo": "Insumos"},
    {"nombre": "Ricardo Vargas",  "empresa": "Rancho Santa Fe",       "rfc": "VARR780512XXX", "telefono": "+526142567890", "banco": "Banamex",   "clabe": "002180005678901235", "tipo": "Ganado"},
]

def cargar_proveedores_iniciales():
    for p in PROVEEDORES_INICIALES:
        clave = p["nombre"].split()[0].lower()
        rancheros[clave] = {
            "nombre_completo": p["nombre"],
            "empresa": p["empresa"],
            "rfc": p["rfc"],
            "numero": "whatsapp:" + p["telefono"],
            "banco": p["banco"],
            "clabe": p["clabe"],
            "tipo": p["tipo"],
        }

cargar_proveedores_iniciales()

# ─── HELPERS ───

def hora_actual():
    return datetime.now().strftime("%H:%M")

def fecha_actual():
    return datetime.now().strftime("%d/%m/%Y")

def menu_principal():
    return (
        "Asistente Grupo Mesteno\n"
        "─────────────────────\n\n"
        "PROVEEDORES:\n"
        "  ver proveedores\n"
        "  info [nombre]\n"
        "  agregar proveedor\n"
        "  eliminar [nombre]\n\n"
        "FACTURAS:\n"
        "  pide factura a [nombre]\n"
        "  pide facturas a todos\n"
        "  facturas del dia\n"
        "  historial [nombre]\n"
        "  limpiar\n\n"
        "TRANSFERENCIAS:\n"
        "  transferencia [nombre] [monto]\n\n"
        "REPORTES:\n"
        "  resumen\n\n"
        "  ayuda - ver este menu"
    )

def historial_proveedor(nombre):
    facturas_p = [f for f in facturas if nombre.lower() in f["de"].lower()]
    if not facturas_p:
        return "No hay facturas de " + nombre.capitalize() + " hoy."
    resultado = "HISTORIAL DE " + nombre.upper() + " - " + fecha_actual() + ":\n\n"
    for f in facturas_p:
        tipo = " [ARCHIVO]" if f.get("tiene_archivo") else ""
        resultado += f["hora"] + tipo + ":\n" + f["contenido"] + "\n\n"
    return resultado.strip()

def resumen_diario():
    total = len([f for f in facturas if f.get("tipo") != "transferencia"])
    transferencias = len([f for f in facturas if f.get("tipo") == "transferencia"])
    enviaron = set(f["de"] for f in facturas if f["de"] not in ["Desconocido", "COORDINADORA"])
    pendientes = set(rancheros.keys()) - set(r.lower() for r in enviaron)
    r = "RESUMEN DEL DIA - " + fecha_actual() + "\n"
    r += "─────────────────────\n"
    r += "Facturas recibidas: " + str(total) + "\n"
    r += "Transferencias registradas: " + str(transferencias) + "\n"
    r += "Proveedores que enviaron: " + str(len(enviaron)) + "/" + str(len(rancheros)) + "\n\n"
    if enviaron:
        r += "ENVIARON:\n"
        for p in sorted(enviaron):
            r += "  + " + p.capitalize() + "\n"
    if pendientes:
        r += "\nPENDIENTES:\n"
        for p in sorted(pendientes):
            r += "  - " + p.capitalize() + "\n"
    return r

def info_proveedor(nombre):
    clave = buscar_proveedor(nombre)
    if not clave:
        return "No encontre a " + nombre + ". Usa: ver proveedores"
    d = rancheros[clave]
    return (
        "DATOS DE " + d.get("nombre_completo", clave.capitalize()) + ":\n"
        "─────────────────────\n"
        "Empresa: " + d["empresa"] + "\n"
        "RFC: " + d["rfc"] + "\n"
        "WhatsApp: " + d["numero"].replace("whatsapp:", "") + "\n"
        "Banco: " + d["banco"] + "\n"
        "CLABE: " + d["clabe"] + "\n"
        "Tipo: " + d["tipo"]
    )

def buscar_proveedor(nombre):
    clave = nombre.lower()
    if clave in rancheros:
        return clave
    for k, v in rancheros.items():
        if nombre.lower() in v.get("nombre_completo", "").lower() or nombre.lower() in k:
            return k
    return None

# ─── WEBHOOK ───

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje = request.form.get("Body", "").strip()
    remitente = request.form.get("From", "")
    num_media = int(request.form.get("NumMedia", 0))
    media_url = request.form.get("MediaUrl0", "")
    resp = MessagingResponse()
    msg = resp.message()
    mensaje_lower = mensaje.lower().strip()

    # ─── MENU AUTOMATICO AL PRIMER MENSAJE ───
    if remitente not in usuarios_conocidos:
        usuarios_conocidos.add(remitente)
        msg.body(
            "Bienvenida al asistente de Grupo Mesteno\n"
            "Base de datos cargada con " + str(len(rancheros)) + " proveedores.\n\n" +
            menu_principal()
        )
        return Response(str(resp), mimetype="text/xml")

    # ─── REGISTRO EN PROCESO ───
    if remitente in registro_en_proceso:
        estado = registro_en_proceso[remitente]
        paso_actual = estado["paso"]
        if mensaje_lower in ["cancelar", "cancel"]:
            del registro_en_proceso[remitente]
            msg.body("Registro cancelado.")
            return Response(str(resp), mimetype="text/xml")
        campo, _ = PASOS_REGISTRO[paso_actual]
        estado["datos"][campo] = mensaje
        siguiente_paso = paso_actual + 1
        if siguiente_paso < len(PASOS_REGISTRO):
            estado["paso"] = siguiente_paso
            _, pregunta = PASOS_REGISTRO[siguiente_paso]
            msg.body(pregunta + "\n\n(Escribe cancelar para salir)")
        else:
            datos = estado["datos"]
            clave = datos["nombre"].split()[0].lower()
            rancheros[clave] = {
                "nombre_completo": datos["nombre"],
                "empresa": datos["empresa"],
                "rfc": datos["rfc"],
                "numero": "whatsapp:" + datos["telefono"],
                "banco": datos["banco"],
                "clabe": datos["clabe"],
                "tipo": datos["tipo"],
            }
            del registro_en_proceso[remitente]
            msg.body(
                "Proveedor registrado exitosamente:\n"
                "─────────────────────\n"
                "Nombre: " + datos["nombre"] + "\n"
                "Empresa: " + datos["empresa"] + "\n"
                "RFC: " + datos["rfc"] + "\n"
                "WhatsApp: " + datos["telefono"] + "\n"
                "Banco: " + datos["banco"] + "\n"
                "CLABE: " + datos["clabe"] + "\n"
                "Tipo: " + datos["tipo"] + "\n\n"
                "Ya puedes usar: pide factura a " + datos["nombre"].split()[0]
            )
        return Response(str(resp), mimetype="text/xml")

    # ─── CONFIRMACION DE TRANSFERENCIA ───
    if remitente in transferencias_pendientes:
        pendiente = transferencias_pendientes[remitente]
        if mensaje_lower in ["si", "confirmar"]:
            del transferencias_pendientes[remitente]
            facturas.append({
                "de": "COORDINADORA", "empresa": "Grupo Mesteno", "numero": remitente,
                "contenido": "TRANSFERENCIA a " + pendiente["destinatario"] + " | Monto: $" + pendiente["monto"] + " | CLABE: " + pendiente["clabe"],
                "hora": hora_actual(), "tiene_archivo": False, "media_url": "", "tipo": "transferencia"
            })
            msg.body("Transferencia registrada:\n─────────────────────\nDestinatario: " + pendiente["destinatario"] + "\nEmpresa: " + pendiente["empresa"] + "\nMonto: $" + pendiente["monto"] + "\nCLABE: " + pendiente["clabe"] + "\nBanco: " + pendiente["banco"] + "\nHora: " + hora_actual())
        elif mensaje_lower in ["no", "cancelar"]:
            del transferencias_pendientes[remitente]
            msg.body("Transferencia cancelada.")
        else:
            msg.body("Tienes una transferencia pendiente:\nDestinatario: " + pendiente["destinatario"] + "\nMonto: $" + pendiente["monto"] + "\n\nResponde SI para confirmar o NO para cancelar.")
        return Response(str(resp), mimetype="text/xml")

    # ─── COMANDOS ───

    if mensaje_lower in ["ayuda", "menu", "inicio", "hola"]:
        msg.body(menu_principal())

    elif mensaje_lower == "ver proveedores":
        if rancheros:
            lista = "PROVEEDORES REGISTRADOS (" + str(len(rancheros)) + "):\n\n"
            for i, (clave, datos) in enumerate(rancheros.items(), 1):
                nombre = datos.get("nombre_completo", clave.capitalize())
                lista += str(i) + ". " + nombre + " - " + datos["empresa"] + " (" + datos["tipo"] + ")\n"
            msg.body(lista)
        else:
            msg.body("No hay proveedores registrados.")

    elif mensaje_lower.startswith("info "):
        nombre = mensaje.split(" ", 1)[1]
        msg.body(info_proveedor(nombre))

    elif mensaje_lower == "agregar proveedor":
        registro_en_proceso[remitente] = {"paso": 0, "datos": {}}
        _, primera_pregunta = PASOS_REGISTRO[0]
        msg.body("Registro de nuevo proveedor\n─────────────────────\nVoy a pedirte los datos uno por uno.\nEscribe cancelar en cualquier momento para salir.\n\n" + primera_pregunta)

    elif mensaje_lower.startswith("eliminar "):
        nombre = mensaje.split(" ", 1)[1]
        clave = buscar_proveedor(nombre)
        if clave:
            nombre_completo = rancheros[clave].get("nombre_completo", clave.capitalize())
            del rancheros[clave]
            msg.body("Proveedor " + nombre_completo + " eliminado del sistema.")
        else:
            msg.body("No encontre a " + nombre + ". Usa: ver proveedores")

    elif mensaje_lower.startswith("pide factura a "):
        nombre = mensaje.split("pide factura a ", 1)[1].strip()
        clave = buscar_proveedor(nombre)
        if clave:
            datos = rancheros[clave]
            nombre_completo = datos.get("nombre_completo", clave.capitalize())
            client.messages.create(from_=SANDBOX_NUMBER, to=datos["numero"],
                body="Buen dia " + nombre_completo.split()[0] + ",\nLa coordinadora de Grupo Mesteno solicita la factura de\n" + datos["empresa"] + "\ncorrespondiente al dia de hoy " + fecha_actual() + ".\n\nPor favor envie su factura respondiendo este mensaje.\nGracias.")
            msg.body("Solicitud enviada a " + nombre_completo + "\n(" + datos["empresa"] + ")")
        else:
            msg.body("No encontre a " + nombre + ". Usa: ver proveedores")

    elif mensaje_lower == "pide facturas a todos":
        if rancheros:
            enviados = []
            for clave, datos in rancheros.items():
                nombre_completo = datos.get("nombre_completo", clave.capitalize())
                client.messages.create(from_=SANDBOX_NUMBER, to=datos["numero"],
                    body="Buen dia " + nombre_completo.split()[0] + ",\nLa coordinadora de Grupo Mesteno solicita su factura del dia de hoy " + fecha_actual() + ".\n\nPor favor envie su factura respondiendo este mensaje.\nGracias.")
                enviados.append(nombre_completo)
            msg.body("Solicitudes enviadas a " + str(len(enviados)) + " proveedores:\n" + "\n".join(enviados))
        else:
            msg.body("No hay proveedores registrados.")

    elif mensaje_lower == "facturas del dia":
        facturas_dia = [f for f in facturas if f.get("tipo") != "transferencia"]
        if facturas_dia:
            lista = "FACTURAS RECIBIDAS HOY (" + str(len(facturas_dia)) + "):\n\n"
            for f in facturas_dia:
                tipo = " [ARCHIVO]" if f.get("tiene_archivo") else ""
                lista += f["hora"] + tipo + " - " + f["de"] + " (" + f["empresa"] + ")\n"
            msg.body(lista)
        else:
            msg.body("No hay facturas registradas hoy.")

    elif mensaje_lower.startswith("historial "):
        nombre = mensaje.split(" ", 1)[1]
        msg.body(historial_proveedor(nombre))

    elif mensaje_lower == "resumen":
        msg.body(resumen_diario())

    elif mensaje_lower == "limpiar":
        facturas.clear()
        transferencias_pendientes.clear()
        msg.body("Lista del dia limpiada.")

    elif mensaje_lower.startswith("transferencia "):
        partes = mensaje.split(" ")
        if len(partes) >= 3:
            nombre = partes[1]
            monto = partes[2].replace("$", "").replace(",", "")
            clave = buscar_proveedor(nombre)
            if clave:
                datos = rancheros[clave]
                nombre_completo = datos.get("nombre_completo", clave.capitalize())
                transferencias_pendientes[remitente] = {"destinatario": nombre_completo, "empresa": datos["empresa"], "monto": monto, "clabe": datos["clabe"], "banco": datos["banco"]}
                msg.body("Confirmar transferencia:\n─────────────────────\nDestinatario: " + nombre_completo + "\nEmpresa: " + datos["empresa"] + "\nBanco: " + datos["banco"] + "\nCLABE: " + datos["clabe"] + "\nMonto: $" + monto + "\nFecha: " + fecha_actual() + "\n\nResponde SI para confirmar o NO para cancelar.")
            else:
                msg.body("No encontre a " + nombre + ". Usa: ver proveedores")
        else:
            msg.body("Formato: transferencia Nombre Monto\nEjemplo: transferencia Juan 5000")

    else:
        nombre_proveedor = "Desconocido"
        empresa_proveedor = "Sin empresa"
        for clave, datos in rancheros.items():
            if datos["numero"] == remitente:
                nombre_proveedor = datos.get("nombre_completo", clave.capitalize())
                empresa_proveedor = datos["empresa"]
                break
        tiene_archivo = num_media > 0
        contenido = mensaje if mensaje else "[Sin texto]"
        if tiene_archivo:
            contenido += " [Archivo adjunto recibido]"
        facturas.append({"de": nombre_proveedor, "empresa": empresa_proveedor, "numero": remitente, "contenido": contenido, "hora": hora_actual(), "tiene_archivo": tiene_archivo, "media_url": media_url, "tipo": "factura"})
        if nombre_proveedor == "Desconocido":
            msg.body("Mensaje recibido. No estas registrado en el sistema. Contacta a la coordinadora de Grupo Mesteno.")
        else:
            msg.body("Recibido " + nombre_proveedor.split()[0] + ".\nTu factura de " + empresa_proveedor + " fue registrada a las " + hora_actual() + ".\nGracias.")

    return Response(str(resp), mimetype="text/xml")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
