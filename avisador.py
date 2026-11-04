"""
Avisa en #en-directo cuando un participante de EliteCraft empieza directo en Twitch.

- Lee los streamers de streamers.txt y los IDs de sus roles de roles_discord.json
  (este último lo crea montar_servidor.py).
- Publica un aviso con mención a "Directo · Nombre" y a "Todos los directos".
- Mientras dura el directo, actualiza el título y el juego si cambian.
- Cuando termina, edita el aviso para que ponga que ha terminado y cuánto duró.
  Así #en-directo siempre refleja quién está en directo ahora.

Pensado para ejecutarse cada pocos minutos (GitHub Actions lo hace solo).

Uso:
    python avisador.py            -> una pasada real
    python avisador.py --prueba   -> manda a #en-directo un aviso de ejemplo
    python avisador.py --simular  -> enseña lo que haría, sin tocar Twitch ni Discord

Variables (en .env para probar en local, o como secretos de GitHub):
    TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, DISCORD_WEBHOOK_EN_DIRECTO
    FILTRO (opcional): "minecraft" (por defecto), "elitecraft" o "todo"
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
ESTADO = CARPETA / "estado.json"
PREFIJO_DIRECTO = "Directo · "
PREFIJO_HILO = "Hilo · "
TODOS = "Todos los directos"
MORADO, GRIS = 0x9146FF, 0x4E5058
FALLOS_PARA_CERRAR = 2  # pasadas seguidas sin verle en directo antes de darlo por terminado
HORAS_ENTRE_AVISOS_TODOS = 6  # "Todos los directos" recibe como mucho un aviso cada 6 horas

for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
def cargar_env():
    env = CARPETA / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                clave, valor = linea.split("=", 1)
                os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def variable(nombre):
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        sys.exit(f"Falta {nombre}. Ponlo en .env (en local) o en los secretos del repositorio (GitHub).")
    return valor


def leer_streamers():
    """Devuelve [(nombre, login_de_twitch)]. Formato: 'Nombre' o 'Nombre | login'."""
    resultado = []
    for linea in (CARPETA / "streamers.txt").read_text(encoding="utf-8").splitlines():
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        nombre, _, login = linea.partition("|")
        nombre = nombre.strip()
        login = (login.strip() or nombre).lower()
        resultado.append((nombre, login))
    return resultado


def leer_roles():
    archivo = CARPETA / "roles_discord.json"
    if not archivo.exists():
        print("! No encuentro roles_discord.json: los avisos saldrán sin mencionar a nadie.")
        print("  Ejecuta montar_servidor.py una vez para crearlo.")
        return {}
    return json.loads(archivo.read_text(encoding="utf-8"))


def leer_estado():
    if ESTADO.exists():
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    return {}


def guardar_estado(estado):
    texto = json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not ESTADO.exists() or ESTADO.read_text(encoding="utf-8") != texto:
        ESTADO.write_text(texto, encoding="utf-8")


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def peticion(metodo, url, cuerpo=None, cabeceras=None, formulario=False):
    cabeceras = {"User-Agent": "AvisadorEliteCraft/1.0", **(cabeceras or {})}
    datos = None
    if cuerpo is not None:
        if formulario:
            datos = urllib.parse.urlencode(cuerpo).encode()
            cabeceras["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            datos = json.dumps(cuerpo).encode()
            cabeceras["Content-Type"] = "application/json"
    for _ in range(5):
        pet = urllib.request.Request(url, data=datos, method=metodo, headers=cabeceras)
        try:
            with urllib.request.urlopen(pet, timeout=30) as r:
                texto = r.read().decode()
                return json.loads(texto) if texto else None
        except urllib.error.HTTPError as e:
            texto = e.read().decode(errors="replace")
            if e.code == 429:
                try:
                    espera = float(json.loads(texto).get("retry_after", 2))
                except ValueError:
                    espera = 2
                time.sleep(espera + 0.3)
                continue
            raise RuntimeError(f"{metodo} {url.split('?')[0]} -> {e.code}: {texto[:300]}") from None
    raise RuntimeError("Demasiadas peticiones seguidas.")


# ---------------------------------------------------------------------------
# Twitch
# ---------------------------------------------------------------------------
class Twitch:
    def __init__(self, client_id, secreto):
        self.client_id = client_id
        r = peticion("POST", "https://id.twitch.tv/oauth2/token", {
            "client_id": client_id, "client_secret": secreto, "grant_type": "client_credentials",
        }, formulario=True)
        self.token = r["access_token"]

    def en_directo(self, logins):
        directos = {}
        for i in range(0, len(logins), 100):
            grupo = logins[i:i + 100]
            consulta = urllib.parse.urlencode([("user_login", l) for l in grupo] + [("first", "100")])
            r = peticion("GET", f"https://api.twitch.tv/helix/streams?{consulta}", cabeceras={
                "Client-Id": self.client_id, "Authorization": f"Bearer {self.token}",
            })
            for s in r.get("data", []):
                if s.get("type") == "live":
                    directos[s["user_login"].lower()] = s
        return directos

    def fotos(self, logins):
        """Foto de perfil de cada canal: {login: url}."""
        fotos = {}
        for i in range(0, len(logins), 100):
            consulta = urllib.parse.urlencode([("login", l) for l in logins[i:i + 100]])
            r = peticion("GET", f"https://api.twitch.tv/helix/users?{consulta}", cabeceras={
                "Client-Id": self.client_id, "Authorization": f"Bearer {self.token}",
            })
            for u in r.get("data", []):
                fotos[u["login"].lower()] = u.get("profile_image_url")
        return fotos


class TwitchSimulado:
    """Finge que están en directo los streamers de las posiciones indicadas."""

    def __init__(self, posiciones):
        self.posiciones = posiciones

    def en_directo(self, logins):
        ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {logins[i]: {
            "id": f"stream{i}", "user_login": logins[i], "user_name": logins[i], "type": "live",
            "title": "EliteCraft 4 | Día 1", "game_name": "Minecraft", "viewer_count": 1234,
            "started_at": ahora,
            "thumbnail_url": f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{logins[i]}-{{width}}x{{height}}.jpg",
        } for i in self.posiciones if i < len(logins)}

    def fotos(self, logins):
        return {l: f"https://example.com/{l}.png" for l in logins}


# ---------------------------------------------------------------------------
# Discord (webhook)
# ---------------------------------------------------------------------------
class Webhook:
    def __init__(self, url):
        self.url = url.split("?")[0].rstrip("/")

    def enviar(self, cuerpo):
        return peticion("POST", self.url + "?wait=true", cuerpo)["id"]

    def editar(self, mensaje_id, cuerpo):
        """Devuelve False si el mensaje ya no existe (por ejemplo, si alguien lo borró)."""
        try:
            peticion("PATCH", f"{self.url}/messages/{mensaje_id}", cuerpo)
            return True
        except RuntimeError as e:
            if "-> 404" in str(e):
                return False
            raise

    def borrar(self, mensaje_id):
        try:
            peticion("DELETE", f"{self.url}/messages/{mensaje_id}")
        except RuntimeError as e:
            if "-> 404" not in str(e):
                raise


class WebhookSimulado:
    def __init__(self):
        self.n = 0

    def enviar(self, cuerpo):
        self.n += 1
        e = cuerpo["embeds"][0]
        print(f"   -> PUBLICA {self.n}:", cuerpo.get("content") or "(sin menciones)", "|", e["title"])
        return str(self.n)

    def editar(self, mensaje_id, cuerpo):
        e = cuerpo["embeds"][0]
        print(f"   -> EDITA {mensaje_id}:", e["title"], "|", e.get("description", "").replace("\n", " / ")[:70])
        return True

    def borrar(self, mensaje_id):
        print(f"   -> BORRA {mensaje_id}")


def duracion(desde_iso):
    inicio = datetime.strptime(desde_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    minutos = int((datetime.now(timezone.utc) - inicio).total_seconds() // 60)
    h, m = divmod(max(minutos, 0), 60)
    return f"{h} h {m} min" if h else f"{m} min"


def autor(texto, login, foto):
    a = {"name": texto, "url": f"https://twitch.tv/{login}"}
    if foto:
        a["icon_url"] = foto
    return a


def pie(juego):
    return {"text": f"{juego} · Twitch" if juego else "Twitch"}


def embed_directo(nombre, s, foto=None, hilo=None):
    # Arriba, la foto y el nombre del streamer; debajo, el título del directo (enlace)
    # y, si existe, el hilo de #hilos-de-directos de ese participante.
    login = s["user_login"].lower()
    miniatura = s["thumbnail_url"].replace("{width}", "1280").replace("{height}", "720")
    embed = {
        "author": autor(f"{nombre} está en directo", login, foto),
        "title": (s.get("title") or "Sin título")[:256],
        "url": f"https://twitch.tv/{login}",
        "color": MORADO,
        "image": {"url": f"{miniatura}?t={int(time.time())}"},
        "footer": pie(s.get("game_name")),
        "timestamp": s["started_at"],
    }
    if hilo:
        embed["description"] = f"🍿 Coméntalo en <#{hilo}>"
    return embed


def embed_terminado(nombre, guardado):
    return {
        "author": autor(f"{nombre} estuvo en directo", guardado["login"], guardado.get("foto")),
        "title": (guardado.get("titulo") or "Sin título")[:256],
        "url": f"https://twitch.tv/{guardado['login']}",
        "description": f"Directo terminado · duró {duracion(guardado['inicio'])}",
        "color": GRIS,
        "footer": pie(guardado.get("juego")),
        "timestamp": guardado["inicio"],
    }


# ---------------------------------------------------------------------------
# Lógica
# ---------------------------------------------------------------------------
def pasa_filtro(s, filtro):
    if filtro == "todo":
        return True
    titulo = (s.get("title") or "").lower().replace(" ", "")
    juego = (s.get("game_name") or "").lower().replace(" ", "")
    # Si Twitch crea una categoría propia para EliteCraft, también cuenta.
    es_elitecraft = "elitecraft" in titulo or "elitecraft" in juego
    if filtro == "elitecraft":
        return es_elitecraft
    return es_elitecraft or juego == "minecraft"


def iso_a_unix(iso):
    return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def ahora_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def toca_avisar_a_todos(estado):
    """'Todos los directos' recibe un solo aviso por tanda: el primero tras HORAS_ENTRE_AVISOS_TODOS."""
    ultimo = estado.get("todos")
    return not ultimo or (time.time() - iso_a_unix(ultimo)) >= HORAS_ENTRE_AVISOS_TODOS * 3600


def embed_panel(directos, nombres):
    if not directos:
        return {
            "title": "En directo ahora",
            "description": "Ahora mismo no hay nadie en directo. Cuando empiece alguien, aparecerá aquí.",
            "color": GRIS, "footer": {"text": "Se actualiza solo cada pocos minutos"},
        }
    lineas = []
    for login, d in sorted(directos.items(), key=lambda x: (x[1]["inicio"], nombres.get(x[0], x[0]).lower())):
        titulo = (d.get("titulo") or "Sin título").replace("\n", " ")
        if len(titulo) > 60:
            titulo = titulo[:57].rstrip() + "…"
        lineas.append(f"**[{nombres.get(login, login)}](https://twitch.tv/{login})** · {titulo} · <t:{iso_a_unix(d['inicio'])}:R>")
    return {
        "title": f"En directo ahora · {len(directos)}",
        "description": "\n".join(lineas)[:4000],
        "color": MORADO, "footer": {"text": "Se actualiza solo cada pocos minutos"},
    }


def actualizar_panel(webhook, estado, nombres, al_final):
    """Mantiene un mensaje con quién está en directo. Si ha habido avisos nuevos,
    lo vuelve a publicar debajo para que siga siendo lo último del canal."""
    panel = embed_panel(estado["directos"], nombres)
    cuerpo = {"embeds": [panel], "allowed_mentions": {"parse": []}}
    huella = panel["title"] + panel["description"]
    if estado.get("panel") and not al_final:
        if estado.get("panel_huella") == huella:
            return
        if webhook.editar(estado["panel"], cuerpo):
            estado["panel_huella"] = huella
            return
    if estado.get("panel"):
        webhook.borrar(estado["panel"])
    estado["panel"] = webhook.enviar(cuerpo)
    estado["panel_huella"] = huella


def pasada(twitch, webhook, filtro):
    streamers = leer_streamers()
    nombres = {login: nombre for nombre, login in streamers}
    roles = leer_roles()
    estado = leer_estado()
    estado.setdefault("directos", {})
    vivos = estado["directos"]
    directos = twitch.en_directo(list(nombres))
    hubo_nuevos = False
    nuevos = [l for l, s in directos.items() if l not in vivos or vivos[l]["stream"] != s["id"]]
    try:
        fotos = twitch.fotos(nuevos) if nuevos else {}
    except RuntimeError:
        fotos = {}  # sin foto el aviso sale igual

    # Directos nuevos o que siguen
    for login, s in directos.items():
        nombre = nombres.get(login, s["user_name"])
        guardado = vivos.get(login)
        if guardado and guardado["stream"] != s["id"]:
            # Ha empezado otro directo sin que viéramos terminar el anterior
            webhook.editar(guardado["mensaje"], {"embeds": [embed_terminado(nombre, guardado)]})
            guardado = None
        if guardado:
            guardado["fallos"] = 0
            if (s.get("title"), s.get("game_name")) != (guardado.get("titulo"), guardado.get("juego")):
                guardado.update(titulo=s.get("title"), juego=s.get("game_name"))
                webhook.editar(guardado["mensaje"], {"embeds": [embed_directo(nombre, s, guardado.get("foto"), roles.get(PREFIJO_HILO + nombre))]})
                print(f"   ~ {nombre}: título o juego actualizado")
            continue
        if not pasa_filtro(s, filtro):
            vivos.pop(login, None)
            continue
        quienes = [PREFIJO_DIRECTO + nombre]
        if toca_avisar_a_todos(estado):
            quienes.append(TODOS)
            estado["todos"] = ahora_iso()
        ids = [roles[n] for n in quienes if n in roles]
        mensaje = webhook.enviar({
            "content": " ".join(f"<@&{i}>" for i in ids), "embeds": [embed_directo(nombre, s, fotos.get(login), roles.get(PREFIJO_HILO + nombre))],
            "allowed_mentions": {"parse": [], "roles": ids},
        })
        vivos[login] = {
            "login": login, "stream": s["id"], "mensaje": mensaje, "inicio": s["started_at"],
            "titulo": s.get("title"), "juego": s.get("game_name"), "fallos": 0, "foto": fotos.get(login),
        }
        hubo_nuevos = True
        print(f"   + {nombre} ha empezado directo" + (" (aviso a Todos los directos)" if TODOS in quienes else ""))

    # Directos que han terminado
    for login in list(vivos):
        if login in directos:
            continue
        guardado = vivos[login]
        guardado["fallos"] = guardado.get("fallos", 0) + 1
        if guardado["fallos"] >= FALLOS_PARA_CERRAR:
            nombre = nombres.get(login, login)
            webhook.editar(guardado["mensaje"], {"embeds": [embed_terminado(nombre, guardado)]})
            del vivos[login]
            print(f"   - {nombre} ha terminado")

    actualizar_panel(webhook, estado, nombres, al_final=hubo_nuevos)
    guardar_estado(estado)
    en_curso = ", ".join(nombres.get(l, l) for l in vivos) or "nadie"
    print(f"En directo ahora: {en_curso}")


def prueba(webhook):
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ejemplo = {
        "id": "0", "user_login": "elrichmc", "user_name": "ElRichMC", "title": "Aviso de prueba: esto es lo que verá la gente",
        "game_name": "Minecraft", "started_at": ahora,
        "thumbnail_url": "https://static-cdn.jtvnw.net/ttv-static/404_preview-{width}x{height}.jpg",
    }
    foto = None
    if os.environ.get("TWITCH_CLIENT_ID") and os.environ.get("TWITCH_CLIENT_SECRET"):
        try:
            foto = Twitch(os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"]).fotos(["elrichmc"]).get("elrichmc")
        except RuntimeError as e:
            print(f"! No he podido conectar con Twitch, el aviso sale sin foto ({e}).")
    webhook.enviar({"content": "*(Aviso de prueba, sin mencionar a nadie. Bórralo cuando lo hayas visto.)*",
                    "embeds": [embed_directo("ElRichMC", ejemplo, foto)], "allowed_mentions": {"parse": []}})
    print("Aviso de prueba enviado a #en-directo.")


def main():
    cargar_env()
    filtro = os.environ.get("FILTRO", "minecraft").strip().lower() or "minecraft"
    if "--simular" in sys.argv:
        print(f"MODO SIMULACIÓN (filtro: {filtro})")
        global ESTADO
        ESTADO = CARPETA / "estado_simulacion.json"
        ESTADO.unlink(missing_ok=True)
        web = WebhookSimulado()
        pasos = [
            ("Empieza el primero (avisa también a Todos)", [0]),
            ("Empieza el segundo (solo a su rol)", [0, 1]),
            ("Sigue igual: no hace nada", [0, 1]),
            ("El primero desaparece una vez: espera", [1]),
            ("Segunda vez sin verle: lo da por terminado", [1]),
            ("Termina el segundo", []),
            ("Confirmado: ya no hay nadie", []),
        ]
        for texto, vivos in pasos:
            print(f"\n[{texto}]")
            pasada(TwitchSimulado(vivos), web, filtro)
        ESTADO.unlink(missing_ok=True)
        return
    webhook = Webhook(variable("DISCORD_WEBHOOK_EN_DIRECTO"))
    if "--prueba" in sys.argv:
        prueba(webhook)
        return
    twitch = Twitch(variable("TWITCH_CLIENT_ID"), variable("TWITCH_CLIENT_SECRET"))
    pasada(twitch, webhook, filtro)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        sys.exit(f"Error: {e}")
