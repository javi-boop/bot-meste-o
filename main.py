from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from datetime import datetime
import os

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

# ─── HELPERS ───

def hora_actual():
    return datetime.now().strftime("%H:%M")

def fecha_actual():
    return datetime.now().strftime("%d/%m/%Y")

def historial_ranchero(nombre):
    nombre_lower = nombre.lower()
    facturas_ranchero = [f for f in facturas if f["de"].lower() == nombre_lower]
    if not facturas_ranchero:
        return "No hay facturas de " + nombre.capitalize() + " hoy."
    resultado = "HISTORIAL DE " + nombre.upper() + " HOY:\n\n"
    for f in facturas_ranchero:
        tipo = " [ARCHIVO]" if f.get("tiene_archivo") else ""
        resultado += f["hora"] + tipo + " - " + f["empresa"] + ":\n" + f["contenido"] + "\n\n"
    return resultado.strip()

def resumen_diario():
    total = len(facturas)
    rancheros_que_enviaron = set(f["de"] for f in facturas if f["de"] != "Desconocido")
    rancheros_pendientes = set(rancheros.keys()) - set(r.lower() for r in rancheros_que_enviaron)
    resumen = "RESUMEN DEL DIA - " + fecha_actual() + "\n"
    resumen += "─────────────────────\n"
    resumen += "Facturas recibidas: " + str(total) + "\n"
    resumen += "Proveedores que enviaron: " + str(len(rancheros_que_enviaron)) + "\n"
    resumen += "Proveedores pendientes: " + str(len(rancheros_pendientes)) + "\n\n"
    if rancheros_que_enviaron:
        resumen += "ENVIARON:\n"
        for r in sorted(rancheros_que_enviaron):
            resumen += "  + " + r.capitalize() + "\n"
    if rancheros_pendientes:
        resumen += "\nPENDIENTES:\n"
        for r in sorted(rancheros_pendientes):
            resumen += "  - " + r.capitalize() + "\n"
    return resumen

