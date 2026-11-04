# Montar el servidor de EliteCraft

Se tarda unos 10 minutos. El script crea los roles, los canales, los permisos, los foros con sus etiquetas, los textos de bienvenida y normas, el AutoMod y las preguntas que aparecen al entrar.

## 1. Crea el servidor vacío
En Discord: **+** (abajo a la izquierda) → **Crear el mío** → **Para un club o comunidad**. Ponle nombre (por ejemplo *EliteCraft Hispano*) e icono.

## 2. Crea el bot que lo va a montar
1. Entra en <https://discord.com/developers/applications> → **New Application**.
2. Ponle **el mismo nombre que el servidor**. Los mensajes de bienvenida y normas quedarán firmados con ese nombre.
3. Ve a **Bot** → **Reset Token** → copia el token.
4. En esta carpeta, copia `.env.example` como `.env` y pega el token después de `DISCORD_TOKEN=`.

No hace falta activar ningún *intent*.

## 3. Invita el bot a tu servidor
En la misma aplicación: **OAuth2** → **URL Generator** → marca **bot** y, más abajo, **Administrator**. Abre la URL que aparece y elige tu servidor.

## 4. Ejecuta el script
Abre una terminal en esta carpeta. Primero, si quieres ver lo que va a hacer sin tocar nada:

```bash
python montar_servidor.py --simular
```

Y para montarlo de verdad:

```bash
python montar_servidor.py
```

Te preguntará si borra los canales que Discord crea por defecto: di que sí. Al final te da una invitación que no caduca.

Si se corta a medias, vuelve a ejecutarlo: lo que ya existe se respeta y solo se crea lo que falta. Si el servidor ya tiene muchos canales o miembros, el script se para para no estropear nada.

## 5. Últimos pasos a mano
1. **Dale tu rol:** clic derecho en tu nombre → Roles → **Admin**.
2. **Revisa las preguntas de entrada:** Ajustes del servidor → **Incorporación**. Ahí puedes verlas como las verá un miembro nuevo.
3. **Avisador de directos:** mira la sección de abajo.
4. **El bot montador:** mientras sigan anunciando participantes, déjalo en el servidor, porque lo necesitas para añadirlos. Cuando ya estén todos, expúlsalo y pulsa **Reset Token** en el portal de desarrolladores para que el token deje de valer. Si más adelante te hace falta, lo invitas otra vez con un token nuevo. Mientras siga dentro, no compartas el `.env` con nadie: quien tenga ese token controla el servidor.

## Avisador de directos
`avisador.py` publica en `#en-directo` un aviso cuando empieza un participante y menciona a su rol (`Directo · Nombre`). Mientras dura el directo actualiza el título y el juego, y cuando termina edita el aviso para que ponga cuánto duró.

- **Todos los directos** recibe un solo aviso por tanda: el primero que empieza tras 6 horas sin avisarle. Así no le llegan 40 notificaciones seguidas al arrancar un evento.
- **Panel:** el último mensaje del canal es siempre la lista de quién está en directo ahora, con enlace y desde cuándo. Se actualiza solo. Funciona gratis, sin límite de streamers y sin tener el PC encendido, porque lo ejecuta GitHub cada 5 minutos.

Por defecto avisa de los directos de **Minecraft** y de cualquier directo que diga EliteCraft en el título o en la categoría (por si Twitch le crea una categoría propia). Para cambiarlo, crea en GitHub una variable `FILTRO` con el valor `elitecraft` (solo EliteCraft) o `todo`.

Qué necesita (todo va en `.env` para probar en local y en los secretos del repositorio de GitHub):
- `DISCORD_WEBHOOK_EN_DIRECTO`: en Discord, editar `#en-directo` → **Integraciones** → **Webhooks** → **Nuevo webhook**. Ponle de nombre *En directo* y copia su URL.
- `TWITCH_CLIENT_ID` y `TWITCH_CLIENT_SECRET`: en <https://dev.twitch.tv/console> → **Registrar tu aplicación**. Twitch pide tener activada la verificación en dos pasos.
- `roles_discord.json`: lo crea `montar_servidor.py` al ejecutarlo.

Para probar en local:
- `python avisador.py --prueba` manda un aviso de ejemplo a `#en-directo`.
- `python avisador.py` hace una pasada real.

## Añadir participantes
Cuando confirmen a alguien de EliteCraft 4, añádelo a `streamers.txt` (con su canal de Twitch si no se llama igual) y vuelve a ejecutar `montar_servidor.py`. Él solo:
- crea su rol `Directo · Nombre` y lo pone en Canales y roles, en su grupo alfabético;
- le abre su hilo en `🧵・hilos-de-directos`;
- lo añade a la lista de `👥・participantes`;
- lo **anuncia en `📰・noticias-elitecraft`**, mencionando a quien tiene el rol Noticias de EliteCraft. Si añades varios de golpe, salen en un solo anuncio;
- actualiza `roles_discord.json`.

Después sube a GitHub `streamers.txt` y `roles_discord.json` para que el avisador empiece a vigilarlo.

Quitar a alguien de la lista no borra su rol ni su hilo: eso hazlo a mano.

## Comentar directos
`🍿・comentando-directos` es un canal de texto normal para comentar los directos en general. Además, `🧵・hilos-de-directos` es un foro con un hilo fijo por participante: los miembros escriben en los hilos pero no pueden abrir hilos nuevos, así no se desordena. Como el foro se ordena por actividad, los hilos de quien está en directo suben solos. Cada aviso de `🔴・en-directo` enlaza al hilo de su participante.

## Eventos de Discord
Para el estreno de la temporada o un evento que anuncien, crea un evento de Discord. Sale arriba del servidor con cuenta atrás, y quien pulse «Me interesa» recibe un aviso cuando empieza.

```bash
python crear_evento.py "Estreno de EliteCraft 4" "2026-12-01 18:00" --avisar
```

La hora es la de España. Opciones: `--horas 2` (duración, por defecto 3), `--lugar "Twitch"`, `--descripcion "..."`, `--avisar` (lo anuncia también en `📰・noticias-elitecraft`) y `--semanal` (se repite cada semana, para los Días de Élite de los martes). También se puede crear a mano desde **Eventos**, arriba del todo en la lista de canales.

## Noticias y tuits oficiales
X cobra por leer tuits desde su API, así que no hay forma gratis y fiable de traerlos solos. Los anuncios oficiales se comparten a mano en `📰・noticias-elitecraft`: son pocos, y un moderador puede añadir contexto. Si quieres intentarlo en automático, el plan gratis de rss.app puede mandar los tuits de @EliteCraftSMP a ese canal por un webhook, aunque con retraso y con límites.

Al publicar en `📰・noticias-elitecraft` (es un canal de anuncios), pulsa **Publicar** para que llegue también a los servidores que lo sigan.

## Cambiar los textos
Los textos de bienvenida, normas y la guía de la temporada (`📖・guía`) están en `textos/`. Cuando salga información nueva (fecha de salida, eventos…), añádela a `textos/guía.md` y vuelve a ejecutar el script. Para cambiarlos, edita el archivo y vuelve a ejecutar el script: actualiza el mensaje que ya hay, sin borrarlo. Desde Discord no se pueden editar, porque los publica el bot. Los emojis de los canales están en `EMOJIS`, dentro de `montar_servidor.py`.

## Ojo al volver a ejecutarlo
Las preguntas de entrada se vuelven a crear desde cero cada vez. Si las has retocado a mano en Discord, esos cambios se pierden.
