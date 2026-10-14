"""Find marketing and advertising agencies by type and city with Serper and extract their public contact details."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
import csv
import re
import time
import os
from datetime import datetime
SERPER_API_KEYS = [k.strip() for k in os.getenv('SERPER_API_KEYS', 'YOUR_SERPER_API_KEY').split(',') if k.strip()]
_current_key_index = 0

def _get_current_key():
    global _current_key_index
    return SERPER_API_KEYS[_current_key_index % len(SERPER_API_KEYS)]

def _rotate_key():
    global _current_key_index
    _current_key_index += 1
    print('   Rotando a Serper key #' + str(_current_key_index % len(SERPER_API_KEYS) + 1), flush=True)
TIPOS_AGENCIA = ['agencia de marketing digital', 'agencia de publicidad', 'agencia de growth marketing', 'agencia de pauta publicitaria', 'agencia SEO SEM', 'agencia de generacion de leads', 'agencia de gestion de redes sociales', 'agencia de diseno y marketing']
CIUDADES = ['Bogota', 'Medellin', 'Cali', 'Barranquilla', 'Cartagena', 'Bucaramanga', 'Pereira']
RESULTADOS_POR_BUSQUEDA = 20
DOMINIOS_IGNORADOS = ('facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com', 'tiktok.com', 'youtube.com', 'wikipedia.org', 'paginasamarillas.com.co', 'clutch.co', 'goodfirms.co', 'designrush.com', 'indeed.com', 'computrabajo.com.co', 'glassdoor.com', 'google.com', 'maps.google.com')
CARPETA_SALIDA = 'agencias_leads'
os.makedirs(CARPETA_SALIDA, exist_ok=True)
SALIDA_CSV = os.path.join(CARPETA_SALIDA, f'agencias_{datetime.now().strftime('%Y-%m-%d')}.csv')
RE_TELEFONO = re.compile('(?:\\+?57)?[\\s\\-\\.]?3\\d{2}[\\s\\-\\.]?\\d{3}[\\s\\-\\.]?\\d{4}')
RE_WA_LINK = re.compile('(?:wa\\.me/|api\\.whatsapp\\.com/send/?\\?phone=)(\\d{10,15})')
RE_EMAIL = re.compile('[\\w.+-]+@[\\w-]+\\.\\w{2,}')
DOMINIOS_EMAIL_IGNORADOS = ('wixpress.com', 'sentry.io', 'shopify.com', 'myshopify.com', 'example.com', 'godaddy.com', 'cloudflare.com', 'schema.org', 'w3.org', 'google.com', 'gstatic.com', 'jsdelivr.net', 'cdnjs.com')
EXTENSIONES_NO_EMAIL = ('.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif', '.ico')
RUTAS_CONTACTO = ('/contacto', '/contactenos', '/contactanos', '/quienes-somos', '/nosotros', '/sobre-nosotros', '/about', '/about-us', '/pages/contacto', '/pages/quienes-somos', '/pages/nosotros')

def _es_numero_de_relleno(digitos_celular):
    return len(set(digitos_celular)) <= 2

def validar_y_normalizar_telefono_co(numero):
    if not numero:
        return None
    solo_digitos = re.sub('\\D', '', numero)
    celular = None
    if solo_digitos.startswith('57') and len(solo_digitos) == 12 and (solo_digitos[2] == '3'):
        celular = solo_digitos[2:]
    elif len(solo_digitos) == 10 and solo_digitos[0] == '3':
        celular = solo_digitos
    else:
        return None
    if _es_numero_de_relleno(celular):
        return None
    return '+57' + celular

def _extraer_email(html):
    for m in RE_EMAIL.finditer(html):
        email = m.group(0).lower()
        dominio_email = email.split('@')[-1]
        if any((d in dominio_email for d in DOMINIOS_EMAIL_IGNORADOS)):
            continue
        if dominio_email.endswith(EXTENSIONES_NO_EMAIL):
            continue
        return email
    return None

def _buscar_pagina_contacto(dominio):
    for ruta in RUTAS_CONTACTO:
        try:
            r = requests.get(f'{dominio}{ruta}', timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                return (r.text, ruta)
        except Exception:
            continue
    return (None, None)

def extraer_contacto(dominio):
    try:
        r = requests.get(dominio, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            return (None, None, None)
        html = r.text
    except Exception:
        return (None, None, None)
    wa_match = RE_WA_LINK.search(html)
    numero = wa_match.group(1) if wa_match else None
    if not numero:
        tel_match = RE_TELEFONO.search(html)
        numero = re.sub('[\\s\\-\\.]', '', tel_match.group(0)) if tel_match else None
    whatsapp = validar_y_normalizar_telefono_co(numero)
    email = _extraer_email(html)
    fuente = 'home' if whatsapp or email else None
    if not whatsapp or not email:
        html_contacto, ruta = _buscar_pagina_contacto(dominio)
        if html_contacto:
            if not email:
                email = _extraer_email(html_contacto)
                if email:
                    fuente = ruta
            if not whatsapp:
                wa_match2 = RE_WA_LINK.search(html_contacto)
                numero2 = wa_match2.group(1) if wa_match2 else None
                if not numero2:
                    tel_match2 = RE_TELEFONO.search(html_contacto)
                    numero2 = re.sub('[\\s\\-\\.]', '', tel_match2.group(0)) if tel_match2 else None
                whatsapp = validar_y_normalizar_telefono_co(numero2)
                if whatsapp and (not fuente):
                    fuente = ruta
    return (whatsapp, email, fuente)

def _una_busqueda_serper(query, num_reintentos=3):
    for intento in range(num_reintentos):
        try:
            r = requests.post('https://google.serper.dev/search', headers={'X-API-KEY': _get_current_key(), 'Content-Type': 'application/json'}, json={'q': query, 'num': RESULTADOS_POR_BUSQUEDA}, timeout=15)
            if r.status_code == 200:
                return r.json().get('organic', [])
            elif r.status_code in (401, 402, 403, 429):
                _rotate_key()
                time.sleep(2)
                continue
            else:
                time.sleep(2 ** intento)
        except Exception as e:
            print(f"    [!] Error en busqueda '{query}': {e}")
            time.sleep(2 ** intento)
    return []

def _dominio_de(link):
    dominio = re.sub('^https?://(www\\.)?', '', link).split('/')[0].lower()
    return dominio

def main():
    total_queries = len(TIPOS_AGENCIA) * len(CIUDADES)
    print(f'[*] {len(TIPOS_AGENCIA)} tipos de agencia x {len(CIUDADES)} ciudades = {total_queries} busquedas (~{total_queries} creditos de Serper)')
    existe = os.path.exists(SALIDA_CSV)
    campos = ['agencia_tipo', 'ciudad', 'dominio', 'whatsapp', 'email', 'fuente_contacto', 'titulo_resultado']
    vistos = set()
    total_guardadas = 0
    total_sin_contacto = 0
    with open(SALIDA_CSV, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        if not existe:
            writer.writeheader()
        for tipo in TIPOS_AGENCIA:
            for ciudad in CIUDADES:
                query = f'{tipo} {ciudad}'
                print(f'\n[*] {query}')
                resultados = _una_busqueda_serper(query)
                for item in resultados:
                    link = item.get('link', '')
                    if not link:
                        continue
                    dominio_raw = _dominio_de(link)
                    if dominio_raw in vistos:
                        continue
                    if any((d in dominio_raw for d in DOMINIOS_IGNORADOS)):
                        continue
                    vistos.add(dominio_raw)
                    dominio = f'https://{dominio_raw}'
                    whatsapp, email, fuente = extraer_contacto(dominio)
                    if not whatsapp and (not email):
                        total_sin_contacto += 1
                        continue
                    writer.writerow({'agencia_tipo': tipo, 'ciudad': ciudad, 'dominio': dominio, 'whatsapp': whatsapp or '', 'email': email or '', 'fuente_contacto': fuente or '', 'titulo_resultado': item.get('title', '')})
                    f.flush()
                    total_guardadas += 1
                    print(f'    [+] {dominio_raw} | fuente: {fuente} | {whatsapp or email}')
                    time.sleep(1)
                time.sleep(0.5)
    print(f'\n[*] Corrida terminada. {total_guardadas} agencias guardadas en {SALIDA_CSV}')
    print(f'    {total_sin_contacto} descartadas por no tener whatsapp ni email extraible')
if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n[*] Detenido manualmente. Lo ya guardado en el CSV esta a salvo.')
    except Exception as e:
        print(f'\n[!] Error no previsto: {e}')
        print('    Lo ya guardado en el CSV esta a salvo. Pega este mensaje en el chat.')
