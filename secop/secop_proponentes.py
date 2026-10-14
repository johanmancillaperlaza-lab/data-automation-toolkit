"""Fetch the bidders of SECOP II processes from the open dataset "Proponentes por Proceso" and write them to CSV."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
import csv
import time
PROPONENTES_DATASET = 'hgi6-6wh3'
PROPONENTES_URL = f'https://www.datos.gov.co/resource/{PROPONENTES_DATASET}.json'

def verificar_campos_proponentes():
    try:
        r = requests.get(PROPONENTES_URL, params={'$limit': 1}, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data:
            print("=== CAMPOS REALES DE 'Proponentes por Proceso' ===")
            for k, v in data[0].items():
                print(f'  {k} = {str(v)[:60]}')
            print('====================================================')
        else:
            print('[!] El dataset respondió vacío.')
        return data
    except Exception as e:
        print(f'[!] No se pudo conectar: {e}')
        print('    Copia este mensaje y pégalo en el chat.')
        return []

def obtener_proponentes_de_proceso(id_proceso):
    params = {'$where': f"id_procedimiento = '{id_proceso}'", '$limit': 50}
    try:
        r = requests.get(PROPONENTES_URL, params=params, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'    [!] Error consultando proponentes: {e}')
        return []

def cruzar_procesos_con_proponentes(archivo_leads_entrada='secop_leads.csv', archivo_salida='secop_proponentes.csv'):
    filas_salida = []
    with open(archivo_leads_entrada, encoding='utf-8') as f:
        procesos = list(csv.DictReader(f))
    print(f'[*] {len(procesos)} procesos a revisar en busca de proponentes...')
    for i, proceso in enumerate(procesos):
        id_proceso = proceso.get('id_del_proceso') or proceso.get('id_proceso')
        if not id_proceso:
            continue
        print(f'[{i + 1}/{len(procesos)}] Proceso {proceso.get('referencia', '')}...')
        proponentes = obtener_proponentes_de_proceso(id_proceso)
        time.sleep(0.5)
        for prop in proponentes:
            nombre_empresa = prop.get('proveedor', '')
            if not nombre_empresa:
                continue
            filas_salida.append({'entidad_compradora': proceso.get('entidad', ''), 'referencia_proceso': proceso.get('referencia', ''), 'nivel_urgencia': proceso.get('nivel_urgencia', ''), 'dias_restantes': proceso.get('dias_restantes', ''), 'empresa_proponente': nombre_empresa, 'nit_proponente': prop.get('nit_proveedor', ''), 'url_proceso': proceso.get('url_proceso', '')})
    if not filas_salida:
        print('[!] No se encontraron proponentes. Corriendo auto-diagnóstico...')
        verificar_campos_proponentes()
        return
    with open(archivo_salida, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=filas_salida[0].keys())
        writer.writeheader()
        writer.writerows(filas_salida)
    print(f'[*] {len(filas_salida)} empresas-proceso -> {archivo_salida}')
    print("    Siguiente paso: pasa 'empresa_proponente' por resolver_contacto() de secop_scraper.py")
if __name__ == '__main__':
    cruzar_procesos_con_proponentes()