def menu_principal():
    return (
        "Bienvenida al asistente de Grupo Mesteno\n"
        "─────────────────────\n\n"
        "PROVEEDORES:\n"
        "  agregar Juan +521XXXXXXXXXX Empresa\n"
        "  ver rancheros\n"
        "  historial Juan\n\n"
        "FACTURAS:\n"
        "  pide factura a Juan\n"
        "  pide facturas a todos\n"
        "  facturas del dia\n"
        "  limpiar\n\n"
        "TRANSFERENCIAS:\n"
        "  transferencia Juan 5000\n\n"
        "REPORTES:\n"
        "  resumen\n\n"
        "  ayuda - ver este menu"
    )

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje = request.form.get("Body", "").strip()
    remitente = request.form.get("From", "")
    num_media = int(request.form.get("NumMedia", 0))
    media_url = request.form.get("MediaUrl0", "")
    resp = MessagingResponse()
    msg = resp.message()
    mensaje_lower = mensaje.lower().strip()

    if remitente not in usuarios_conocidos:
        usuarios_conocidos.add(remitente)
        msg.body(menu_principal())
        return Response(str(resp), mimetype="text/xml")

    if remitente in transferencias_pendientes:
        pendiente = transferencias_pendientes[remitente]
        if mensaje_lower in ["si", "confirmar"]:
            del transferencias_pendientes[remitente]
            facturas.append({
                "de": "COORDINADORA",
                "empresa": "Grupo Mesteno",
                "numero": remitente,
                "contenido": "TRANSFERENCIA CONFIRMADA a " + pendiente["destinatario"] + " por $" + pendiente["monto"],
                "hora": hora_actual(),
                "tiene_archivo": False,
                "media_url": "",
                "tipo": "transferencia"
            })
            msg.body("Transferencia registrada:\nDestinatario: " + pendiente["destinatario"] + "\nMonto: $" + pendiente["monto"] + "\nHora: " + hora_actual())
        elif mensaje_lower in ["no", "cancelar"]:
            del transferencias_pendientes[remitente]
            msg.body("Transferencia cancelada.")
        else:
            msg.body("Tienes una transferencia pendiente:\nDestinatario: " + pendiente["destinatario"] + "\nMonto: $" + pendiente["monto"] + "\n\nResponde SI para confirmar o NO para cancelar.")
        return Response(str(resp), mimetype="text/xml")

    if mensaje_lower in ["ayuda", "menu", "inicio", "hola"]:
        msg.body(menu_principal())

    elif mensaje_lower == "ver rancheros":
        if rancheros:
            lista = "PROVEEDORES REGISTRADOS (" + str(len(rancheros)) + "):\n\n"
            for i, (nombre, datos) in enumerate(rancheros.items(), 1):
                lista += str(i) + ". " + nombre.capitalize() + " - " + datos["empresa"] + "\n"
            msg.body(lista)
        else:
            msg.body("No hay rancheros registrados.\nUsa: agregar Nombre +521XXXXXXXXXX Empresa")

    elif mensaje_lower.startswith("agregar "):
        partes = mensaje.split(" ")
        if len(partes) >= 3:
            nombre = partes[1].lower()
            numero = partes[2]
            empresa = " ".join(partes[3:]) if len(partes) >= 4 else "Sin empresa"
            rancheros[nombre] = {"numero": "whatsapp:" + numero, "empresa": empresa}
            msg.body("Ranchero registrado:\nNombre: " + nombre.capitalize() + "\nEmpresa: " + empresa + "\nNumero: " + numero)
        else:
            msg.body("Formato: agregar Nombre +521XXXXXXXXXX Empresa")

    elif mensaje_lower.startswith("eliminar "):
        nombre = mensaje_lower.replace("eliminar ", "").strip()
        if nombre in rancheros:
            del rancheros[nombre]
            msg.body("Ranchero " + nombre.capitalize() + " eliminado.")
        else:
            msg.body("No encontre a " + nombre + ". Usa: ver rancheros")

    elif mensaje_lower.startswith("historial "):
        nombre = mensaje_lower.replace("historial ", "").strip()
        msg.body(historial_ranchero(nombre))

    elif mensaje_lower.startswith("pide factura a "):
        nombre = mensaje_lower.replace("pide factura a ", "").strip()
        if nombre in rancheros:
            numero = rancheros[nombre]["numero"]
            empresa = rancheros[nombre]["empresa"]
            client.messages.create(from_=SANDBOX_NUMBER, to=numero, body="Buen dia " + nombre.capitalize() + ",\nLa coordinadora de Grupo Mesteno solicita la factura de " + empresa + " del dia de hoy " + fecha_actual() + ".\nPor favor envie su factura respondiendo este mensaje.\nGracias.")
            msg.body("Solicitud enviada a " + nombre.capitalize() + " (" + empresa + ")")
        else:
            msg.body("No encontre a " + nombre + ". Usa: ver rancheros")

    elif mensaje_lower == "pide facturas a todos":
        if rancheros:
            enviados = []
            for nombre, datos in rancheros.items():
                client.messages.create(from_=SANDBOX_NUMBER, to=datos["numero"], body="Buen dia " + nombre.capitalize() + ",\nLa coordinadora de Grupo Mesteno solicita su factura del dia de hoy " + fecha_actual() + ".\nPor favor envie su factura respondiendo este mensaje.\nGracias.")
                enviados.append(nombre.capitalize())
            msg.body("Solicitudes enviadas a " + str(len(enviados)) + " proveedores:\n" + "\n".join(enviados))
        else:
            msg.body("No hay rancheros registrados.")

    elif mensaje_lower == "facturas del dia":
        if facturas:
            lista = "FACTURAS RECIBIDAS HOY (" + str(len(facturas)) + "):\n\n"
            for f in facturas:
                tipo = " [ARCHIVO]" if f.get("tiene_archivo") else ""
                lista += f["de"] + " - " + f["empresa"] + " " + f["hora"] + tipo + "\n"
            msg.body(lista)
        else:
            msg.body("No hay facturas registradas hoy.")

    elif mensaje_lower == "resumen":
        msg.body(resumen_diario())

    elif mensaje_lower == "limpiar":
        facturas.clear()
        transferencias_pendientes.clear()
        msg.body("Lista del dia limpiada.")

    elif mensaje_lower.startswith("transferencia "):
        partes = mensaje_lower.split(" ")
        if len(partes) >= 3:
            destinatario = partes[1].capitalize()
            monto = partes[2].replace("$", "").replace(",", "")
            transferencias_pendientes[remitente] = {"destinatario": destinatario, "monto": monto}
            msg.body("Confirmar transferencia:\n─────────────────────\nDestinatario: " + destinatario + "\nMonto: $" + monto + "\nFecha: " + fecha_actual() + "\nHora: " + hora_actual() + "\n\nResponde SI para confirmar o NO para cancelar.")
        else:
            msg.body("Formato: transferencia Nombre Monto\nEjemplo: transferencia Juan 5000")

    else:
        nombre_ranchero = "Desconocido"
        empresa_ranchero = "Sin empresa"
        for nombre, datos in rancheros.items():
            if datos["numero"] == remitente:
                nombre_ranchero = nombre.capitalize()
                empresa_ranchero = datos["empresa"]
                break
        tiene_archivo = num_media > 0
        contenido = mensaje if mensaje else "[Sin texto]"
        if tiene_archivo:
            contenido += " [Archivo adjunto recibido]"
        facturas.append({"de": nombre_ranchero, "empresa": empresa_ranchero, "numero": remitente, "contenido": contenido, "hora": hora_actual(), "tiene_archivo": tiene_archivo, "media_url": media_url, "tipo": "factura"})
        if nombre_ranchero == "Desconocido":
            msg.body("Mensaje recibido. No estas registrado en el sistema. Contacta a la coordinadora.")
        else:
            msg.body("Recibido " + nombre_ranchero + ". Tu factura fue registrada a las " + hora_actual() + ". Gracias.")

    return Response(str(resp), mimetype="text/xml")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
