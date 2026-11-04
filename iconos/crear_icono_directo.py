"""Genera iconos/en-directo.png: el icono del webhook de avisos de directo."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

TAM, ESCALA = 512, 4          # se dibuja a 4x y se reduce, para bordes suaves
T = TAM * ESCALA
MORADO_CLARO, MORADO_OSCURO = (157, 92, 255), (100, 45, 214)
BLANCO, ROJO = (255, 255, 255), (255, 72, 88)

# Fondo: degradado diagonal morado (el mismo tono que la franja de los avisos)
fondo = Image.new("RGB", (T, T))
px = fondo.load()
for y in range(T):
    for x in range(0, T, 1):
        t = (x + y) / (2 * T)
        px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(MORADO_CLARO, MORADO_OSCURO))

capa = Image.new("RGBA", (T, T), (0, 0, 0, 0))
d = ImageDraw.Draw(capa)
c = T // 2
grosor = int(T * 0.045)

# Ondas de emisión a cada lado
for radio, alfa in ((0.25, 255), (0.36, 200)):
    r = int(T * radio)
    caja = (c - r, c - r, c + r, c + r)
    d.arc(caja, 145, 215, fill=BLANCO + (alfa,), width=grosor)   # izquierda
    d.arc(caja, -35, 35, fill=BLANCO + (alfa,), width=grosor)    # derecha

# Punto rojo central con halo
halo = Image.new("RGBA", (T, T), (0, 0, 0, 0))
rh = int(T * 0.15)
ImageDraw.Draw(halo).ellipse((c - rh, c - rh, c + rh, c + rh), fill=ROJO + (150,))
halo = halo.filter(ImageFilter.GaussianBlur(T * 0.03))
rp = int(T * 0.105)
d.ellipse((c - rp, c - rp, c + rp, c + rp), fill=ROJO + (255,), outline=BLANCO + (255,), width=int(T * 0.018))

final = fondo.convert("RGBA")
final.alpha_composite(halo)
final.alpha_composite(capa)
final = final.resize((TAM, TAM), Image.LANCZOS)
salida = Path(__file__).with_name("en-directo.png")
final.save(salida)
print(f"Guardado: {salida}")
