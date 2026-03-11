from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from datetime import datetime
import os

app = Flask(__name__)

ACCOUNT_SID = os.environ.get("ACCOUNT_SID")
AUTH_TOKEN = os.environ.get("AUTH_TOKEN")
SANDBOX_NUMBER = "whatsapp:+14155238886"

client = Client(ACCOUNT_SID, AUTH_TOKEN)

facturas = []
rancheros = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    mensaje = request.form.get("Body", "").strip()
    remitente = request.form.get("From", "")
    resp = MessagingResponse()
    msg = resp.message()
    mensaje_lower = mensaje.lower()

    if mensaje_lower == "ayuda":
        msg.body("COMANDOS:\nagregar Juan +521XXXXXXXXXX Empresa RFC\nver rancheros\npide factura a Juan\npide facturas a todos\nfacturas del dia\nlimpiar\nayuda")

    elif mensaje_lower == "ver rancheros":
        if rancheros:
            lista = "PROVEEDORES:\n"
            for i, (nombre, datos) in enumerate(rancheros.items(), 1):
                lista += str(i) + ". " + nombre.capitalize() + " - " + datos["empresa"] + "\n"
            msg.body(lista)
        else:
            msg.body("No hay rancheros registrados.")

    elif mensaje_lower.startswith("agregar "):
        partes = mensaje.split(" ")
        if len(partes) >= 3:
            nombre = partes[1].lower()
            numero = partes[2]
            empresa = partes[3] if len(partes) >= 4 else "Sin empresa"
            rfc = partes[4] if len(partes) >= 5 else "Sin RFC"
            rancheros[nombre] = {"numero": "whatsapp:" + numero, "empresa": empresa, "rfc": rfc}
            msg.body("Ranchero " + nombre.capitalize() + " agregado. Empresa: " + empresa)
        else:
            msg.body("Formato: agregar Nombre +521XXXXXXXXXX Empresa RFC")

    elif mensaje_lower.startswith("pide factura a "):
        nombre = mensaje_lower.replace("pide factura a ", "").strip()
        if nombre in rancheros:
            numero = rancheros[nombre]["numero"]
            empresa = rancheros[nombre]["empresa"]
            client.messages.create(from_=SANDBOX_NUMBER, to=numero, body="Buen dia " + nombre.capitalize() + ", la coordinadora de Grupo Mesteno solicita la factura de " + empresa + " del dia de hoy. Gracias.")
            msg.body("Solicitud enviada a " + nombre.capitalize())
        else:
            msg.body("No encontre a " + nombre + ". Usa: ver rancheros")

    elif mensaje_lower == "pide facturas a todos":
        if rancheros:
            for nombre, datos in rancheros.items():
                client.messages.create(from_=SANDBOX_NUMBER, to=datos["numero"], body="Buen dia " + nombre.capitalize() + ", la coordinadora de Grupo Mesteno solicita su factura del dia de hoy. Gracias.")
            msg.body("Solicitud enviada a " + str(len(rancheros)) + " proveedores.")
        else:
            msg.body("No hay rancheros registrados.")

    elif mensaje_lower == "facturas del dia":
        if facturas:
            lista = "FACTURAS HOY: " + str(len(facturas)) + "\n\n"
            for f in facturas:
                lista += f["de"] + " a las " + f["hora"] + ":\n" + f["contenido"] + "\n\n"
            msg.body(lista)
        else:
            msg.body("No hay facturas hoy.")

    elif mensaje_lower == "limpiar":
        facturas.clear()
        msg.body("Lista limpiada.")

    else:
        nombre_ranchero = "Desconocido"
        empresa_ranchero = "Sin empresa"
        for nombre, datos in rancheros.items():
            if datos["numero"] == remitente:
                nombre_ranchero = nombre.capitalize()
                empresa_ranchero = datos["empresa"]
                break
        facturas.append({"de": nombre_ranchero, "empresa": empresa_ranchero, "numero": remitente, "contenido": mensaje, "hora": datetime.now().strftime("%H:%M")})
        msg.body("Factura recibida. Gracias, en breve la coordinadora la revisara.")

    return str(resp)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
