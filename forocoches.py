#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import random
import sys
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from html import escape

# ========= CONFIGURACIÓN =========
START_PAGE = 1
END_PAGE = 41         # procesa hasta la 41
N_CICLOS = 5        # total de vueltas
OUTPUT_FILE = "hilos_forocoches.html"

MODO_LIMPIO = False   # True = borrar fichero al empezar, False = mantenerlo

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36"
HEADERS = {"User-Agent": USER_AGENT}

PAUSE_BETWEEN_REQ = (0.5, 2.0)
LONG_PAUSE_EVERY = 20
LONG_PAUSE_TIME = (5, 10)
# =================================

session = requests.Session()
session.headers.update(HEADERS)

def get_soup(url):
    r = session.get(url, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def iter_threads_from_list(list_page_url):
    """Devuelve (titulo, url) desde una página forumdisplay.php."""
    soup = get_soup(list_page_url)
    anchors = soup.select('a[id^="thread_title_"]')
    if not anchors:
        anchors = [a for a in soup.find_all("a", href=True)
                   if "showthread.php" in a["href"] and "t=" in a["href"]]
    seen = set()
    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        url = urljoin(list_page_url, href)
        if url in seen:
            continue
        seen.add(url)
        title = a.get_text(strip=True) or ""
        yield title, url

# --------- Carga de fichero existente (HTML o TSV legado) ---------

def cargar_existente(path):
    """
    Carga fichero previo, soportando:
      - HTML: filas <tr><td>NN</td><td><a href="URL">TÍTULO</a></td></tr>
      - TSV legado: NN<TAB>URL<TAB>TÍTULO o URL<TAB>TÍTULO
    Deduplica por TÍTULO y **asigna página 99** a todas las entradas cargadas,
    para que las nuevas detecciones con páginas reales (1..41) prevalezcan si son menores.
    """
    por_titulo = {}  # title -> {"page": int, "url": str}

    if not os.path.exists(path):
        return por_titulo

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return por_titulo

    # Intentar parsear como HTML
    try:
        soup = BeautifulSoup(content, "html.parser")
        rows = soup.select("table tbody tr")
        if rows:
            for tr in rows:
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    a = tds[1].find("a", href=True)
                    if not a:
                        continue
                    url = a["href"].strip()
                    title = a.get_text(strip=True)
                    # Asignar SIEMPRE página 99 al cargar
                    page = 99
                    prev = por_titulo.get(title)
                    if prev is None or page < prev["page"]:
                        por_titulo[title] = {"page": page, "url": url}
            if por_titulo:
                return por_titulo
    except Exception:
        pass

    # Fallback: intentar TSV legado
    for line in content.splitlines():
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            _, url, title = parts
        elif len(parts) == 2:
            url, title = parts
        else:
            continue
        url = url.strip()
        title = title.strip()
        page = 99  # Asignar SIEMPRE 99 al cargar desde TSV
        prev = por_titulo.get(title)
        if prev is None or page < prev["page"]:
            por_titulo[title] = {"page": page, "url": url}

    return por_titulo

# --------- Volcado HTML ---------

def volcar_html(path, por_titulo):
    """
    Escribe un HTML con una tabla (dos columnas):
      1) Nº de página (dos dígitos)
      2) Hipervínculo: texto = título, href = URL
    Ordenado por página ascendente y luego título.
    """
    rows = []
    for title, data in sorted(por_titulo.items(), key=lambda kv: (kv[1]["page"], kv[0].lower())):
        page = data["page"]
        url = data["url"]
        rows.append(
            f"<tr><td>{page:02d}</td><td><a href=\"{escape(url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{escape(title)}</a></td></tr>"
        )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Hilos ForoCoches</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Helvetica,Arial,sans-serif;margin:24px}}
  table{{border-collapse:collapse;width:100%;max-width:1200px}}
  th,td{{border:1px solid #ddd;padding:8px;vertical-align:top}}
  th{{background:#f6f6f6;text-align:left}}
  tr:nth-child(even){{background:#fafafa}}
  a{{text-decoration:none}}
  a:hover{{text-decoration:underline}}
  caption{{caption-side:top;font-weight:600;margin-bottom:8px}}
</style>
</head>
<body>
<table>
  <caption>Hilos capturados</caption>
  <thead>
    <tr><th>Página</th><th>Título</th></tr>
  </thead>
  <tbody>
    {"".join(rows)}
  </tbody>
</table>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

# --------- Principal ---------

def main():
    # Modo limpio
    if MODO_LIMPIO and os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

    # Cargar inventario existente (si hay), asignando página 99 a todos
    por_titulo = cargar_existente(OUTPUT_FILE)

    for ciclo in range(1, N_CICLOS + 1):
        nuevos_ciclo = 0

        for page in range(START_PAGE, END_PAGE + 1):
            list_url = f"https://forocoches.com/foro/forumdisplay.php?f=2&order=desc&page={page}"

            try:
                for title, thread_url in iter_threads_from_list(list_url):
                    prev = por_titulo.get(title)
                    if prev is None:
                        por_titulo[title] = {"page": page, "url": thread_url}
                        nuevos_ciclo += 1
                    else:
                        # Si ya existe ese título, prevalece el número de página INFERIOR
                        if page < prev["page"]:
                            por_titulo[title] = {"page": page, "url": thread_url}
            except Exception as e:
                sys.stdout.write(f"\r[ERROR:{e}]")
                sys.stdout.flush()

            # progreso en la misma línea (dos dígitos)
            sys.stdout.write(f"\rVUELTA {ciclo} de {N_CICLOS}: {page:02d}")
            sys.stdout.flush()

            # pausas
            time.sleep(random.uniform(*PAUSE_BETWEEN_REQ))
            if page % LONG_PAUSE_EVERY == 0:
                time.sleep(random.uniform(*LONG_PAUSE_TIME))

        # Actualizar HTML (consolidado y ordenado) y sobrescribir línea con resumen
        volcar_html(OUTPUT_FILE, por_titulo)
        sys.stdout.write(f"\r✔ Vuelta {ciclo} de {N_CICLOS} completada. {nuevos_ciclo} hilos nuevos añadidos.\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
