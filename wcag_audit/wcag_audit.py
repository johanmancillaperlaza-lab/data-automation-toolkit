"""Find Shopify stores (Serper), run Google PageSpeed Insights accessibility audits, map failures to WCAG criteria with fix guidance and write CSV and HTML reports."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import datetime
import time
import requests
import csv
import os
import re
from urllib.parse import urlparse
SERPER_API_KEYS = [k.strip() for k in os.getenv('SERPER_API_KEYS', 'YOUR_SERPER_API_KEY').split(',') if k.strip()]
current_key_index = 0
SERPER_URL = 'https://google.serper.dev/search'
PAGESPEED_API_KEY = os.getenv('PAGESPEED_API_KEY', 'YOUR_PAGESPEED_API_KEY')
PAGESPEED_URL = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
NICHOS_OBJETIVO = ['skincare', 'fitness', 'fashion', 'home']
SUBNICHOS = {'vegan': ['vegan skincare', 'vegan protein', 'vegan snacks', 'vegan supplements', 'vegan clothing', 'vegan candles', 'vegan beauty'], 'pet': ['pet toys', 'pet supplements', 'dog accessories', 'cat accessories', 'pet grooming', 'dog treats', 'pet food'], 'organic': ['organic skincare', 'organic snacks', 'organic supplements', 'organic baby products', 'organic tea', 'organic coffee', 'organic clothing'], 'skincare': ['natural skincare', 'clean beauty', 'korean skincare', 'anti-aging skincare', 'acne skincare', "men's skincare"], 'fitness': ['fitness supplements', 'protein powder', 'pre workout supplements', 'fitness apparel', 'yoga gear', 'home gym equipment'], 'fashion': ['sustainable fashion', 'ethical clothing', 'slow fashion', 'eco friendly apparel', 'sustainable activewear'], 'home': ['eco friendly home goods', 'sustainable home decor', 'zero waste home', 'eco cleaning products', 'sustainable kitchenware']}
PLANTILLAS_QUERY = ['{nicho} online store shopify', '{nicho} shop powered by shopify', '{nicho} store shopify -site:shopify.com', 'buy {nicho} online shopify']
PAGINAS_POR_QUERY = 2
AUDITS_CRITICOS_PRIORITARIOS = ['button-name', 'aria-input-field-name', 'label', 'color-contrast', 'link-name', 'image-alt', 'form-field-multiple-labels']
WCAG_MAPPING = {'color-contrast': ('1.4.3 Contraste minimo', 'AA'), 'image-alt': ('1.1.1 Contenido no textual', 'A'), 'input-image-alt': ('1.1.1 Contenido no textual', 'A'), 'image-redundant-alt': ('1.1.1 Contenido no textual', 'A'), 'button-name': ('4.1.2 Nombre, funcion, valor', 'A'), 'link-name': ('2.4.4 Proposito del enlace (en contexto)', 'A'), 'select-name': ('4.1.2 Nombre, funcion, valor', 'A'), 'frame-title': ('4.1.2 Nombre, funcion, valor', 'A'), 'label': ('1.3.1 Informacion y relaciones', 'A'), 'form-field-multiple-labels': ('3.3.2 Etiquetas o instrucciones', 'A'), 'aria-input-field-name': ('4.1.2 Nombre, funcion, valor', 'A'), 'aria-roles': ('4.1.2 Nombre, funcion, valor', 'A'), 'aria-valid-attr': ('4.1.2 Nombre, funcion, valor', 'A'), 'aria-valid-attr-value': ('4.1.2 Nombre, funcion, valor', 'A'), 'duplicate-id-aria': ('4.1.1 Procesamiento', 'A'), 'html-has-lang': ('3.1.1 Idioma de la pagina', 'A'), 'html-lang-valid': ('3.1.1 Idioma de la pagina', 'A'), 'document-title': ('2.4.2 Pagina con titulo', 'A'), 'target-size': ('2.5.8 Tamano del objetivo (minimo)', 'AA'), 'tap-targets': ('2.5.8 Tamano del objetivo (minimo)', 'AA'), 'meta-viewport': ('1.4.4 Cambiar tamano del texto', 'AA'), 'heading-order': ('1.3.1 Informacion y relaciones', 'A'), 'aria-required-attr': ('4.1.2 Nombre, funcion, valor', 'A'), 'aria-allowed-attr': ('4.1.2 Nombre, funcion, valor', 'A'), 'aria-required-children': ('1.3.1 Informacion y relaciones', 'A'), 'aria-required-parent': ('1.3.1 Informacion y relaciones', 'A'), 'aria-hidden-focus': ('4.1.2 Nombre, funcion, valor', 'A'), 'aria-command-name': ('4.1.2 Nombre, funcion, valor', 'A'), 'accesskeys': ('2.1.1 Teclado', 'A'), 'bypass': ('2.4.1 Evitar bloques', 'A'), 'landmark-one-main': ('1.3.1 Informacion y relaciones', 'A'), 'list': ('1.3.1 Informacion y relaciones', 'A'), 'listitem': ('1.3.1 Informacion y relaciones', 'A'), 'definition-list': ('1.3.1 Informacion y relaciones', 'A'), 'dlitem': ('1.3.1 Informacion y relaciones', 'A')}
FIX_GUIDANCE = {'color-contrast': 'Subir el contraste del texto contra el fondo hasta cumplir la razon minima de 4.5:1 (texto normal) o 3:1 (texto grande).', 'image-alt': 'Agregar un atributo alt descriptivo a cada imagen que comunique informacion.', 'input-image-alt': 'Agregar alt descriptivo a los inputs de tipo imagen (ej. boton de busqueda con icono).', 'image-redundant-alt': "Quitar el alt si la imagen es puramente decorativa (alt=''), o hacerlo descriptivo si aporta informacion.", 'button-name': 'Agregar aria-label o texto visible al boton para que un lector de pantalla anuncie su funcion.', 'link-name': "Agregar texto descriptivo o aria-label al enlace, evitar 'click aqui' sin contexto.", 'select-name': 'Asociar un label visible o aria-label al campo select.', 'frame-title': 'Agregar atributo title al iframe describiendo su contenido.', 'label': 'Asociar cada campo de formulario a su label con el atributo for/id.', 'form-field-multiple-labels': 'Dejar una sola etiqueta clara por campo, eliminar labels duplicados o en conflicto.', 'aria-input-field-name': 'Agregar aria-label o aria-labelledby al campo para que tenga nombre accesible.', 'aria-roles': 'Corregir el valor del atributo role para que coincida con un rol ARIA valido.', 'aria-valid-attr': 'Revisar y corregir los atributos aria-* mal escritos o no reconocidos.', 'aria-valid-attr-value': 'Corregir el valor asignado al atributo aria-*, debe coincidir con los valores permitidos.', 'duplicate-id-aria': 'Asegurar que cada id referenciado por atributos aria sea unico en la pagina.', 'html-has-lang': "Agregar el atributo lang al tag <html> (ej. lang='en').", 'html-lang-valid': "Corregir el valor del atributo lang a un codigo de idioma valido (ej. 'en', 'es').", 'document-title': 'Agregar un <title> descriptivo y unico a la pagina.', 'target-size': 'Aumentar el tamano o separacion de botones/campos tactiles a minimo 24x24px.', 'tap-targets': 'Aumentar el tamano o separacion de los elementos tactiles para evitar toques accidentales.', 'meta-viewport': "Quitar 'user-scalable=no' o 'maximum-scale' restrictivo del meta viewport, debe permitirse zoom.", 'heading-order': 'Corregir el orden de los encabezados para que bajen de forma secuencial (h1, luego h2, no saltar de h2 a h4).', 'aria-required-attr': 'Agregar los atributos aria-* obligatorios que ese rol ARIA necesita.', 'aria-allowed-attr': 'Quitar el atributo aria-* que no esta permitido para ese elemento/rol.', 'aria-required-children': 'Agregar los elementos hijos que ese rol ARIA requiere dentro de el.', 'aria-required-parent': 'Envolver el elemento en el contenedor padre que ese rol ARIA requiere.', 'aria-hidden-focus': 'Quitar aria-hidden de un elemento que todavia puede recibir foco por teclado, o quitarle el foco.', 'aria-command-name': 'Agregar nombre accesible (texto, aria-label o aria-labelledby) al boton, enlace o menu.', 'accesskeys': 'Asegurar que cada atajo de teclado (accesskey) sea unico en la pagina.', 'bypass': "Agregar un enlace de 'saltar al contenido' al inicio de la pagina.", 'landmark-one-main': 'Agregar una sola etiqueta <main> que envuelva el contenido principal.', 'list': 'Asegurar que los elementos <ul>/<ol> solo contengan <li> como hijos directos.', 'listitem': 'Asegurar que cada <li> este dentro de un <ul> o <ol>.', 'definition-list': 'Asegurar que <dl> solo contenga grupos de <dt> y <dd> en el orden correcto.', 'dlitem': 'Asegurar que <dt> y <dd> esten dentro de un <dl>.'}
DEFAULT_FIX_GUIDANCE = 'Revisar contra la documentacion oficial de WCAG 2.1/2.2 para ese criterio especifico.'
USUARIO_AFECTADO = {'color-contrast': 'alguien con baja vision', 'image-alt': 'alguien usando lector de pantalla', 'input-image-alt': 'alguien usando lector de pantalla', 'image-redundant-alt': 'alguien usando lector de pantalla', 'button-name': 'alguien usando lector de pantalla', 'link-name': 'alguien usando lector de pantalla', 'select-name': 'alguien usando lector de pantalla', 'frame-title': 'alguien usando lector de pantalla', 'label': 'alguien usando lector de pantalla', 'form-field-multiple-labels': 'alguien usando lector de pantalla', 'aria-input-field-name': 'alguien usando lector de pantalla', 'aria-roles': 'alguien usando lector de pantalla', 'aria-valid-attr': 'alguien usando lector de pantalla', 'aria-valid-attr-value': 'alguien usando lector de pantalla', 'duplicate-id-aria': 'alguien usando lector de pantalla', 'html-has-lang': 'alguien usando lector de pantalla', 'html-lang-valid': 'alguien usando lector de pantalla', 'document-title': 'alguien usando lector de pantalla', 'target-size': 'alguien con movilidad reducida usando el celular', 'tap-targets': 'alguien con movilidad reducida usando el celular', 'meta-viewport': 'alguien con baja vision que necesita hacer zoom'}
DEFAULT_USUARIO_AFECTADO = 'alguien usando tecnologia de asistencia'

def obtener_usuario_afectado(audit_id):
    return USUARIO_AFECTADO.get(audit_id, DEFAULT_USUARIO_AFECTADO)
THUM_IO_BASE = 'https://image.thum.io/get/width/1200/'

def generar_url_captura(url_pagina):
    return THUM_IO_BASE + url_pagina

def obtener_criterio_wcag(audit_id):
    return WCAG_MAPPING.get(audit_id, ('No mapeado a un criterio especifico', ''))

def obtener_guia_arreglo(audit_id):
    return FIX_GUIDANCE.get(audit_id, DEFAULT_FIX_GUIDANCE)
DOMINIOS_TIENDA_DEMO = ('.myshopify.com',)
DOMINIOS_IGNORAR = ('shopify.com', 'example.com', 'sentry.io', 'google.com', 'w3.org')
DOMINIOS_MARKETPLACE_EXCLUIR = ('apps.shopify.com', 'themes.shopify.com', 'elements.envato.com', 'themeforest.net', 'pipiads.com', 'eachspy.com', 'cro.media', 'getclipara.com', 'gempages.net', 'omnisend.com', 'omnithemes.com', 'foxecom.com', 'shopplaza.io', 'wemakewebsites.com', 'team90degree.com', 'greendropship.com', 'koala-apps.io', 'suttoncommerce.co.uk', 'easyappsecom.com', 'webinopoly.com', 'ecomency.com', 'ecomchief.com', 'inspiredtheme.com', 'halothemes.net', 'tyack.com.au')
PATRONES_URL_EXCLUIR = ('/blog', '/work/', '/portfolio', '/case-study', '/case-studies', '/news/', '/press/', '/about')
CORREOS_PLACEHOLDER = ('your', 'email', 'name', 'user', 'johndoe', 'janedoe', 'youremail', 'example', 'test', 'sample', 'username', 'yourname')
REGEX_EMAIL = '[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.(?:com|co|net|org|io|shop|store|info|biz|me)(?:\\.(?:au|uk|ca|nz|za|mx|br))?\\b'
MAX_TIENDAS = 130
CHECKPOINT_INTERVAL = 10
TIMEOUT_REQUEST = 12
CSV_FILE = 'motor2_wcag_' + datetime.date.today().isoformat() + '.csv'
OUTPUT_HTML = 'motor2_wcag_' + datetime.date.today().isoformat() + '.html'
fecha_hoy = datetime.date.today()
HEADERS_NAVEGADOR = {'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36'}

def get_current_key():
    global current_key_index
    return SERPER_API_KEYS[current_key_index % len(SERPER_API_KEYS)]

def rotate_key():
    global current_key_index
    current_key_index += 1
    print('   Rotando a key #' + str(current_key_index % len(SERPER_API_KEYS) + 1), flush=True)

def buscar_serper(query, num_reintentos=3, page=1):
    for intento in range(num_reintentos):
        headers = {'X-API-KEY': get_current_key(), 'Content-Type': 'application/json'}
        payload = {'q': query, 'num': 30, 'page': page}
        try:
            resp = requests.post(SERPER_URL, headers=headers, json=payload, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in [401, 403, 429]:
                rotate_key()
                time.sleep(2)
                continue
            else:
                time.sleep(2 ** intento)
        except requests.exceptions.RequestException:
            time.sleep(2 ** intento)
    return None

def es_dominio_marketplace(link):
    dominio = urlparse(link).netloc.lower()
    return any((dominio == d or dominio.endswith('.' + d) for d in DOMINIOS_MARKETPLACE_EXCLUIR))

def es_ruta_excluida(link):
    ruta = urlparse(link).path.lower()
    return any((patron in ruta for patron in PATRONES_URL_EXCLUIR))

def es_tienda_shopify(html_texto):
    senales = ['cdn.shopify.com', 'Shopify.theme', 'myshopify.com', 'shopify-section']
    html_l = html_texto.lower()
    return any((s.lower() in html_l for s in senales))

def menciona_el_nicho(html_texto, nicho):
    return nicho.lower() in html_texto.lower()

def verificar_products_json(link):
    try:
        raiz = urlparse(link)
        url_products = raiz.scheme + '://' + raiz.netloc + '/products.json'
        resp = requests.get(url_products, headers=HEADERS_NAVEGADOR, timeout=TIMEOUT_REQUEST)
        if resp.status_code != 200:
            return (False, None)
        data = resp.json()
        productos = data.get('products', [])
        if len(productos) == 0:
            return (False, None)
        handle = productos[0].get('handle')
        url_producto = raiz.scheme + '://' + raiz.netloc + '/products/' + handle if handle else None
        return (True, url_producto)
    except Exception:
        return (False, None)

def es_email_valido(email):
    if not email:
        return False
    partes = email.split('@')
    if len(partes) != 2:
        return False
    if partes[0].lower() in CORREOS_PLACEHOLDER:
        return False
    return True

def extraer_email_footer(html_texto):
    candidatos = re.findall(REGEX_EMAIL, html_texto)
    prefijos_utiles = ('hello', 'contact', 'support', 'info', 'hi', 'help', 'sales', 'team')
    for c in candidatos:
        c_l = c.lower()
        dominio = c_l.split('@')[-1]
        if any((d in dominio for d in DOMINIOS_IGNORAR)):
            continue
        if not es_email_valido(c):
            continue
        prefijo = c_l.split('@')[0]
        if any((prefijo.startswith(p) for p in prefijos_utiles)):
            return c
    for c in candidatos:
        dominio = c.lower().split('@')[-1]
        if not any((d in dominio for d in DOMINIOS_IGNORAR)) and es_email_valido(c):
            return c
    return None

def consultar_wcag(url, pagina='', dispositivo='mobile', num_reintentos=2):
    params = {'url': url, 'strategy': dispositivo, 'category': ['accessibility', 'performance', 'seo', 'best-practices']}
    if PAGESPEED_API_KEY:
        params['key'] = PAGESPEED_API_KEY
    for intento in range(num_reintentos):
        try:
            resp = requests.get(PAGESPEED_URL, params=params, timeout=60)
            if resp.status_code != 200:
                if intento < num_reintentos - 1:
                    time.sleep(3)
                    continue
                return (None, [], {})
            data = resp.json()
            categorias = data.get('lighthouseResult', {}).get('categories', {})

            def score_de(cat_id):
                s = categorias.get(cat_id, {}).get('score')
                return int(s * 100) if s is not None else None
            score_100 = score_de('accessibility')
            otros_scores = {'performance': score_de('performance'), 'seo': score_de('seo'), 'best-practices': score_de('best-practices')}
            ids_accesibilidad = set((ref.get('id') for ref in categorias.get('accessibility', {}).get('auditRefs', [])))
            audits = data.get('lighthouseResult', {}).get('audits', {})
            violaciones = []
            for audit_id, audit in audits.items():
                if audit_id not in ids_accesibilidad:
                    continue
                if audit.get('score') == 0:
                    items = audit.get('details', {}).get('items', [])
                    num_elementos = len(items)
                    if num_elementos == 0:
                        continue
                    snippet = ''
                    if items:
                        nodo = items[0].get('node', {})
                        snippet = (nodo.get('snippet') or '')[:200]
                    contraste_info = ''
                    if audit_id == 'color-contrast' and items:
                        item0 = items[0]
                        ratio = item0.get('contrastRatio') or item0.get('ratio')
                        fg = item0.get('fgColor') or item0.get('foreground')
                        bg = item0.get('bgColor') or item0.get('background')
                        if ratio:
                            contraste_info = 'ratio=' + str(ratio)
                            if fg:
                                contraste_info += ' fg=' + str(fg)
                            if bg:
                                contraste_info += ' bg=' + str(bg)
                    violaciones.append((audit_id, audit.get('title', audit_id), audit.get('description', '')[:150], num_elementos, pagina, dispositivo, snippet, contraste_info))
            violaciones.sort(key=lambda v: (v[0] not in AUDITS_CRITICOS_PRIORITARIOS, -v[3]))
            return (score_100, violaciones, otros_scores)
        except requests.exceptions.RequestException:
            if intento < num_reintentos - 1:
                time.sleep(3)
                continue
            return (None, [], {})
    return (None, [], {})

def score_preliminar(wcag_score, num_violaciones_criticas, tiene_email):
    s = 0
    if wcag_score is not None:
        if wcag_score < 50:
            s += 4
        elif wcag_score < 70:
            s += 2
    if num_violaciones_criticas >= 3:
        s += 3
    elif num_violaciones_criticas >= 1:
        s += 1
    if tiene_email:
        s += 3
    return min(s, 10)

def save_leads_to_csv(leads, filename):
    fieldnames = ['tienda_url', 'nicho', 'email_contacto', 'wcag_score_home_mobile', 'wcag_score_home_desktop', 'wcag_score_producto_mobile', 'wcag_score_producto_desktop', 'wcag_score_carrito_mobile', 'wcag_score_carrito_desktop', 'num_violaciones_criticas', 'criterios_wcag_distintos', 'violaciones_detalle', 'captura_home', 'captura_producto', 'captura_carrito', 'performance_score_home_mobile', 'seo_score_home_mobile', 'best_practices_score_home_mobile', 'score_preliminar', 'fecha_extraccion']
    modo = 'a' if os.path.exists(filename) and os.path.getsize(filename) > 0 else 'w'
    with open(filename, modo, newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if modo == 'w':
            w.writeheader()
        w.writerows(leads)
print('=' * 60)
print('WCAG accessibility audit')
print('Nichos: ' + ', '.join(NICHOS_OBJETIVO))
print('=' * 60)
VISTOS_FILE = 'motor2_vistos.txt'
vistos_previos = set()
if os.path.exists(VISTOS_FILE):
    with open(VISTOS_FILE, 'r', encoding='utf-8') as f:
        vistos_previos = set((line.strip() for line in f if line.strip()))
    print(str(len(vistos_previos)) + ' dominios ya vistos en corridas anteriores (se saltan).')
todos = []
seen_urls = set()
dominios_ya_capturados = set(vistos_previos)
nuevos_este_run = set()
leads_since_save = 0
queries = []
nicho_por_query = {}
for nicho in NICHOS_OBJETIVO:
    terminos = [nicho] + SUBNICHOS.get(nicho, [])
    for termino in terminos:
        for plantilla in PLANTILLAS_QUERY:
            q = plantilla.format(nicho=termino)
            queries.append(q)
            nicho_por_query[q] = nicho
print(str(len(queries)) + ' queries a ejecutar (x' + str(PAGINAS_POR_QUERY) + ' paginas c/u).\n')
for idx, query in enumerate(queries):
    if len(todos) >= MAX_TIENDAS:
        break
    nicho_actual = nicho_por_query.get(query, '')
    print('[' + str(idx + 1) + '/' + str(len(queries)) + '] ' + query, flush=True)
    resultados = []
    for pagina in range(1, PAGINAS_POR_QUERY + 1):
        data = buscar_serper(query, page=pagina)
        if not data:
            print('   pagina ' + str(pagina) + ': sin resultados / fallo de API', flush=True)
            continue
        resultados.extend(data.get('organic', []))
        time.sleep(0.5)
    for r in resultados:
        if len(todos) >= MAX_TIENDAS:
            break
        link = r.get('link', '')
        if not link or link in seen_urls:
            continue
        seen_urls.add(link)
        if es_dominio_marketplace(link):
            print('   [descartado] dominio de agencia/marketplace conocido: ' + link, flush=True)
            continue
        if es_ruta_excluida(link):
            print('   [descartado] ruta de blog/portafolio, no es la tienda: ' + link, flush=True)
            continue
        try:
            resp = requests.get(link, headers=HEADERS_NAVEGADOR, timeout=TIMEOUT_REQUEST)
            html_texto = resp.text
        except requests.exceptions.RequestException:
            continue
        if not es_tienda_shopify(html_texto):
            continue
        dominio_tienda = urlparse(link).netloc.lower().replace('www.', '')
        if dominio_tienda in dominios_ya_capturados:
            continue
        if any((dominio_tienda.endswith(d) for d in DOMINIOS_TIENDA_DEMO)):
            print('   [descartado] tienda demo/plantilla: ' + link, flush=True)
            continue
        if not menciona_el_nicho(html_texto, nicho_actual):
            print('   [descartado] coincidencia irrelevante de nicho: ' + link, flush=True)
            continue
        tiene_productos, url_producto = verificar_products_json(link)
        if not tiene_productos:
            print('   [descartado] /products.json vacio, no es tienda real: ' + link, flush=True)
            continue
        email = extraer_email_footer(html_texto)
        if not email:
            print('   [descartado] sin correo bundleado: ' + link, flush=True)
            continue
        raiz_link = urlparse(link)
        cart_url = raiz_link.scheme + '://' + raiz_link.netloc + '/cart'
        paginas_a_auditar = [('home', link)]
        if url_producto:
            paginas_a_auditar.append(('producto', url_producto))
        paginas_a_auditar.append(('carrito', cart_url))
        todas_violaciones = []
        scores_por_pagina = {}
        otros_scores_home_mobile = {}
        for nombre_pagina, url_pagina in paginas_a_auditar:
            for dispositivo in ('mobile', 'desktop'):
                score_pd, viol_pd, otros_pd = consultar_wcag(url_pagina, pagina=nombre_pagina, dispositivo=dispositivo)
                if nombre_pagina == 'home' and dispositivo == 'mobile':
                    wcag_score_home = score_pd
                    otros_scores_home_mobile = otros_pd
                scores_por_pagina[nombre_pagina, dispositivo] = score_pd
                todas_violaciones.extend(viol_pd)
                time.sleep(0.8)
        print('   [debug] wcag_score_home=' + str(wcag_score_home) + ' | violaciones_totales=' + str(len(todas_violaciones)) + ' (home+producto+carrito, mobile+desktop)', flush=True)
        if len(todas_violaciones) < 1:
            print('   [descartado] sin violaciones detectadas: ' + link, flush=True)
            continue
        criticas = todas_violaciones
        score = score_preliminar(wcag_score_home, len(criticas), bool(email))
        detalle_items = []
        criterios_vistos = set()
        for audit_id, titulo, _, num, pagina_v, dispositivo_v, snippet, contraste_info in criticas[:8]:
            criterio, nivel = obtener_criterio_wcag(audit_id)
            guia = obtener_guia_arreglo(audit_id)
            afectado = obtener_usuario_afectado(audit_id)
            criterios_vistos.add(criterio)
            bloquea = 'BLOQUEA COMPRA' if audit_id in AUDITS_CRITICOS_PRIORITARIOS else 'cosmetico'
            cita = ' | Elemento: ' + snippet if snippet else ''
            contraste_txt = ' | Contraste real: ' + contraste_info if contraste_info else ''
            detalle_items.append(titulo + ' (' + str(num) + ' elementos, ' + pagina_v + '/' + dispositivo_v + ') | WCAG ' + criterio + (' nivel ' + nivel if nivel else '') + ' | ' + bloquea + ' | Afecta a: ' + afectado + ' | Arreglo: ' + guia + cita + contraste_txt)
        criterios_totales = set((obtener_criterio_wcag(v[0])[0] for v in todas_violaciones))
        lead = {'tienda_url': link, 'nicho': nicho_actual, 'email_contacto': email, 'wcag_score_home_mobile': scores_por_pagina.get(('home', 'mobile'), 'no disponible'), 'wcag_score_home_desktop': scores_por_pagina.get(('home', 'desktop'), 'no disponible'), 'wcag_score_producto_mobile': scores_por_pagina.get(('producto', 'mobile'), 'no disponible'), 'wcag_score_producto_desktop': scores_por_pagina.get(('producto', 'desktop'), 'no disponible'), 'wcag_score_carrito_mobile': scores_por_pagina.get(('carrito', 'mobile'), 'no disponible'), 'wcag_score_carrito_desktop': scores_por_pagina.get(('carrito', 'desktop'), 'no disponible'), 'num_violaciones_criticas': len(criticas), 'criterios_wcag_distintos': len(criterios_totales), 'violaciones_detalle': ' || '.join(detalle_items), 'captura_home': generar_url_captura(link), 'captura_producto': generar_url_captura(url_producto) if url_producto else '', 'captura_carrito': generar_url_captura(cart_url), 'performance_score_home_mobile': otros_scores_home_mobile.get('performance', 'no disponible'), 'seo_score_home_mobile': otros_scores_home_mobile.get('seo', 'no disponible'), 'best_practices_score_home_mobile': otros_scores_home_mobile.get('best-practices', 'no disponible'), 'score_preliminar': score, 'fecha_extraccion': str(fecha_hoy)}
        todos.append(lead)
        dominios_ya_capturados.add(dominio_tienda)
        nuevos_este_run.add(dominio_tienda)
        leads_since_save += 1
        print('   [OK] ' + link + ' | score home mobile:' + str(wcag_score_home) + ' | ' + str(len(criticas)) + ' violaciones criticas | ' + email, flush=True)
        time.sleep(1)
    if leads_since_save >= CHECKPOINT_INTERVAL:
        save_leads_to_csv(todos[-leads_since_save:], CSV_FILE)
        leads_since_save = 0
        print('   CHECKPOINT guardado.', flush=True)
    time.sleep(1.5)
if todos:
    conteo_email = {}
    for l in todos:
        conteo_email[l['email_contacto']] = conteo_email.get(l['email_contacto'], 0) + 1
    antes = len(todos)
    todos = [l for l in todos if conteo_email[l['email_contacto']] == 1]
    descartados_agencia = antes - len(todos)
    if descartados_agencia:
        print('\n[filtro final] ' + str(descartados_agencia) + ' leads descartados por correo compartido entre varias tiendas (agencia/tema).')
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(todos[0].keys()) if todos else [])
        w.writeheader()
        w.writerows(todos)
    print('\nCSV guardado: ' + CSV_FILE)
    with open(VISTOS_FILE, 'a', encoding='utf-8') as f:
        for d in nuevos_este_run:
            f.write(d + '\n')
    print('Vistos actualizados: ' + VISTOS_FILE + ' (' + str(len(nuevos_este_run)) + ' dominios nuevos agregados)')
    todos_ordenados = sorted(todos, key=lambda x: x['score_preliminar'], reverse=True)
    total = len(todos_ordenados)
    html = '<!DOCTYPE html>\n<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Motor 2 - WCAG Accessibility</title>\n<style>\nbody{font-family:Arial;background:#0a0e1a;color:#e0e0e0;padding:15px;margin:0}\nh2{color:#58a6ff;margin-bottom:5px}\n.stats{color:#8b949e;margin-bottom:12px;font-size:13px}\ntable{width:100%;border-collapse:collapse;background:#1a1f2e;font-size:12px}\nth{background:#0f1420;color:#58a6ff;padding:8px;text-align:left;position:sticky;top:0}\ntd{padding:7px 8px;border-bottom:1px solid #21262d;vertical-align:top}\na{color:#58a6ff;text-decoration:none}\n.sh{color:#3fb950;font-weight:bold} .sm{color:#d29922} .sl{color:#8b949e}\n.nota{background:#1a1f2e;border-left:3px solid #f0a500;padding:10px;margin-bottom:15px;font-size:12px;color:#c9d1d9}\n</style></head><body>\n<h2>Motor 2 - Tiendas con violaciones WCAG criticas</h2>\n<div class="nota">Preliminary score based on WCAG score, critical violations and confirmed email.</div>\n<div class="stats">Total: ' + str(total) + ' | ' + str(fecha_hoy) + '</div>\n<table><thead><tr>\n<th>#</th><th>Tienda</th><th>Nicho</th><th>Correo</th><th>Score WCAG</th><th>Violaciones criticas</th><th>Score</th>\n</tr></thead><tbody>\n'
    for i, l in enumerate(todos_ordenados, 1):
        sc_class = 'sh' if l['score_preliminar'] >= 7 else 'sm' if l['score_preliminar'] >= 4 else 'sl'
        html += '<tr><td>' + str(i) + '</td>'
        html += "<td><a href='" + l['tienda_url'] + "' target='_blank'>" + l['tienda_url'][:40] + '...</a></td>'
        html += '<td>' + l['nicho'] + '</td><td>' + l['email_contacto'] + '</td>'
        html += '<td>' + str(l['wcag_score_home_mobile']) + '</td><td>' + str(l['num_violaciones_criticas']) + '</td>'
        html += "<td class='" + sc_class + "'>" + str(l['score_preliminar']) + '/10</td></tr>\n'
    html += '</tbody></table></body></html>'
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    print('HTML: ' + OUTPUT_HTML)
    print('TOTAL: ' + str(total) + ' tiendas con violaciones criticas confirmadas.')
    try:
        os.system('termux-notification --title "Motor 2 WCAG" --content "Scraper termino" --sound')
    except Exception:
        pass
else:
    print('\nSin resultados. Prueba ampliando NICHOS_OBJETIVO o revisando las keys de Serper.')
try:
    import subprocess
    subprocess.run(['termux-wake-unlock'], check=False)
except Exception:
    pass
