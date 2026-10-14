"""Pull upcoming SECOP II procurement processes from the Colombian open data API (datos.gov.co), rank them by urgency, resolve a contact number per company (Serper search + site parsing) and write a CSV."""
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
from datetime import datetime, timedelta
SERPER_API_KEYS = [k.strip() for k in os.getenv('SERPER_API_KEYS', 'YOUR_SERPER_API_KEY').split(',') if k.strip()]
_current_key_index = 0

def _get_current_key():
    global _current_key_index
    return SERPER_API_KEYS[_current_key_index % len(SERPER_API_KEYS)]

def _rotate_key():
    global _current_key_index
    _current_key_index += 1
    print('   Rotando a Serper key #' + str(_current_key_index % len(SERPER_API_KEYS) + 1), flush=True)
SECOP_DATASET = 'p6dx-8zbt'
SECOP_URL = f'https://www.datos.gov.co/resource/{SECOP_DATASET}.json'
PALABRAS_CLAVE = ['software', 'tecnologia', 'consultoria', 'logistica', 'mantenimiento', 'construccion', 'suministro', 'dotacion', 'obra', 'infraestructura', 'adecuacion', 'adecuación', 'aseo', 'vigilancia', 'seguridad', 'transporte', 'papeleria', 'papelería', 'insumos', 'equipos', 'electrico', 'eléctrico', 'redes', 'conectividad', 'impresion', 'impresión', 'publicidad', 'eventos', 'alimentacion', 'alimentación', 'catering']
DIAS_VENTANA = 7
SALIDA_CSV = 'secop_leads.csv'
PALABRAS_EXCLUIR = ['servicios profesionales', 'servicio profesional', 'prestacion de servicios de apoyo', 'prestación de servicios de apoyo', 'apoyo a la gestion', 'apoyo a la gestión', 'auxiliar de enfermeria', 'auxiliar de enfermería', 'profesional complementario', 'gestor comunitario', 'citohistologia', 'citohistología', 'medico general', 'médico general', 'psicologo', 'psicólogo']
MARCADORES_EMPRESA = ['s.a.s', 'sas', 'ltda', 's.a.', ' sa ', 'cia', 'e.u.', 'eu ', 'asociados']

def es_nombre_de_persona(texto):
    t = texto.strip()
    if not t:
        return False
    tl = t.lower()
    if any((m in tl for m in MARCADORES_EMPRESA)):
        return False
    palabras = t.split()
    if not 2 <= len(palabras) <= 4:
        return False
    if not all((re.fullmatch('[A-ZÁÉÍÓÚÑ]+', p) for p in palabras)):
        return False
    palabras_contrato = {'SERVICIO', 'SERVICIOS', 'MANTENIMIENTO', 'OBRA', 'SUMINISTRO', 'CONTRATO', 'COMPRA', 'ADQUISICION', 'ADQUISICIÓN', 'DOTACION', 'DOTACIÓN', 'APOYO'}
    if palabras_contrato & set(palabras):
        return False
    return True

