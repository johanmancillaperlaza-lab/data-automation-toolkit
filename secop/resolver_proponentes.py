"""Resolve a contact number for the bidders found by secop_proponentes.py, reusing the contact resolution of secop_scraper.py."""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import csv
import time
from secop_scraper import resolver_contacto
ARCHIVO_ENTRADA = 'secop_proponentes.csv'
ARCHIVO_SALIDA = 'secop_proponentes_contacto.csv'

def main():
    with open(ARCHIVO_ENTRADA, encoding='utf-8') as f:
        filas = list(csv.DictReader(f))
    print(f'[*] {len(filas)} empresas a resolver...')
    resultado = []
    for i, fila in enumerate(filas):
        nombre = fila.get('empresa_proponente', '')
        if not nombre:
            continue
        print(f'[{i + 1}/{len(filas)}] Resolviendo contacto: {nombre}...')
        numero, nivel_contacto, link = resolver_contacto(nombre)
        time.sleep(1)
        fila['numero_whatsapp'] = numero or ''
        fila['nivel_contacto'] = nivel_contacto
        fila['link_respaldo'] = link or ''
        resultado.append(fila)
    if not resultado:
        print('[!] No hay filas para escribir.')
        return
    with open(ARCHIVO_SALIDA, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=resultado[0].keys())
        writer.writeheader()
        writer.writerows(resultado)
    con_numero = sum((1 for r in resultado if r['numero_whatsapp']))
    print(f'[*] Listo -> {ARCHIVO_SALIDA}')
    print(f'    Con WhatsApp válido: {con_numero}/{len(resultado)}')
    print(f'    Con solo link de respaldo: {sum((1 for r in resultado if not r['numero_whatsapp'] and r['link_respaldo']))}/{len(resultado)}')
if __name__ == '__main__':
    main()
