#!/usr/bin/env python3
"""
download_data.py
================
Script flexível para automação de download dos dados oficiais da CEAP
da Câmara dos Deputados do Brasil para qualquer intervalo histórico de anos
(2008 até a atualidade) e do catálogo de parlamentares.
"""

import os
import sys
import io
import zipfile
import argparse
import urllib.request

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data'))

def download_file(url, dest_path):
    print(f"[*] Baixando: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req) as resp:
        total_size = int(resp.info().get('Content-Length', -1))
        downloaded = 0
        chunk_size = 64 * 1024
        chunks = []
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                percent = (downloaded / total_size) * 100
                sys.stdout.write(f"\r    Progresso: {downloaded / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB ({percent:.1f}%)")
            else:
                sys.stdout.write(f"\r    Baixados: {downloaded / (1024*1024):.2f} MB")
            sys.stdout.flush()
        print()
        return b''.join(chunks)

def process_despesas(year):
    zip_url = f"https://www.camara.leg.br/cotas/Ano-{year}.csv.zip"
    csv_filename = f"Ano-{year}.csv"
    dest_csv = os.path.join(DATA_DIR, csv_filename)

    if os.path.exists(dest_csv):
        print(f"[OK] {csv_filename} já existe em {DATA_DIR}. Pulando download.")
        return

    try:
        content = download_file(zip_url, dest_csv)
        print(f"[*] Descompactando {csv_filename}...")
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            z.extractall(DATA_DIR)
        print(f"[OK] {csv_filename} salvo com sucesso.")
    except Exception as e:
        print(f"[AVISO] Tentando fallback para URL alternativa para ano {year}...")
        try:
            alt_url = f"https://dadosabertos.camara.leg.br/arquivos/despesas/csv/Ano-{year}.csv"
            content = download_file(alt_url, dest_csv)
            with open(dest_csv, 'wb') as f:
                f.write(content)
            print(f"[OK] {csv_filename} baixado via URL alternativa.")
        except Exception as e2:
            print(f"[ERRO] Falha ao processar ano {year}: {e2}")

def process_deputados():
    url = "https://dadosabertos.camara.leg.br/arquivos/deputados/csv/deputados.csv"
    dest_csv = os.path.join(DATA_DIR, "deputados.csv")

    if os.path.exists(dest_csv):
        print(f"[OK] deputados.csv já existe em {DATA_DIR}. Pulando download.")
        return

    try:
        content = download_file(url, dest_csv)
        with open(dest_csv, 'wb') as f:
            f.write(content)
        print(f"[OK] deputados.csv salvo com sucesso.")
    except Exception as e:
        print(f"[ERRO] Falha ao baixar deputados.csv: {e}")

def main():
    parser = argparse.ArgumentParser(description="Download flexível de dados da CEAP (Câmara dos Deputados)")
    parser.add_argument("--ano-inicial", type=int, default=2019, help="Ano inicial da série (default: 2019, mínimo: 2008)")
    parser.add_argument("--ano-final", type=int, default=2024, help="Ano final da série (default: 2024)")
    parser.add_argument("--todos", action="store_true", help="Baixar a série histórica completa desde 2008")
    args = parser.parse_args()

    ano_ini = 2008 if args.todos else args.ano_inicial
    ano_fim = args.ano_final

    years = list(range(ano_ini, ano_fim + 1))

    os.makedirs(DATA_DIR, exist_ok=True)
    print("=" * 70)
    print(f"  INGESTÃO DE DADOS DA CEAP: ANOS {ano_ini} A {ano_fim}")
    print("=" * 70)
    print(f"Diretório de destino: {DATA_DIR}\n")

    for y in years:
        process_despesas(y)

    process_deputados()

    print("\n" + "=" * 70)
    print("  DOWNLOAD E EXTRAÇÃO CONCLUÍDOS!")
    print("=" * 70)

if __name__ == "__main__":
    main()