def verificar_campos_secop():
    try:
        r = requests.get(SECOP_URL, params={'$limit': 1}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data:
            print('=== CAMPOS REALES QUE DEVUELVE SECOP ===')
            for k, v in data[0].items():
                print(f'  {k} = {str(v)[:60]}')
            print('=========================================')
        else:
            print('[!] SECOP respondió vacío. Puede estar caído, revisa de nuevo en un rato.')
        return data
    except Exception as e:
        print(f'[!] No se pudo conectar a SECOP: {e}')
        print('    Copia este mensaje y pégalo en el chat para que lo revise.')
        return []
MAX_CONTACTOS_A_RESOLVER = 60

def obtener_procesos(limit_total=3000, tamano_pagina=1000):
    fecha_desde = (datetime.now() - timedelta(days=20)).strftime('%Y-%m-%dT00:00:00')
    where_clause = f"fecha_de_publicacion_del > '{fecha_desde}' AND estado_de_apertura_del_proceso = 'Abierto'"
    todos = []
    offset = 0
    while offset < limit_total:
        params = {'$limit': tamano_pagina, '$offset': offset, '$order': 'fecha_de_publicacion_del DESC', '$where': where_clause}
        try:
            r = requests.get(SECOP_URL, params=params, timeout=30)
            r.raise_for_status()
            pagina = r.json()
        except Exception as e:
            print(f'[!] Error consultando SECOP (offset {offset}): {e}')
            print('    Corriendo auto-diagnóstico...')
            verificar_campos_secop()
            break
        if not pagina:
            break
        todos.extend(pagina)
        print(f'[*] {len(todos)} procesos traídos hasta ahora...')
        offset += tamano_pagina
        time.sleep(0.5)
    return todos

def clasificar_urgencia(proceso):
    fase = str(proceso.get('fase', '')).lower()
    estado = str(proceso.get('estado_resumen', '')).lower()
    descripcion = str(proceso.get('descripci_n_del_procedimiento', '')).lower()
    if 'subsana' in fase or 'subsana' in estado or 'subsana' in descripcion:
        return (1, None)
    if 'presentaci' in fase and 'oferta' in fase:
        return (2, None)
    if 'presentaci' in estado and 'oferta' in estado:
        return (2, None)
    return (3, None)
PALABRAS_EXCLUIR = ['servicios profesionales', 'servicio profesional', 'prestacion de servicios de apoyo', 'prestación de servicios de apoyo', 'apoyo a la gestion', 'apoyo a la gestión']
MODALIDADES_EXCLUIR = ['contratación directa', 'contratacion directa']

def filtra_por_sector(proceso):
    nombre_proc = str(proceso.get('nombre_del_procedimiento', ''))
    texto = (nombre_proc + ' ' + str(proceso.get('descripci_n_del_procedimiento', ''))).lower()
    modalidad = str(proceso.get('modalidad_de_contratacion', '')).lower()
    adjudicado = str(proceso.get('adjudicado', '')).strip().lower()
    proveedor = str(proceso.get('nombre_del_proveedor', '')).strip().lower()
    if adjudicado == 'si' or adjudicado == 'sí':
        return False
    if proveedor and proveedor not in ('no definido', '', 'no adjudicado'):
        return False
    if es_nombre_de_persona(nombre_proc):
        return False
    if 'directa' in modalidad:
        return False
    if any((p in texto for p in PALABRAS_EXCLUIR)):
        return False
    return any((p in texto for p in PALABRAS_CLAVE))
RE_TELEFONO = re.compile('(?<!\\d)(?:\\+?57)?[\\s\\-\\.]?3\\d{2}[\\s\\-\\.]?\\d{3}[\\s\\-\\.]?\\d{4}(?!\\d)')
RE_WA_LINK = re.compile('(?:wa\\.me/|api\\.whatsapp\\.com/send\\?phone=)(\\d{10,15})')

def buscar_en_serper(query, num_reintentos=3):
    for intento in range(num_reintentos):
        try:
            r = requests.post('https://google.serper.dev/search', headers={'X-API-KEY': _get_current_key(), 'Content-Type': 'application/json'}, json={'q': query}, timeout=15)
            if r.status_code == 200:
                return r.json()
            elif r.status_code in (401, 403, 429):
                _rotate_key()
                time.sleep(2)
                continue
            else:
                time.sleep(2 ** intento)
        except Exception as e:
            print(f'    [!] Error Serper: {e}')
            time.sleep(2 ** intento)
    return {}

def buscar_places_serper(nombre_empresa, num_reintentos=3):
    for intento in range(num_reintentos):
        try:
            r = requests.post('https://google.serper.dev/places', headers={'X-API-KEY': _get_current_key(), 'Content-Type': 'application/json'}, json={'q': nombre_empresa}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                places = data.get('places', [])
                if places and places[0].get('phoneNumber'):
                    return (places[0]['phoneNumber'], places[0].get('website', ''))
                return (None, None)
            elif r.status_code in (401, 403, 429):
                _rotate_key()
                time.sleep(2)
                continue
            else:
                time.sleep(2 ** intento)
        except Exception as e:
            print(f'    [!] Error Places: {e}')
            time.sleep(2 ** intento)
    return (None, None)

def extraer_de_sitio(url):
    try:
        r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        html = r.text
        wa = RE_WA_LINK.search(html)
        if wa:
            return (wa.group(1), 'wa.me directo')
        tel = RE_TELEFONO.search(html)
        if tel:
            numero = re.sub('[\\s\\-\\.]', '', tel.group(0))
            return (numero, 'telefono en sitio')
    except Exception:
        pass
    return (None, None)

def validar_y_normalizar_telefono_co(numero):
    if not numero:
        return None
    solo_digitos = re.sub('\\D', '', numero)
    if solo_digitos.startswith('57') and len(solo_digitos) == 12 and (solo_digitos[2] == '3'):
        return '+' + solo_digitos
    if len(solo_digitos) == 10 and solo_digitos[0] == '3':
        return '+57' + solo_digitos
    return None

def resolver_contacto(nombre_empresa):
    tel, sitio = buscar_places_serper(nombre_empresa)
    tel_valido = validar_y_normalizar_telefono_co(tel)
    if tel_valido:
        return (tel_valido, '1-places', sitio)
    candidatos = []
    resultado = buscar_en_serper(f'"{nombre_empresa}" contacto OR whatsapp Colombia')
    organico = resultado.get('organic', [])
    candidatos.extend((o['link'] for o in organico[:4] if o.get('link')))
    resultado_fb = buscar_en_serper(f'"{nombre_empresa}" site:facebook.com Colombia')
    organico_fb = resultado_fb.get('organic', [])
    candidatos.extend((o['link'] for o in organico_fb[:2] if o.get('link')))
    if not candidatos:
        return (None, 'descartado', None)
    for url in candidatos:
        numero, tipo = extraer_de_sitio(url)
        numero_valido = validar_y_normalizar_telefono_co(numero)
        if numero_valido:
            return (numero_valido, f'2/3-{tipo}', url)
    return (None, '4-solo-link', candidatos[0])

def main():
    print('[*] Consultando SECOP II (esto puede traer miles de filas crudas)...')
    procesos = obtener_procesos()
    print(f'[*] {len(procesos)} procesos crudos recibidos')
    ya_adjudicados = sum((1 for p in procesos if str(p.get('adjudicado', '')).strip().lower() in ('si', 'sí') or str(p.get('nombre_del_proveedor', '')).strip().lower() not in ('no definido', '', 'no adjudicado')))
    print(f'[*] {ya_adjudicados} de esos ya tienen proveedor adjudicado (se descartan, publicados solo por transparencia)')
    candidatos = [p for p in procesos if filtra_por_sector(p) and p.get('entidad')]
    print(f'[*] {len(candidatos)} pasaron el filtro de sector/persona/adjudicado')
    con_urgencia = [(*clasificar_urgencia(p), p) for p in candidatos]
    con_urgencia.sort(key=lambda x: x[0])
    candidatos_ordenados = [p for _, _, p in con_urgencia]
    if len(candidatos_ordenados) > MAX_CONTACTOS_A_RESOLVER:
        print(f'[*] Cortando a los {MAX_CONTACTOS_A_RESOLVER} más urgentes (de {len(candidatos_ordenados)} candidatos) para no agotar Serper')
    candidatos_ordenados = candidatos_ordenados[:MAX_CONTACTOS_A_RESOLVER]
    leads = []
    for p in candidatos_ordenados:
        nivel_urgencia, dias = clasificar_urgencia(p)
        entidad = p.get('entidad', '')
        print(f'[*] Resolviendo contacto: {entidad[:50]}...')
        numero, nivel_contacto, link = resolver_contacto(entidad)
        time.sleep(1)
        if numero is None and link is None:
            continue
        leads.append({'id_del_proceso': p.get('id_del_proceso', ''), 'entidad': entidad, 'nit': p.get('nit_entidad', ''), 'proceso': p.get('nombre_del_procedimiento', '')[:120], 'modalidad': p.get('modalidad_de_contratacion', ''), 'referencia': p.get('referencia_del_proceso', ''), 'nivel_urgencia': nivel_urgencia, 'dias_restantes': dias, 'numero_whatsapp': numero or '', 'nivel_contacto': nivel_contacto, 'link_respaldo': link or '', 'url_proceso': (p.get('urlproceso') or {}).get('url', '') if isinstance(p.get('urlproceso'), dict) else p.get('urlproceso', '')})
    leads.sort(key=lambda x: (x['nivel_urgencia'], x['dias_restantes'] or 999))
    with open(SALIDA_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=leads[0].keys() if leads else [])
        writer.writeheader()
        writer.writerows(leads)
    print(f'[*] Listo. {len(leads)} leads con contacto resuelto -> {SALIDA_CSV}')
    print(f'    Nivel 1 (urgente): {sum((1 for l in leads if l['nivel_urgencia'] == 1))}')
    print(f'    Nivel 2 (7 dias):  {sum((1 for l in leads if l['nivel_urgencia'] == 2))}')
    print(f'    Nivel 3 (relleno): {sum((1 for l in leads if l['nivel_urgencia'] == 3))}')
if __name__ == '__main__':
    main()
