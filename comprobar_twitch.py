"""
Comprueba canales de Twitch antes de añadirlos a streamers.txt.

Uso:
    python comprobar_twitch.py canal1 canal2 ...

Por cada canal dice si existe, su nombre, si es partner o afiliado, el
principio de su descripción y la fecha de su último directo guardado.
Usa las mismas claves de Twitch que el avisador (archivo .env).
"""
import os
import sys

import avisador as a

a.cargar_env()
t = a.Twitch(a.variable("TWITCH_CLIENT_ID"), a.variable("TWITCH_CLIENT_SECRET"))
cab = {"Client-Id": t.client_id, "Authorization": "Bearer " + t.token}

for login in sys.argv[1:]:
    r = a.peticion("GET", "https://api.twitch.tv/helix/users?login=" + login.lower(), cabeceras=cab)
    if not r["data"]:
        print(f"{login:<20} no existe")
        continue
    u = r["data"][0]
    v = a.peticion("GET", "https://api.twitch.tv/helix/videos?first=1&user_id=" + u["id"], cabeceras=cab)
    ultimo = v["data"][0]["created_at"][:10] if v["data"] else "sin vídeos"
    tipo = u.get("broadcaster_type") or "normal"
    print(f"{login:<20} {u['display_name']:<18} {tipo:<9} último: {ultimo:<10}  {u['description'][:50]!r}")
