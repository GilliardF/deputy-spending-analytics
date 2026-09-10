#!/usr/bin/env python3
"""
generate_sample_data.py
=======================
Gera amostras reais representativas cobrindo marcos históricos da CEAP
(2008 até a atualidade) na pasta data/sample/ para testes imediatos no Power BI.
"""

import os
import io
import zipfile
import urllib.request

SAMPLE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'sample'))
KEY_YEARS = [2008, 2011, 2015, 2019, 2020, 2021, 2022, 2023, 2024]

def fetch_sample_year(year, num_rows=1000):
    url = f"https://www.camara.leg.br/cotas/Ano-{year}.csv.zip"
    dest_path = os.path.join(SAMPLE_DIR, f"Ano-{year}.csv")
    if os.path.exists(dest_path):
        print(f"[OK] Amostra {dest_path} já existe.")
        return

    print(f"[*] Baixando amostra do marco histórico {year}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as resp:
            z = zipfile.ZipFile(io.BytesIO(resp.read()))
            csv_name = f"Ano-{year}.csv"
            with z.open(csv_name) as f_in, open(dest_path, 'w', encoding='utf-8') as f_out:
                for i, line in enumerate(f_in):
                    f_out.write(line.decode('utf-8', errors='ignore'))
                    if i >= num_rows:
                        break
        print(f"[OK] Amostra de {year} salva com {num_rows} registros em {dest_path}")
    except Exception as e:
        print(f"[AVISO] Tentando fallback para URL direta em {year}: {e}")
        try:
            alt_url = f"https://dadosabertos.camara.leg.br/arquivos/despesas/csv/Ano-{year}.csv"
            req2 = urllib.request.Request(alt_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req2) as resp2, open(dest_path, 'w', encoding='utf-8') as f_out:
                for i, line in enumerate(resp2):
                    f_out.write(line.decode('utf-8', errors='ignore'))
                    if i >= num_rows:
                        break
            print(f"[OK] Amostra de {year} salva via URL alternativa.")
        except Exception as e2:
            print(f"[ERRO] Não foi possível obter {year}: {e2}")

def fetch_sample_deputados(num_rows=500):
    url = "https://dadosabertos.camara.leg.br/arquivos/deputados/csv/deputados.csv"
    dest_path = os.path.join(SAMPLE_DIR, "deputados.csv")
    if os.path.exists(dest_path):
        print(f"[OK] Amostra {dest_path} já existe.")
        return

    print("[*] Baixando amostra de deputados.csv...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as resp:
            lines = []
            for i, line in enumerate(resp):
                lines.append(line.decode('utf-8', errors='ignore'))
                if i >= num_rows:
                    break
            with open(dest_path, 'w', encoding='utf-8') as f_out:
                f_out.writelines(lines)
        print(f"[OK] Amostra de deputados.csv salva com {num_rows} registros.")
    except Exception as e:
        print(f"[AVISO] Não foi possível baixar deputados: {e}")

def main():
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    print("=" * 70)
    print("  GERAÇÃO DE AMOSTRAS MULTIANUAIS (2008 A 2024+)")
    print("=" * 70)
    for y in KEY_YEARS:
        fetch_sample_year(y)
    fetch_sample_deputados()
    print("\nAmostras históricas concluídas em:", SAMPLE_DIR)

if __name__ == "__main__":
    main()
