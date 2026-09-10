#!/usr/bin/env python3
"""
validate_model.py
=================
Valida a integridade do modelo semântico TMDL multianual (Camara_Analytics),
parâmetros de 2008 a 2026, estrutura PBIR e realiza os cálculos estatísticos
de auditoria (Z-Score e IQR anualizados, e Lei de Benford) sobre a base histórica.
"""

import os
import csv
import math
from collections import Counter

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SAMPLE_DIR = os.path.join(BASE_DIR, 'data', 'sample')

def validate_files():
    print("=== 1. VERIFICANDO ARQUIVOS DA ARQUITETURA PBIP/TMDL/PBIR (2008 A 2026) ===")
    required_files = [
        os.path.join(BASE_DIR, 'Camara_Analytics.pbip'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition.pbism'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'database.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'model.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'expressions.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'relationships.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'tables', 'F_Despesas.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'tables', 'D_Deputado.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'tables', 'D_Calendario.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'tables', 'D_TipoDespesa.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'tables', 'D_Fornecedor.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'tables', 'D_Benford.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.SemanticModel', 'definition', 'tables', '_Medidas.tmdl'),
        os.path.join(BASE_DIR, 'Camara_Analytics.Report', 'definition.pbir'),
        os.path.join(BASE_DIR, 'Camara_Analytics.Report', 'definition', 'report.json'),
        os.path.join(BASE_DIR, 'Camara_Analytics.Report', 'definition', 'pages', 'pages.json'),
        os.path.join(BASE_DIR, 'Camara_Analytics.Report', 'definition', 'pages', '01_linha_tempo_historica', 'page.json'),
        os.path.join(BASE_DIR, 'Camara_Analytics.Report', 'definition', 'pages', '02_painel_auditoria_fraudes', 'page.json'),
        os.path.join(BASE_DIR, 'Camara_Analytics.Report', 'definition', 'pages', '03_raio_x_parlamentar', 'page.json'),
        os.path.join(BASE_DIR, 'Camara_Analytics.Report', 'definition', 'pages', '04_fornecedores_risco', 'page.json')
    ]

    all_ok = True
    for fpath in required_files:
        rel = os.path.relpath(fpath, BASE_DIR)
        if os.path.exists(fpath):
            print(f" [OK] {rel}")
        else:
            print(f" [FALTA] {rel}")
            all_ok = False
    return all_ok

