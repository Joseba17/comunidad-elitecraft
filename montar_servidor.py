"""
Monta el servidor de Discord de la comunidad de EliteCraft.

Uso:
    python montar_servidor.py            -> monta (o actualiza) el servidor
    python montar_servidor.py --simular  -> enseña lo que haría, sin tocar Discord

Se puede ejecutar las veces que haga falta: lo que ya existe se respeta y solo
se crea lo que falta. Así, para añadir streamers, basta con apuntarlos en
streamers.txt y volver a ejecutarlo.

Solo usa la librería estándar de Python (no hay que instalar nada).
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
API = "https://discord.com/api/v10"

# ---------------------------------------------------------------------------
# Permisos de Discord (bits)
# ---------------------------------------------------------------------------
P = {
    "CREATE_INSTANT_INVITE": 1 << 0,
    "KICK_MEMBERS": 1 << 1,
    "BAN_MEMBERS": 1 << 2,
    "ADMINISTRATOR": 1 << 3,
    "MANAGE_CHANNELS": 1 << 4,
    "ADD_REACTIONS": 1 << 6,
    "VIEW_AUDIT_LOG": 1 << 7,
    "STREAM": 1 << 9,
    "VIEW_CHANNEL": 1 << 10,
    "SEND_MESSAGES": 1 << 11,
    "MANAGE_MESSAGES": 1 << 13,
    "EMBED_LINKS": 1 << 14,
    "ATTACH_FILES": 1 << 15,
    "READ_MESSAGE_HISTORY": 1 << 16,
    "MENTION_EVERYONE": 1 << 17,
    "USE_EXTERNAL_EMOJIS": 1 << 18,
    "CONNECT": 1 << 20,
    "SPEAK": 1 << 21,
    "MUTE_MEMBERS": 1 << 22,
    "DEAFEN_MEMBERS": 1 << 23,
    "MOVE_MEMBERS": 1 << 24,
    "USE_VAD": 1 << 25,
    "CHANGE_NICKNAME": 1 << 26,
    "MANAGE_NICKNAMES": 1 << 27,
    "USE_APPLICATION_COMMANDS": 1 << 31,
    "REQUEST_TO_SPEAK": 1 << 32,
    "MANAGE_EVENTS": 1 << 33,
    "MANAGE_THREADS": 1 << 34,
    "CREATE_PUBLIC_THREADS": 1 << 35,
    "USE_EXTERNAL_STICKERS": 1 << 37,
    "SEND_MESSAGES_IN_THREADS": 1 << 38,
    "USE_EMBEDDED_ACTIVITIES": 1 << 39,
    "MODERATE_MEMBERS": 1 << 40,
    "USE_SOUNDBOARD": 1 << 42,
    "CREATE_EVENTS": 1 << 44,
    "SEND_VOICE_MESSAGES": 1 << 46,
    "SEND_POLLS": 1 << 49,
    "PIN_MESSAGES": 1 << 51,
}


def perms(*nombres):
    total = 0
    for n in nombres:
        total |= P[n]
    return total


# Lo que puede hacer cualquier miembro en general. No incluye encuestas
# (solo en #predicciones) ni mencionar a @everyone.
PERMISOS_MIEMBRO = perms(
    "CREATE_INSTANT_INVITE", "VIEW_CHANNEL", "SEND_MESSAGES", "SEND_MESSAGES_IN_THREADS",
    "CREATE_PUBLIC_THREADS", "EMBED_LINKS", "ATTACH_FILES", "ADD_REACTIONS",
    "USE_EXTERNAL_EMOJIS", "USE_EXTERNAL_STICKERS", "READ_MESSAGE_HISTORY", "CONNECT",
    "SPEAK", "STREAM", "USE_VAD", "USE_APPLICATION_COMMANDS", "CHANGE_NICKNAME",
    "REQUEST_TO_SPEAK", "USE_EMBEDDED_ACTIVITIES", "USE_SOUNDBOARD", "SEND_VOICE_MESSAGES",
)

ESCRIBIR = perms("SEND_MESSAGES", "SEND_MESSAGES_IN_THREADS", "CREATE_PUBLIC_THREADS", "SEND_POLLS")
VER = perms("VIEW_CHANNEL")

# ---------------------------------------------------------------------------
# Roles (de arriba abajo, en el orden en que se verán en Discord)
# ---------------------------------------------------------------------------
ROLES = [
    # nombre, color, separado en la lista de miembros, permisos
    ("Admin", 0xE5484D, True, perms("ADMINISTRATOR")),
    ("Moderador", 0x3E9BFF, True, perms(
        "KICK_MEMBERS", "BAN_MEMBERS", "MODERATE_MEMBERS", "MANAGE_MESSAGES", "PIN_MESSAGES",
        "MANAGE_THREADS", "MANAGE_NICKNAMES", "VIEW_AUDIT_LOG", "MUTE_MEMBERS",
        "DEAFEN_MEMBERS", "MOVE_MEMBERS", "MANAGE_EVENTS", "CREATE_EVENTS", "SEND_POLLS",
        "MENTION_EVERYONE")),
    ("Ayudante", 0x8CC4FF, True, perms(
        "MODERATE_MEMBERS", "MANAGE_MESSAGES", "PIN_MESSAGES", "MANAGE_THREADS",
        "MUTE_MEMBERS", "MOVE_MEMBERS")),
    ("Participante de EliteCraft", 0xF5B83D, True, 0),
    ("Creador de contenido", 0x57C7B8, False, 0),
    ("Desde la T1", 0xE07A3F, False, 0),
    ("Desde la T2", 0xD9577E, False, 0),
    ("Desde la T3", 0x9D7BEA, False, 0),
    ("Desde la T4", 0x4CC38A, False, 0),
    ("Noticias de EliteCraft", 0, False, 0),
    ("Novedades del servidor", 0, False, 0),
    ("Eventos", 0, False, 0),
    ("Todos los directos", 0, False, 0),
    # Después van los roles "Directo · <streamer>", sacados de streamers.txt
]
STAFF = ["Admin", "Moderador", "Ayudante"]
PREFIJO_DIRECTO = "Directo · "

# ---------------------------------------------------------------------------
# Canales
# ---------------------------------------------------------------------------
TEXTO, VOZ, CATEGORIA, ANUNCIOS, ESCENARIO, FORO = 0, 2, 4, 5, 13, 15
LISTA, GALERIA = 1, 2
POR_ACTIVIDAD, POR_FECHA = 0, 1

# Cada categoría: nombre, tipo de acceso, canales.
# Acceso: "publico", "lectura" (solo el staff escribe) o "staff" (privado).
# Las claves de cada canal:
#   tipo, tema, lento (segundos entre mensajes), acceso (si cambia respecto a
#   la categoría), escriben (roles que sí pueden escribir), etiquetas (foros),
#   reaccion (foros), vista (foros), orden (foros), encuestas (True/False).
ESTRUCTURA = [
    ("Inicio", "lectura", [
        ("bienvenida", dict(tipo=TEXTO, tema="Qué es este servidor y por dónde empezar.")),
        ("normas", dict(tipo=TEXTO, tema="Léelas antes de escribir. Son cortas.")),
        ("anuncios", dict(tipo=ANUNCIOS, tema="Novedades de este servidor. Elige el rol Novedades del servidor para recibir avisos.")),
        ("noticias-elitecraft", dict(tipo=ANUNCIOS, escriben=["Moderador"],
            tema="Anuncios oficiales de EliteCraft: participantes, fechas y eventos.")),
    ]),
    ("EliteCraft", "publico", [
        ("guía", dict(tipo=TEXTO, acceso="lectura",
            tema="Lo que se sabe de EliteCraft 4: fechas, Días de Élite, pranks, medallas y novedades.")),
        ("participantes", dict(tipo=TEXTO, acceso="lectura",
            tema="Quién participa en EliteCraft 4, con su Twitch y su hilo. Se actualiza solo.")),
        ("en-directo", dict(tipo=TEXTO, acceso="lectura",
            tema="Avisos automáticos cuando un participante empieza directo. Elige de quién en Canales y roles.")),
        # Foro con un hilo fijo por participante (los crea el script). Los miembros
        # responden en los hilos pero no abren hilos nuevos, para que no se desordene.
        ("comentando-directos", dict(tipo=FORO, acceso="respuestas", vista=LISTA, orden=POR_ACTIVIDAD, lento=3,
            tema="Un hilo por participante para comentar sus directos, y uno general. Aquí sí hay spoilers.")),
        ("clips", dict(tipo=FORO, vista=GALERIA, orden=POR_FECHA, reaccion="🔥",
            tema="Un clip por publicación. En el título, quién sale y qué pasa. Añade el enlace al clip o al directo.",
            etiquetas=["T1", "T2", "T3", "T4", "Mítico", "Gracioso", "Épico", "PvP", "Prank", "Construcción"])),
        ("teorías-y-lore", dict(tipo=FORO, vista=LISTA, orden=POR_ACTIVIDAD,
            tema="Teorías, alianzas, conflictos y la historia del server. Un tema por publicación.",
            etiquetas=["Teoría", "Alianzas", "Conflictos", "Lore", "Pranks", "Pregunta", "T1", "T2", "T3", "T4"])),
        ("nostalgia", dict(tipo=FORO, vista=LISTA, orden=POR_ACTIVIDAD,
            tema="Momentos, construcciones y recuerdos de las temporadas anteriores.",
            etiquetas=["T1", "T2", "T3", "Momento mítico", "Construcción", "Recuerdo"])),
        ("predicciones", dict(tipo=TEXTO, lento=30, encuestas=True,
            tema="Encuestas sobre lo que va a pasar: quién gana cada evento, alianzas, traiciones y dramas.")),
    ]),
    ("Comunidad", "publico", [
        ("general", dict(tipo=TEXTO, tema="Para hablar de lo que sea.")),
        ("memes", dict(tipo=TEXTO, tema="Memes de EliteCraft y de Minecraft.")),
        ("fanart-y-ediciones", dict(tipo=FORO, vista=GALERIA, orden=POR_FECHA, reaccion="❤️",
            tema="Dibujos, ediciones, skins y construcciones de la comunidad. Si no es tuyo, cita al autor.",
            etiquetas=["Dibujo", "Edición", "Skin", "Construcción", "Animación", "Música"])),
        ("minecraft", dict(tipo=TEXTO, tema="Minecraft en general: versiones, mods, construcciones y servidores.")),
        ("buscar-gente", dict(tipo=TEXTO, lento=30,
            tema="Busca con quién jugar. Di versión, modo o servidor y cuántos sois.")),
        ("tu-contenido", dict(tipo=TEXTO, lento=21600,
            tema="Comparte tu canal, tus vídeos o tu servidor. Un mensaje cada 6 horas.")),
        ("sugerencias", dict(tipo=FORO, vista=LISTA, orden=POR_ACTIVIDAD,
            tema="Ideas para mejorar el servidor. Una por publicación.",
            etiquetas=["Propuesta", "Error", "En estudio*", "Hecho*", "Descartado*"])),
    ]),
    ("Voz", "publico", [
        ("Charla 1", dict(tipo=VOZ)),
        ("Charla 2", dict(tipo=VOZ)),
        ("Viendo directos", dict(tipo=VOZ)),
        ("Jugando", dict(tipo=VOZ)),
        ("Escenario", dict(tipo=ESCENARIO, tema="Eventos de la comunidad.")),
    ]),
    ("Staff", "staff", [
        ("staff", dict(tipo=TEXTO, tema="Coordinación del equipo.")),
        ("registros", dict(tipo=TEXTO, tema="Alertas de AutoMod y avisos de Discord.")),
    ]),
]
# Las etiquetas con * solo las puede poner el staff (sirven para responder a sugerencias).

# Emoji de cada categoría y canal. En Discord se ven como "📌 Inicio" y "👋・bienvenida".
# Uno por canal y sin repetir, para encontrarlos de un vistazo. Si cambias uno,
# vuelve a ejecutar el script y renombra el canal (no crea otro).
EMOJIS = {
    "Inicio": "📌", "EliteCraft": "⚔️", "Comunidad": "🌍", "Voz": "🔊", "Staff": "🔒",
    "bienvenida": "👋", "normas": "📜", "anuncios": "📢", "noticias-elitecraft": "📰",
    "guía": "📖", "participantes": "👥", "en-directo": "🔴", "comentando-directos": "🍿", "clips": "🎬", "teorías-y-lore": "🧩",
    "nostalgia": "🕰️", "predicciones": "🔮",
    "general": "💬", "memes": "😂", "fanart-y-ediciones": "🎨", "minecraft": "⛏️",
    "buscar-gente": "🤝", "tu-contenido": "🚀", "sugerencias": "💡",
    "Charla 1": "🗣️", "Charla 2": "🗣️", "Viendo directos": "📺", "Jugando": "🎮", "Escenario": "🎤",
    "staff": "🛡️", "registros": "📋",
}
SEPARADOR = "・"


def nombre_visible(nombre, tipo):
    emoji = EMOJIS.get(nombre)
    if not emoji:
        return nombre
    return f"{emoji} {nombre}" if tipo == CATEGORIA else f"{emoji}{SEPARADOR}{nombre}"


def nombre_base(nombre):
    """Quita el emoji del principio: '👋・bienvenida' -> 'bienvenida', '📌 Inicio' -> 'Inicio'."""
    if SEPARADOR in nombre:
        return nombre.split(SEPARADOR, 1)[1]
    partes = nombre.split(" ", 1)
    if len(partes) == 2 and not any(ch.isalnum() for ch in partes[0]):
        return partes[1]
    return nombre


# Textos fijos de la carpeta textos/
TEXTOS = ["bienvenida", "normas", "guía", "staff"]

# Canales que hacen falta antes de activar el modo Comunidad.
PREVIOS = {"normas", "registros"}

# Participantes
ORGANIZADOR = "ElRichMC"
PREFIJO_HILO = "Hilo · "           # clave en roles_discord.json del hilo de cada participante
HILO_GENERAL = "General"           # hilo para comentar sin un participante concreto

# ---------------------------------------------------------------------------
# Preguntas al entrar (Onboarding)
# ---------------------------------------------------------------------------
PREGUNTAS = [
    dict(titulo="¿Desde cuándo sigues EliteCraft?", una_sola=True, obligatoria=True, opciones=[
        ("Desde la primera temporada", None, "Desde la T1"),
        ("Desde la segunda", None, "Desde la T2"),
        ("Desde la tercera", None, "Desde la T3"),
        ("Llego con la cuarta", None, "Desde la T4"),
    ]),
    dict(titulo="¿Qué avisos quieres recibir?", una_sola=False, obligatoria=False, opciones=[
        ("Noticias de EliteCraft", "Anuncios oficiales: participantes, fechas y eventos.", "Noticias de EliteCraft"),
        ("Novedades del servidor", "Cambios y anuncios de esta comunidad.", "Novedades del servidor"),
        ("Eventos", "Quizzes, noches de nostalgia y otros eventos de la comunidad.", "Eventos"),
    ]),
    # La tercera pregunta (avisos de directo) se construye con streamers.txt
]

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8")


def paso(texto):
    print(f"\n== {texto}")


def hecho(texto):
    print(f"   + {texto}")


def igual(texto):
    print(f"   = {texto}")


def aviso(texto):
    print(f"   ! {texto}")


def leer_token():
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    env = CARPETA / ".env"
    if not token and env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith("DISCORD_TOKEN="):
                token = linea.split("=", 1)[1].strip().strip('"').strip("'")
    if not token or token == "pega-aqui-el-token":
        sys.exit("No encuentro el token. Copia .env.example como .env y pega en él el token del bot.")
    return token


def leer_canales_twitch():
    """{nombre: canal_de_twitch} según streamers.txt ('Nombre' o 'Nombre | canal')."""
    archivo = CARPETA / "streamers.txt"
    canales = {}
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.split("#", 1)[0].strip()
            nombre, _, canal = linea.partition("|")
            nombre = nombre.strip()
            if nombre and nombre not in canales:
                canales[nombre] = (canal.strip() or nombre).lower()
    return canales


def leer_streamers():
    return list(leer_canales_twitch())


def agrupar_por_letra(nombres, tam):
    """Reparte los nombres en grupos parecidos de como mucho `tam`, en orden alfabético
    y sin partir una misma inicial entre dos grupos (salvo que no quepa en uno)."""
    ordenados = sorted(nombres, key=str.casefold)
    if not ordenados:
        return []
    n_grupos = -(-len(ordenados) // tam)
    objetivo = -(-len(ordenados) // n_grupos)
    letras = {}
    for n in ordenados:
        letras.setdefault(n[0].upper(), []).append(n)
    grupos, actual = [], []
    for bloque in letras.values():
        while len(bloque) > tam:  # una inicial con demasiados nombres
            if actual:
                grupos.append(actual)
                actual = []
            grupos.append(bloque[:tam])
            bloque = bloque[tam:]
        if actual and (len(actual) + len(bloque) > tam or len(actual) >= objetivo):
            grupos.append(actual)
            actual = []
        actual = actual + bloque
    if actual:
        grupos.append(actual)
    return grupos


def snowflake_generador():
    base = (int(time.time() * 1000) - 1420070400000) << 22
    n = 0
    while True:
        n += 1
        yield str(base + n)


class DiscordAPI:
    def __init__(self, token):
        self.cabeceras = {
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (https://discord.com/developers, 1.0) montar-servidor",
            "Content-Type": "application/json",
        }

    def __call__(self, metodo, ruta, cuerpo=None, motivo="Montaje del servidor"):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        for _ in range(6):
            pet = urllib.request.Request(API + ruta, data=datos, method=metodo,
                                         headers={**self.cabeceras, "X-Audit-Log-Reason": urllib.parse.quote(motivo)})
            try:
                with urllib.request.urlopen(pet, timeout=30) as r:
                    texto = r.read().decode()
                    return json.loads(texto) if texto else None
            except urllib.error.HTTPError as e:
                texto = e.read().decode(errors="replace")
                if e.code == 429:
                    espera = json.loads(texto).get("retry_after", 2)
                    time.sleep(float(espera) + 0.3)
                    continue
                raise ErrorDiscord(e.code, texto) from None
        raise ErrorDiscord(429, "Demasiadas peticiones seguidas, prueba otra vez en un minuto.")


class ErrorDiscord(Exception):
    def __init__(self, codigo, texto):
        super().__init__(f"{codigo}: {texto[:400]}")
        self.codigo = codigo


class APISimulada:
    """Imita las respuestas de Discord para ver el plan sin tocar nada."""

    def __init__(self):
        self.ids = snowflake_generador()

    def __call__(self, metodo, ruta, cuerpo=None, motivo=None):
        if metodo == "GET":
            if ruta == "/users/@me/guilds":
                return [{"id": "100", "name": "Servidor de prueba"}]
            if ruta.startswith("/guilds/100?"):
                return {"id": "100", "name": "Servidor de prueba", "features": [], "approximate_member_count": 1}
            if ruta == "/guilds/100/channels":
                return [
                    {"id": "201", "name": "Canales de texto", "type": CATEGORIA},
                    {"id": "202", "name": "general", "type": TEXTO, "parent_id": "201"},
                    {"id": "203", "name": "Canales de voz", "type": CATEGORIA},
                    {"id": "204", "name": "General", "type": VOZ, "parent_id": "203"},
                ]
            if ruta == "/guilds/100/roles":
                return [{"id": "100", "name": "@everyone", "position": 0},
                        {"id": "150", "name": "Montador", "position": 1, "managed": True}]
            if ruta == "/users/@me":
                return {"id": "150"}
            return []
        if metodo == "POST" and ruta.endswith("/invites"):
            return {"code": "prueba123"}
        if metodo == "POST":
            return {"id": next(self.ids), **(cuerpo or {})}
        return cuerpo


# ---------------------------------------------------------------------------
# Montaje
# ---------------------------------------------------------------------------
class Montador:
    def __init__(self, api, simulado):
        self.api = api
        self.simulado = simulado
        self.roles = {}      # nombre -> id
        self.canales = {}    # nombre -> id
        self.publicos = []   # ids de canales que ve todo el mundo
        self.streamers = leer_streamers()

    # -- servidor ----------------------------------------------------------
    def elegir_servidor(self):
        servidores = self.api("GET", "/users/@me/guilds")
        if not servidores:
            sys.exit("El bot no está en ningún servidor. Invítalo primero (mira LEEME.md, paso 3).")
        if len(servidores) == 1:
            return servidores[0]["id"]
        print("El bot está en varios servidores:")
        for i, s in enumerate(servidores, 1):
            print(f"  {i}. {s['name']}")
        n = input("¿En cuál lo monto? Escribe el número: ").strip()
        try:
            return servidores[int(n) - 1]["id"]
        except (ValueError, IndexError):
            sys.exit("Número no válido.")

    def preguntar(self, texto):
        if self.simulado:
            print(f"   ? {texto} (simulación: sí)")
            return True
        return input(f"   ? {texto} (s/n): ").strip().lower() in ("s", "si", "sí")

    def ejecutar(self):
        g = self.elegir_servidor()
        self.g = g
        info = self.api("GET", f"/guilds/{g}?with_counts=true")
        print(f"Servidor: {info['name']}")
        existentes = self.api("GET", f"/guilds/{g}/channels")
        nuestro = any(c["type"] == CATEGORIA and nombre_base(c["name"]).lower() == "inicio" for c in existentes)

        if not nuestro:
            miembros = info.get("approximate_member_count", 0)
            if len(existentes) > 12 or miembros > 5:
                sys.exit(f"Este servidor ya tiene {len(existentes)} canales y {miembros} miembros. "
                         "El script está pensado para un servidor nuevo y vacío; no sigo para no estropear nada.")
            if existentes:
                nombres = ", ".join(c["name"] for c in existentes)
                if self.preguntar(f"Borro los canales que Discord crea por defecto ({nombres})?"):
                    paso("Quitando los canales por defecto")
                    for c in sorted(existentes, key=lambda c: c["type"] == CATEGORIA):
                        self.api("DELETE", f"/channels/{c['id']}")
                        hecho(c["name"])
                    existentes = []
        else:
            print("Ya estaba montado: solo añado lo que falte.")

        self.existentes = existentes
        self.montar_roles()
        self.ajustes_basicos()
        self.montar_canales(solo=PREVIOS)
        self.activar_comunidad(info)
        self.montar_canales()
        self.montar_hilos()
        self.publicar_textos()
        self.publicar_participantes()
        self.anunciar_nuevos()
        self.guardar_ids()
        self.montar_automod()
        self.montar_onboarding()
        self.final()

    # -- roles -------------------------------------------------------------
    def montar_roles(self):
        paso("Roles")
        actuales = self.api("GET", f"/guilds/{self.g}/roles")
        por_nombre = {r["name"]: r for r in actuales}
        todos = list(ROLES) + [(PREFIJO_DIRECTO + s, 0, False, 0) for s in self.streamers]
        # Si ya existía el servidor, los streamers con rol nuevo son participantes recién anunciados.
        self.primera_vez = "Todos los directos" not in por_nombre
        self.nuevos = []
        for nombre, color, separado, permisos in todos:
            if nombre in por_nombre:
                self.roles[nombre] = por_nombre[nombre]["id"]
                igual(nombre)
                continue
            r = self.api("POST", f"/guilds/{self.g}/roles", {
                "name": nombre, "color": color, "hoist": separado,
                "permissions": str(permisos), "mentionable": False,
            })
            self.roles[nombre] = r["id"]
            if nombre.startswith(PREFIJO_DIRECTO):
                self.nuevos.append(nombre[len(PREFIJO_DIRECTO):])
            hecho(nombre)

        self.ordenar_roles([self.roles[n] for n, *_ in todos])

        # Permisos base de @everyone
        self.api("PATCH", f"/guilds/{self.g}/roles/{self.g}", {"permissions": str(PERMISOS_MIEMBRO)})
        hecho("Permisos básicos de @everyone (sin encuestas ni @everyone)")

    def ordenar_roles(self, nuestros):
        """Coloca nuestros roles justo debajo del rol del bot, en el orden de ROLES."""
        if self.simulado:
            hecho("Roles ordenados")
            return
        actuales = {r["id"]: r for r in self.api("GET", f"/guilds/{self.g}/roles")}
        yo = self.api("GET", "/users/@me")["id"]
        mis_roles = self.api("GET", f"/guilds/{self.g}/members/{yo}")["roles"]
        tope = max(actuales[r]["position"] for r in mis_roles)
        bot_nombre = max((actuales[r] for r in mis_roles), key=lambda r: r["position"])["name"]

        # Discord puede dar la misma posición a varios roles; en ese caso muestra
        # arriba el más antiguo. "rango" reproduce el orden que se ve en la app.
        visibles = sorted(actuales.values(), key=lambda r: (-r["position"], int(r["id"])))
        rango = {r["id"]: i for i, r in enumerate(visibles)}
        rango_bot = min(rango[r] for r in mis_roles)
        orden_actual = [rango[r] for r in nuestros]
        if rango_bot < orden_actual[0] and orden_actual == sorted(orden_actual):
            igual("Roles ya ordenados")
            return
        por_encima = [actuales[r]["name"] for r in nuestros if rango[r] < rango_bot]
        if por_encima:
            aviso(f"El rol del bot ({bot_nombre}) está por debajo de: {', '.join(por_encima)}.")
            aviso("Arrástralo arriba del todo en Ajustes del servidor > Roles y vuelve a ejecutar el script.")
            return
        otros = sorted((r for r in actuales.values()
                        if r["id"] not in nuestros and r["id"] != self.g and r["position"] < tope),
                       key=lambda r: -r["position"])
        orden = nuestros + [r["id"] for r in otros]
        try:
            self.api("PATCH", f"/guilds/{self.g}/roles",
                     [{"id": rid, "position": tope - 1 - i} for i, rid in enumerate(orden)])
            hecho("Roles ordenados")
        except ErrorDiscord as e:
            aviso(f"No he podido ordenar los roles ({e}). Ordénalos a mano si salen desordenados.")

    # -- ajustes -----------------------------------------------------------
    def ajustes_basicos(self):
        paso("Ajustes del servidor")
        self.api("PATCH", f"/guilds/{self.g}", {
            "verification_level": 2,            # cuenta con más de 5 minutos
            "explicit_content_filter": 2,       # revisar imágenes de todos
            "default_message_notifications": 1, # solo menciones
            "preferred_locale": "es-ES",
        })
        hecho("Notificaciones por defecto: solo menciones")
        hecho("Verificación media y filtro de contenido explícito para todos")

    def activar_comunidad(self, info):
        paso("Modo Comunidad")
        features = list(info.get("features", []))
        if "COMMUNITY" in features:
            igual("Ya estaba activado")
            return
        self.api("PATCH", f"/guilds/{self.g}", {
            "features": features + ["COMMUNITY"],
            "rules_channel_id": self.canales["normas"],
            "public_updates_channel_id": self.canales["registros"],
            "safety_alerts_channel_id": self.canales["registros"],
            "description": "Comunidad de fans de EliteCraft. No oficial.",
        })
        hecho("Activado (normas en #normas, avisos de Discord en #registros)")

    # -- canales -----------------------------------------------------------
    def permisos_de(self, acceso, extra):
        todos, staff = self.g, [self.roles[n] for n in STAFF]
        lista = []
        if acceso == "staff":
            lista.append({"id": todos, "type": 0, "allow": "0", "deny": str(VER)})
            lista += [{"id": r, "type": 0, "allow": str(VER), "deny": "0"} for r in staff]
        elif acceso == "lectura":
            lista.append({"id": todos, "type": 0, "allow": "0", "deny": str(ESCRIBIR)})
            escriben = extra.get("escriben", [])
            lista += [{"id": self.roles[n], "type": 0, "allow": str(ESCRIBIR), "deny": "0"} for n in escriben]
        elif acceso == "respuestas":
            # Foro: se puede responder en los hilos, pero solo el staff abre hilos nuevos.
            lista.append({"id": todos, "type": 0, "allow": str(P["SEND_MESSAGES_IN_THREADS"]),
                          "deny": str(perms("SEND_MESSAGES", "CREATE_PUBLIC_THREADS"))})
            lista.append({"id": self.roles["Moderador"], "type": 0, "allow": str(P["SEND_MESSAGES"]), "deny": "0"})
        elif extra.get("encuestas"):
            lista.append({"id": todos, "type": 0, "allow": str(P["SEND_POLLS"]), "deny": "0"})
        if extra.get("tipo") == ESCENARIO:
            lista.append({"id": self.roles["Moderador"], "type": 0, "deny": "0",
                          "allow": str(perms("MANAGE_CHANNELS", "MUTE_MEMBERS", "MOVE_MEMBERS"))})
        return lista

    def buscar(self, nombre, tipo, padre=None):
        """Busca el canal por su nombre sin emoji y, si el emoji ha cambiado, lo renombra."""
        visible = nombre_visible(nombre, tipo)
        for c in self.existentes:
            if (nombre_base(c["name"]).lower() == nombre.lower() and c["type"] == tipo
                    and (padre is None or c.get("parent_id") == padre)):
                if c["name"] != visible:
                    try:
                        self.api("PATCH", f"/channels/{c['id']}", {"name": visible})
                        print(f"   ~ {c['name']} -> {visible}")
                        c["name"] = visible
                    except ErrorDiscord as e:
                        aviso(f"No he podido renombrar {c['name']} ({e}).")
                return c["id"]
        return None

    def montar_canales(self, solo=None):
        paso("Canales" if solo is None else "Canales necesarios para el modo Comunidad")
        for pos_cat, (cat_nombre, cat_acceso, canales) in enumerate(ESTRUCTURA):
            if solo is not None and not any(n in solo for n, _ in canales):
                continue
            cat_id = self.buscar(cat_nombre, CATEGORIA)
            if not cat_id:
                c = self.api("POST", f"/guilds/{self.g}/channels", {
                    "name": nombre_visible(cat_nombre, CATEGORIA), "type": CATEGORIA, "position": pos_cat,
                    "permission_overwrites": self.permisos_de("staff" if cat_acceso == "staff" else "publico", {}),
                })
                cat_id = c["id"]
                self.existentes.append({**c, "type": CATEGORIA, "name": nombre_visible(cat_nombre, CATEGORIA)})
                hecho(f"[{nombre_visible(cat_nombre, CATEGORIA)}]")

            for pos, (nombre, op) in enumerate(canales):
                if solo is not None and nombre not in solo:
                    continue
                acceso = op.get("acceso", cat_acceso)
                cid = self.buscar(nombre, op["tipo"], cat_id)
                if cid:
                    self.canales[nombre] = cid
                    # Si has cambiado el tema en el script, se actualiza también en Discord.
                    actual = next((c for c in self.existentes if c["id"] == cid), {})
                    if (op.get("tema") and op["tipo"] in (TEXTO, ANUNCIOS, FORO)
                            and actual.get("topic") is not None and actual.get("topic") != op["tema"]):
                        self.api("PATCH", f"/channels/{cid}", {"topic": op["tema"]})
                        actual["topic"] = op["tema"]
                        print(f"   ~ tema de {nombre_visible(nombre, op['tipo'])} actualizado")
                    # Foros: añade las etiquetas nuevas del script sin tocar las que ya hay.
                    if op["tipo"] == FORO and "available_tags" in actual:
                        tienen = {t["name"] for t in actual["available_tags"]}
                        faltan = [t for t in op.get("etiquetas", []) if t.rstrip("*") not in tienen]
                        if faltan:
                            etiquetas = actual["available_tags"] + [
                                {"name": t.rstrip("*"), "moderated": t.endswith("*")} for t in faltan]
                            try:
                                self.api("PATCH", f"/channels/{cid}", {"available_tags": etiquetas[:20]})
                                print(f"   ~ etiquetas nuevas en {nombre_visible(nombre, op['tipo'])}: "
                                      + ", ".join(t.rstrip("*") for t in faltan))
                            except ErrorDiscord as e:
                                aviso(f"No he podido añadir etiquetas a {nombre} ({e}).")
                    if acceso != "staff":
                        self.publicos.append(cid)
                    if solo is None:
                        igual(nombre_visible(nombre, op["tipo"]))
                    continue
                self.retirar_tipo_antiguo(nombre, op["tipo"], cat_id)
                cuerpo = {
                    "name": nombre_visible(nombre, op["tipo"]), "type": op["tipo"], "parent_id": cat_id, "position": pos,
                    "permission_overwrites": self.permisos_de(acceso, op),
                }
                if op.get("tema") and op["tipo"] in (TEXTO, ANUNCIOS, FORO):
                    cuerpo["topic"] = op["tema"]
                if op.get("lento"):
                    # En un foro, el modo lento que importa es el de dentro de los hilos.
                    cuerpo["default_thread_rate_limit_per_user" if op["tipo"] == FORO else "rate_limit_per_user"] = op["lento"]
                if op["tipo"] == FORO:
                    cuerpo["available_tags"] = [
                        {"name": t.rstrip("*"), "moderated": t.endswith("*")} for t in op.get("etiquetas", [])
                    ]
                    cuerpo["default_forum_layout"] = op.get("vista", LISTA)
                    cuerpo["default_sort_order"] = op.get("orden", POR_ACTIVIDAD)
                    if op.get("reaccion"):
                        cuerpo["default_reaction_emoji"] = {"emoji_id": None, "emoji_name": op["reaccion"]}
                c = self.api("POST", f"/guilds/{self.g}/channels", cuerpo)
                self.canales[nombre] = c["id"]
                self.existentes.append({**c, "type": op["tipo"], "name": cuerpo["name"], "parent_id": cat_id})
                if acceso != "staff":
                    self.publicos.append(c["id"])
                hecho(cuerpo["name"])

        if solo is None:
            self.ordenar_canales()

    def retirar_tipo_antiguo(self, nombre, tipo, cat_id):
        """Si el canal existía con otro tipo (p. ej. texto y ahora es foro), Discord no deja
        convertirlo: se borra si está vacío o se renombra a '-antiguo' si tiene mensajes."""
        for c in list(self.existentes):
            if (nombre_base(c["name"]).lower() != nombre.lower() or c["type"] == tipo
                    or c["type"] == CATEGORIA or c.get("parent_id") != cat_id):
                continue
            mensajes = self.api("GET", f"/channels/{c['id']}/messages?limit=1") if c["type"] == TEXTO else []
            if mensajes:
                self.api("PATCH", f"/channels/{c['id']}", {"name": f"{nombre}-antiguo"})
                aviso(f"{c['name']} tenía mensajes: lo dejo como {nombre}-antiguo. Bórralo cuando no lo necesites.")
            else:
                self.api("DELETE", f"/channels/{c['id']}")
                print(f"   ~ {c['name']} pasa a ser de otro tipo: quito el antiguo (estaba vacío)")
            self.existentes.remove(c)

    def ordenar_canales(self):
        """Deja categorías y canales en el orden de ESTRUCTURA (útil al añadir canales nuevos)."""
        ids = {nombre_base(c["name"]).lower(): c["id"] for c in self.existentes if c["type"] == CATEGORIA}
        posiciones, n = [], 0
        for cat_nombre, _, canales in ESTRUCTURA:
            cat_id = ids.get(cat_nombre.lower())
            if cat_id:
                posiciones.append({"id": cat_id, "position": n})
            for nombre, _ in canales:
                if nombre in self.canales:
                    posiciones.append({"id": self.canales[nombre], "position": n})
                    n += 1
            n += 1
        try:
            self.api("PATCH", f"/guilds/{self.g}/channels", posiciones)
        except ErrorDiscord as e:
            aviso(f"No he podido ordenar los canales ({e}).")

    # -- hilos de comentando-directos ---------------------------------------
    def montar_hilos(self):
        paso("Hilos para comentar directos")
        foro = self.canales.get("comentando-directos")
        self.hilos = {}
        if not foro:
            return
        existentes = {}
        activos = self.api("GET", f"/guilds/{self.g}/threads/active") or {}
        archivados = self.api("GET", f"/channels/{foro}/threads/archived/public?limit=100") or {}
        for t in (activos.get("threads", []) if isinstance(activos, dict) else []) + \
                 (archivados.get("threads", []) if isinstance(archivados, dict) else []):
            if t.get("parent_id") == foro:
                existentes.setdefault(t["name"], t["id"])

        canales = leer_canales_twitch()
        deseados = [(f"💬 {HILO_GENERAL}", HILO_GENERAL,
                     "Para comentar EliteCraft en general, o cuando hay varios directos a la vez que se cruzan.")]
        deseados += [(s, s, f"Comenta aquí los directos de **{s}**.\n🔴 <https://twitch.tv/{canales.get(s, s.lower())}>")
                     for s in sorted(self.streamers, key=str.casefold)]
        for titulo, clave, texto in deseados:
            if titulo in existentes:
                self.hilos[clave] = existentes[titulo]
                igual(titulo)
                continue
            t = self.api("POST", f"/channels/{foro}/threads", {
                "name": titulo, "auto_archive_duration": 10080,
                "message": {"content": texto, "flags": 4, "allowed_mentions": {"parse": []}},
            })
            self.hilos[clave] = t["id"]
            if clave == HILO_GENERAL:
                try:
                    self.api("PATCH", f"/channels/{t['id']}", {"flags": 2})  # fijado arriba del foro
                except ErrorDiscord:
                    pass
            hecho(titulo)

    # -- textos ------------------------------------------------------------
    def rellenar(self, texto):
        def canal(m):
            cid = self.canales.get(m.group(1))
            return f"<#{cid}>" if cid else f"#{m.group(1)}"

        def rol(m):
            rid = self.roles.get(m.group(1))
            return f"<@&{rid}>" if rid else f"@{m.group(1)}"

        texto = re.sub(r"\{canal:([^}]+)\}", canal, texto)
        return re.sub(r"\{rol:([^}]+)\}", rol, texto)

    def publicar_textos(self):
        """Publica bienvenida y normas como mensaje normal. Si ya las publicó este bot,
        las actualiza en el sitio (sin borrar ni volver a publicar)."""
        paso("Textos de bienvenida y normas")
        for canal in TEXTOS:
            archivo = CARPETA / "textos" / f"{canal}.md"
            if archivo.exists():
                self.publicar_fijo(canal, self.rellenar(archivo.read_text(encoding="utf-8").strip()))

    def publicar_fijo(self, canal, texto):
        """Mantiene en un canal un texto fijo del bot: lo publica, lo edita si ha cambiado
        y lo reparte en varios mensajes si pasa del límite de Discord."""
        cid = self.canales.get(canal)
        if not cid:
            return
        if not hasattr(self, "yo"):
            self.yo = self.api("GET", "/users/@me")["id"]
        trozos, actual = [], ""
        for linea in texto.split("\n"):
            if actual and len(actual) + len(linea) + 1 > 1900:
                trozos.append(actual.rstrip("\n"))
                actual = ""
            actual += linea + "\n"
        if actual.strip():
            trozos.append(actual.rstrip("\n"))

        mensajes = self.api("GET", f"/channels/{cid}/messages?limit=50") or []
        mios = sorted((m for m in mensajes if m.get("author", {}).get("id") == self.yo), key=lambda m: int(m["id"]))
        if not mios and mensajes:
            igual(f"#{canal} tiene mensajes de otra persona, no lo toco")
            return
        if len(mios) == len(trozos) and all(m.get("content") == t and not m.get("embeds") for m, t in zip(mios, trozos)):
            igual(f"#{canal} sin cambios")
            return
        for i, trozo in enumerate(trozos):
            # flags 4 = sin vista previa de enlaces; menciones desactivadas para no avisar a nadie
            cuerpo = {"content": trozo, "embeds": [], "flags": 4, "allowed_mentions": {"parse": []}}
            if i < len(mios):
                self.api("PATCH", f"/channels/{cid}/messages/{mios[i]['id']}", cuerpo)
            else:
                self.api("POST", f"/channels/{cid}/messages", cuerpo)
        for sobrante in mios[len(trozos):]:
            self.api("DELETE", f"/channels/{cid}/messages/{sobrante['id']}")
        hecho(f"#{canal} {'actualizado' if mios else 'publicado'}")

    # -- participantes -----------------------------------------------------
    def linea_participante(self, nombre, canales):
        partes = [f"**{nombre}**", f"[Twitch](<https://twitch.tv/{canales.get(nombre, nombre.lower())}>)"]
        if nombre in self.hilos:
            partes.append(f"<#{self.hilos[nombre]}>")
        return " · ".join(partes)

    def publicar_participantes(self):
        paso("Lista de participantes")
        canales = leer_canales_twitch()
        confirmados = sorted((s for s in self.streamers if s != ORGANIZADOR), key=str.casefold)
        lineas = ["# 👥 Participantes de EliteCraft 4",
                  "-# Se actualiza sola cada vez que se confirma a alguien.", ""]
        if ORGANIZADOR in self.streamers:
            lineas += ["## Organiza", self.linea_participante(ORGANIZADOR, canales), ""]
        lineas += [f"## Confirmados · {len(confirmados)}"] + [self.linea_participante(s, canales) for s in confirmados]
        lineas += ["", "-# ¿Quieres avisos cuando entren en directo? Elige de quién en **Canales y roles**."]
        self.publicar_fijo("participantes", "\n".join(lineas))

    def anunciar_nuevos(self):
        """Anuncia en #noticias-elitecraft a los participantes añadidos en esta ejecución."""
        nuevos = [n for n in self.nuevos if n != ORGANIZADOR]
        if self.primera_vez or not nuevos:
            return
        paso("Anuncio de participantes nuevos")
        cid = self.canales.get("noticias-elitecraft")
        rol = self.roles.get("Noticias de EliteCraft")
        canales = leer_canales_twitch()
        if len(nuevos) == 1:
            titulo = f"## Nuevo participante: {nuevos[0]}"
            frase = f"**{nuevos[0]}** se une a EliteCraft 4."
        else:
            lista = ", ".join(f"**{n}**" for n in nuevos[:-1]) + f" y **{nuevos[-1]}**"
            titulo = "## Nuevos participantes confirmados"
            frase = f"{lista} se unen a EliteCraft 4."
        lineas = [f"<@&{rol}>" if rol else "", titulo, frase, ""]
        lineas += [self.linea_participante(n, canales) for n in nuevos]
        lineas += ["", "-# Para tener avisos de sus directos, actívalos en **Canales y roles**."]
        m = self.api("POST", f"/channels/{cid}/messages", {
            "content": "\n".join(l for l in lineas if l is not None).strip(), "flags": 4,
            "allowed_mentions": {"parse": [], "roles": [rol] if rol else []},
        })
        try:  # que llegue también a los servidores que siguen este canal
            self.api("POST", f"/channels/{cid}/messages/{m['id']}/crosspost")
        except ErrorDiscord:
            pass
        hecho(f"Anunciado en #noticias-elitecraft: {', '.join(nuevos)}")

    def guardar_ids(self):
        """roles_discord.json: lo que necesita el avisador (roles a mencionar e hilos de cada participante)."""
        ids = {n: i for n, i in self.roles.items() if n.startswith(PREFIJO_DIRECTO) or n == "Todos los directos"}
        ids.update({PREFIJO_HILO + n: i for n, i in self.hilos.items()})
        if not self.simulado:
            (CARPETA / "roles_discord.json").write_text(
                json.dumps(ids, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        hecho("roles_discord.json (para el avisador de directos)")

    # -- automod -----------------------------------------------------------
    def montar_automod(self):
        paso("AutoMod")
        actuales = {r["name"] for r in self.api("GET", f"/guilds/{self.g}/auto-moderation/rules") or []}
        alerta = {"type": 2, "metadata": {"channel_id": self.canales["registros"]}}
        staff = [self.roles[n] for n in STAFF]
        reglas = [
            dict(name="Spam", trigger_type=3, actions=[{"type": 1}, alerta]),
            dict(name="Menciones masivas", trigger_type=5,
                 trigger_metadata={"mention_total_limit": 5, "mention_raid_protection_enabled": True},
                 actions=[{"type": 1}, alerta, {"type": 3, "metadata": {"duration_seconds": 600}}]),
            dict(name="Invitaciones a otros servidores", trigger_type=1,
                 trigger_metadata={"regex_patterns": [r"discord(app)?\.(gg|com/invite)/\S+"]},
                 exempt_channels=[self.canales["tu-contenido"]],
                 actions=[{"type": 1, "metadata": {"custom_message":
                           "Las invitaciones a otros servidores solo se pueden compartir en #tu-contenido."}}, alerta]),
            dict(name="Contenido inapropiado", trigger_type=4,
                 trigger_metadata={"presets": [2, 3]},
                 actions=[{"type": 1}, alerta]),
        ]
        for r in reglas:
            if r["name"] in actuales:
                igual(r["name"])
                continue
            cuerpo = {"event_type": 1, "enabled": True, "exempt_roles": staff, **r}
            try:
                self.api("POST", f"/guilds/{self.g}/auto-moderation/rules", cuerpo)
            except ErrorDiscord:
                # Algunas reglas no admiten alerta o aislamiento: se prueba solo bloqueando.
                try:
                    cuerpo["actions"] = [a for a in cuerpo["actions"] if a["type"] == 1]
                    self.api("POST", f"/guilds/{self.g}/auto-moderation/rules", cuerpo)
                except ErrorDiscord as e:
                    aviso(f"{r['name']}: no se pudo crear ({e})")
                    continue
            hecho(r["name"])

    # -- onboarding --------------------------------------------------------
    def montar_onboarding(self):
        paso("Preguntas al entrar (Onboarding)")
        # Respeta los canales que hayas añadido tú a mano a los canales por defecto.
        try:
            previo = self.api("GET", f"/guilds/{self.g}/onboarding") or {}
            anteriores = previo.get("default_channel_ids", []) if isinstance(previo, dict) else []
        except ErrorDiscord:
            anteriores = []
        vigentes = {c["id"] for c in self.existentes}
        anteriores = [c for c in anteriores if c in vigentes]  # sin canales que ya no existen
        publicos = list(dict.fromkeys(self.publicos + anteriores))

        # Discord limita las opciones por pregunta. Al entrar solo se pregunta si
        # quieren avisos de todos; los streamers uno a uno se eligen después en
        # "Canales y roles", repartidos en grupos. Si el grupo es demasiado grande,
        # se prueba con uno más pequeño.
        for tam in (12, 10, 8, 6):
            try:
                prompts = self.preguntas_onboarding(tam)
                self.api("PUT", f"/guilds/{self.g}/onboarding", {
                    "prompts": prompts, "default_channel_ids": publicos, "enabled": True, "mode": 0,
                })
            except ErrorDiscord as e:
                if "TOO_MANY_ONBOARDING_OPTIONS" in str(e) and tam > 6:
                    continue
                aviso(f"No se pudo configurar ({e}).")
                aviso("Hazlo a mano en Ajustes del servidor > Incorporación (mira LEEME.md).")
                return
            grupos = len(prompts) - len(PREGUNTAS) - 1
            hecho(f"{len(PREGUNTAS) + 1} preguntas al entrar, {len(publicos)} canales visibles por defecto")
            if grupos > 0:
                hecho(f"Streamers en Canales y roles: {grupos} grupo(s) de hasta {tam}")
            return

    def preguntas_onboarding(self, tam):
        ids = snowflake_generador()
        preguntas = [dict(p, en_entrada=True) for p in PREGUNTAS]
        if self.streamers:
            preguntas.append(dict(
                titulo="¿Quieres avisos cuando empiece un directo?", una_sola=False, obligatoria=False, en_entrada=True,
                opciones=[("Sí, cuando empiecen los directos",
                           "Un solo aviso por tanda, no uno por participante. Para elegir de quién, ve luego a Canales y roles.",
                           "Todos los directos")],
            ))
            # En orden alfabético y, si hay varios grupos, con las letras que abarca cada uno.
            grupos = agrupar_por_letra(self.streamers, tam)
            for grupo in grupos:
                titulo = "¿De quién quieres avisos de directo?"
                if len(grupos) > 1:
                    desde, hasta = grupo[0][0].upper(), grupo[-1][0].upper()
                    titulo = f"Avisos de directo: {desde}" + (f" – {hasta}" if hasta != desde else "")
                preguntas.append(dict(titulo=titulo, una_sola=False, obligatoria=False, en_entrada=False,
                                      opciones=[(s, None, PREFIJO_DIRECTO + s) for s in grupo]))
        prompts = []
        for p in preguntas:
            opciones = []
            for titulo, desc, rol in p["opciones"]:
                o = {"id": next(ids), "title": titulo, "role_ids": [self.roles[rol]], "channel_ids": []}
                if desc:
                    o["description"] = desc
                opciones.append(o)
            prompts.append({
                "id": next(ids), "type": 0, "title": p["titulo"], "options": opciones,
                "single_select": p["una_sola"], "required": p["obligatoria"], "in_onboarding": p["en_entrada"],
            })
        return prompts

    # -- final -------------------------------------------------------------
    def final(self):
        paso("Invitación")
        try:
            inv = self.api("POST", f"/channels/{self.canales['bienvenida']}/invites",
                           {"max_age": 0, "max_uses": 0, "unique": False})
            hecho(f"https://discord.gg/{inv['code']}  (no caduca)")
        except ErrorDiscord as e:
            aviso(f"No se pudo crear la invitación ({e}).")
        print("\nListo. Si has añadido streamers, sube a GitHub streamers.txt y roles_discord.json.")


def main():
    simulado = "--simular" in sys.argv
    if simulado:
        print("MODO SIMULACIÓN: no se toca Discord.\n")
        api = APISimulada()
    else:
        api = DiscordAPI(leer_token())
    try:
        Montador(api, simulado).ejecutar()
    except ErrorDiscord as e:
        if e.codigo in (401,):
            sys.exit("\nEl token no es válido. Vuelve a copiarlo del portal de desarrolladores.")
        if e.codigo in (403,):
            sys.exit(f"\nAl bot le faltan permisos. Invítalo con permisos de Administrador (LEEME.md, paso 3).\n{e}")
        sys.exit(f"\nDiscord ha devuelto un error: {e}")


if __name__ == "__main__":
    main()
