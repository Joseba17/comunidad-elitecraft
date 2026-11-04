"""
Crea un evento de Discord: sale arriba del servidor con cuenta atrás, y quien pulse
"Me interesa" recibe un aviso cuando empieza.

Ejemplos:
    python crear_evento.py "Estreno de EliteCraft 4" "2026-12-01 18:00"
    python crear_evento.py "Evento: carrera al End" "2026-12-08 20:00" --horas 2 --avisar
    python crear_evento.py "Día de Élite" "2026-12-08 18:00" --semanal
    python crear_evento.py "Noche de nostalgia" "2026-11-20 22:00" --lugar "🎤・Escenario" --descripcion "Vemos los mejores momentos de la T1."

La hora es la de España (se ajusta sola al horario de verano o de invierno).
Con --avisar, además se anuncia en #noticias-elitecraft mencionando a "Noticias de EliteCraft".
Usa el mismo bot y el mismo .env que montar_servidor.py.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone

import montar_servidor as m


def ultimo_domingo(anio, mes):
    d = datetime(anio, mes + 1, 1) - timedelta(days=1) if mes < 12 else datetime(anio, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def hora_espana_a_utc(texto):
    """'2026-12-01 18:00' (hora peninsular) -> datetime en UTC."""
    try:
        local = datetime.strptime(texto.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        sys.exit('La fecha va así: "AAAA-MM-DD HH:MM", por ejemplo "2026-12-01 18:00".')
    # Horario de verano: del último domingo de marzo al último domingo de octubre.
    inicio_verano = ultimo_domingo(local.year, 3).replace(hour=2)
    fin_verano = ultimo_domingo(local.year, 10).replace(hour=3)
    desfase = 2 if inicio_verano <= local < fin_verano else 1
    return (local - timedelta(hours=desfase)).replace(tzinfo=timezone.utc)


def buscar(lista, nombre, tipo=None):
    for c in lista:
        base = m.nombre_base(c["name"]).lower() if "type" in c else c["name"].lower()
        if base == nombre.lower() and (tipo is None or c.get("type") == tipo):
            return c
    return None


def main():
    p = argparse.ArgumentParser(description="Crea un evento de Discord en el servidor.")
    p.add_argument("nombre", help='Nombre del evento, entre comillas. Ej.: "Estreno de EliteCraft 4"')
    p.add_argument("fecha", help='Cuándo empieza, hora de España. Ej.: "2026-12-01 18:00"')
    p.add_argument("--horas", type=float, default=3, help="Cuánto dura (por defecto, 3 horas)")
    p.add_argument("--lugar", default="Twitch", help='Dónde se ve. Por defecto "Twitch"')
    p.add_argument("--descripcion", default="", help="Texto que sale en el evento")
    p.add_argument("--semanal", action="store_true", help="Repetirlo cada semana el mismo día y a la misma hora")
    p.add_argument("--avisar", action="store_true", help="Anunciarlo también en #noticias-elitecraft")
    p.add_argument("--simular", action="store_true", help="Enseña lo que haría, sin tocar Discord")
    a = p.parse_args()

    inicio = hora_espana_a_utc(a.fecha)
    if inicio <= datetime.now(timezone.utc):
        sys.exit("Esa fecha ya ha pasado.")
    fin = inicio + timedelta(hours=a.horas)

    api = m.APISimulada() if a.simular else m.DiscordAPI(m.leer_token())
    g = m.Montador(api, a.simular).elegir_servidor()
    try:
        evento = api("POST", f"/guilds/{g}/scheduled-events", {
            "name": a.nombre[:100], "description": a.descripcion[:1000],
            "privacy_level": 2, "entity_type": 3,  # 3 = evento externo (fuera de un canal de voz)
            "entity_metadata": {"location": a.lugar[:100]},
            "scheduled_start_time": inicio.isoformat(), "scheduled_end_time": fin.isoformat(),
            **({"recurrence_rule": {"start": inicio.isoformat(), "frequency": 2, "interval": 1,
                                    "by_weekday": [inicio.weekday()]}} if a.semanal else {}),
        })
    except m.ErrorDiscord as e:
        sys.exit(f"Discord no ha dejado crear el evento: {e}")
    enlace = f"https://discord.com/events/{g}/{evento['id']}"
    print(f"Evento creado: {a.nombre}")
    print(f"  Empieza: {a.fecha} (hora de España) · dura {a.horas:g} h · {a.lugar}")
    print(f"  Enlace: {enlace}")
    if a.semanal:
        print("  Se repite cada semana. Discord lo guarda en hora universal: cuando cambie la hora")
        print("  (último domingo de marzo y de octubre), revisa que siga a la hora buena.")

    if a.avisar:
        canales = api("GET", f"/guilds/{g}/channels") or []
        roles = api("GET", f"/guilds/{g}/roles") or []
        canal = buscar(canales, "noticias-elitecraft")
        rol = buscar(roles, "Noticias de EliteCraft")
        if not canal:
            print("! No encuentro #noticias-elitecraft: no lo anuncio.")
            return
        unix = int(inicio.timestamp())
        texto = "\n".join(filter(None, [
            f"<@&{rol['id']}>" if rol else "",
            f"## {a.nombre}",
            a.descripcion,
            f"🗓️ <t:{unix}:F> · <t:{unix}:R>",
            "-# Pulsa «Me interesa» en el evento para que te avise al empezar.",
            enlace,
        ]))
        api("POST", f"/channels/{canal['id']}/messages", {
            "content": texto, "allowed_mentions": {"parse": [], "roles": [rol["id"]] if rol else []},
        })
        print("  Anunciado en #noticias-elitecraft.")


if __name__ == "__main__":
    main()