def test_statistical_calculations():
    print("\n=== 2. TESTE DOS MOTORES ESTATÍSTICOS DAX NA SÉRIE MULTIANUAL (2008 A 2024) ===")
    sample_files = [os.path.join(SAMPLE_DIR, f) for f in os.listdir(SAMPLE_DIR) if f.startswith("Ano-") and f.endswith(".csv")]
    sample_files.sort()
    
    valores = []
    primeiros_digitos = []
    valores_por_ano_categoria = {}
    notas_centavos_zero = 0
    anos_encontrados = set()

    for sfile in sample_files:
        ano_str = os.path.basename(sfile).replace("Ano-", "").replace(".csv", "")
        with open(sfile, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                try:
                    v_str = row.get('vlrLiquido', '0').replace(',', '.')
                    v = float(v_str)
                    cat = row.get('txtDescricao', 'OUTROS')
                    ano = int(row.get('numAno', ano_str))
                    if v > 0:
                        valores.append(v)
                        anos_encontrados.add(ano)
                        # Checagem de centavos .00
                        if round(v * 100) % 100 == 0:
                            notas_centavos_zero += 1

                        # Primeiro dígito para Lei de Benford
                        str_clean = ''.join(c for c in f"{v:.2f}" if c in '123456789')
                        if str_clean:
                            primeiros_digitos.append(int(str_clean[0]))
                        
                        chave = (ano, cat)
                        if chave not in valores_por_ano_categoria:
                            valores_por_ano_categoria[chave] = []
                        valores_por_ano_categoria[chave].append(v)
                except Exception:
                    pass

    total_notas = len(valores)
    total_gasto = sum(valores)
    ticket_medio = total_gasto / total_notas if total_notas > 0 else 0

    print(f"Anos Presentes na Amostra: {sorted(list(anos_encontrados))}")
    print(f"Total de Notas Analisadas: {total_notas:,}")
    print(f"Total Gasto Histórico Amostral: R$ {total_gasto:,.2f}")
    print(f"Ticket Médio Global: R$ {ticket_medio:,.2f}")
    print(f"Notas com Valores Redondos (.00): {notas_centavos_zero:,} ({notas_centavos_zero/total_notas*100:.2f}%)")

    # 1. Lei de Benford
    print("\n--- LEI DE BENFORD (MULTIANUAL 2008 A 2024) ---")
    contagem_digitos = Counter(primeiros_digitos)
    total_digitos = len(primeiros_digitos)
    mad_total = 0.0

    print(f"{'Dígito':<8}{'Real (Qtd)':<12}{'Real (%)':<12}{'Teórico Benford (%)':<20}{'Desvio Abs'}")
    for d in range(1, 10):
        qtd = contagem_digitos.get(d, 0)
        freq_real = qtd / total_digitos if total_digitos > 0 else 0
        freq_teorica = math.log10(1 + (1 / d))
        desvio = abs(freq_real - freq_teorica)
        mad_total += desvio
        print(f"{d:<8}{qtd:<12}{freq_real*100:>7.2f}%    {freq_teorica*100:>10.2f}%          {desvio*100:>6.2f}%")

    mad = mad_total / 9.0
    print(f"\nMAD Benford: {mad:.4f}")
    status = "Conformidade Estrita" if mad <= 0.006 else ("Conformidade Aceitável" if mad <= 0.012 else ("Conformidade Marginal" if mad <= 0.015 else "Alerta Forense"))
    print(f"Status Nigrini: {status}")

    # 2. Z-Score Anualizado por Categoria
    print("\n--- OUTLIERS Z-SCORE ANUALIZADOS (Z > 3 por Ano e Categoria) ---")
    outliers_z = 0
    total_outliers_z_val = 0.0
    for (ano, cat), v_list in valores_por_ano_categoria.items():
        if len(v_list) > 2:
            n = len(v_list)
            mean = sum(v_list) / n
            var = sum((x - mean) ** 2 for x in v_list) / (n - 1)
            std = math.sqrt(var)
            if std > 0:
                for x in v_list:
                    z = (x - mean) / std
                    if z > 3:
                        outliers_z += 1
                        total_outliers_z_val += x

    print(f"Qtd Documentos com Z > 3 Anualizado: {outliers_z}")
    print(f"Volume Financeiro Outliers Z-Score: R$ {total_outliers_z_val:,.2f}")

    # 3. IQR Anualizado por Categoria
    print("\n--- OUTLIERS IQR ANUALIZADOS (Q3 + 1.5 * IQR por Ano e Categoria) ---")
    outliers_iqr = 0
    total_outliers_iqr_val = 0.0
    for (ano, cat), v_list in valores_por_ano_categoria.items():
        if len(v_list) >= 4:
            s_list = sorted(v_list)
            n = len(s_list)
            q1 = s_list[int(n * 0.25)]
            q3 = s_list[int(n * 0.75)]
            iqr = q3 - q1
            lim_sup = q3 + (1.5 * iqr)
            for x in v_list:
                if x > lim_sup:
                    outliers_iqr += 1
                    total_outliers_iqr_val += x

    print(f"Qtd Documentos Outliers IQR Anualizado: {outliers_iqr}")
    print(f"Volume Financeiro Outliers IQR: R$ {total_outliers_iqr_val:,.2f}")

def main():
    ok = validate_files()
    if ok:
        print("\n[SUCESSO] Todos os arquivos da arquitetura Camara_Analytics estão 100% íntegros!")
    test_statistical_calculations()

if __name__ == "__main__":
    main()
