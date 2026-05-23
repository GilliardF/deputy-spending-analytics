#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script de Ingestão e ETL (GCP) - Despesas dos Deputados Federais
Este script realiza as seguintes etapas:
1. Busca a lista de deputados das legislaturas especificadas na API da Câmara.
2. Busca as despesas de cada deputado nos anos informados.
3. Salva os dados brutos no formato NDJSON (.jsonl) em uma pasta temporária local.
4. Envia o arquivo local para o Google Cloud Storage (GCS).
5. Carrega os dados do GCS no Google BigQuery.
6. Limpa o arquivo temporário local.
"""

import argparse
import datetime
import json
import logging
import os
import time
import sys
import requests
from dotenv import load_dotenv
from google.cloud import storage, bigquery
from google.auth import default

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente do .env
load_dotenv()

# Mapeamento oficial de anos padrão para cada legislatura
LEGISLATURE_YEARS = {
    56: [2019, 2020, 2021, 2022, 2023],
    57: [2023, 2024, 2025, 2026, 2027]
}

def get_deputies(legislature, limit=None):
    """
    Busca a lista de deputados de uma determinada legislatura.
    """
    url = "https://dadosabertos.camara.leg.br/api/v2/deputados"
    params = {
        "idLegislatura": legislature,
        "ordem": "ASC",
        "ordenarPor": "nome"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    logger.info(f"Buscando deputados da legislatura {legislature}...")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        deputies = data.get("dados", [])
        
        if limit:
            logger.info(f"Aplicando limite de {limit} deputados para teste.")
            deputies = deputies[:limit]
            
        logger.info(f"Total de deputados obtidos: {len(deputies)}")
        return deputies
    except Exception as e:
        logger.error(f"Erro ao buscar lista de deputados para a legislatura {legislature}: {e}")
        return []

def get_expenses_for_deputy(deputy_id, year, delay=0.1):
    """
    Busca as despesas de um deputado em um ano específico com paginação.
    """
    url = f"https://dadosabertos.camara.leg.br/api/v2/deputados/{deputy_id}/despesas"
    params = {
        "ano": year,
        "itens": 100,
        "ordem": "ASC",
        "ordenarPor": "dataDocumento"
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    expenses = []
    
    while url:
        try:
            # Usar parâmetros somente na primeira chamada (onde a URL não tem query string de paginação)
            is_first_call = url.endswith("/despesas")
            response = requests.get(
                url, 
                params=params if is_first_call else None, 
                headers=headers, 
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            records = data.get("dados", [])
            expenses.extend(records)
            
            # Paginação
            url = None
            for link in data.get("links", []):
                if link.get("rel") == "next":
                    url = link.get("href")
                    break
                    
            if url:
                time.sleep(delay)  # Pequeno delay entre as páginas
                
        except Exception as e:
            logger.error(f"Erro ao buscar despesas do deputado {deputy_id} no ano {year}: {e}")
            break
            
    return expenses

def upload_file_to_gcs(local_path, bucket_name, destination_blob, project_id=None):
    """
    Faz o upload do arquivo local para um bucket do Cloud Storage (GCS).
    Cria o bucket caso ele não exista.
    """
    logger.info(f"Iniciando conexão com o Cloud Storage (Projeto: {project_id})...")
    storage_client = storage.Client(project=project_id)
    
    try:
        bucket = storage_client.get_bucket(bucket_name)
        logger.info(f"Bucket '{bucket_name}' já existe.")
    except Exception:
        logger.info(f"Bucket '{bucket_name}' não encontrado. Criando novo bucket...")
        # Cria o bucket na multi-região US por padrão (pode ser alterado conforme necessário)
        bucket = storage_client.create_bucket(bucket_name, location="US")
        logger.info(f"Bucket '{bucket_name}' criado com sucesso.")
        
    blob = bucket.blob(destination_blob)
    logger.info(f"Enviando arquivo '{local_path}' para 'gs://{bucket_name}/{destination_blob}'...")
    blob.upload_from_filename(local_path)
    logger.info("Upload realizado com sucesso.")
    return f"gs://{bucket_name}/{destination_blob}"

def load_gcs_to_bigquery(gcs_uri, dataset_id, table_id, project_id=None):
    """
    Carrega o arquivo NDJSON do GCS para o BigQuery.
    Cria o dataset caso ele não exista.
    """
    logger.info(f"Iniciando conexão com o BigQuery (Projeto: {project_id})...")
    bq_client = bigquery.Client(project=project_id)
    
    # Criar o dataset se não existir
    dataset_ref = bigquery.DatasetReference(bq_client.project, dataset_id)
    try:
        bq_client.get_dataset(dataset_ref)
        logger.info(f"Dataset '{dataset_id}' já existe.")
    except Exception:
        logger.info(f"Dataset '{dataset_id}' não encontrado. Criando novo dataset...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        bq_client.create_dataset(dataset)
        logger.info(f"Dataset '{dataset_id}' criado com sucesso.")
        
    table_ref = dataset_ref.table(table_id)
    
    # Configurar o Job de Carga
    # Definimos esquema explícito para campos com tipos de dados mistos (como UUIDs em codDocumento)
    # ou formatos de texto variados, para evitar erros de conversão do autodetect.
    schema_overrides = [
        bigquery.SchemaField("codDocumento", "STRING"),
        bigquery.SchemaField("numDocumento", "STRING"),
        bigquery.SchemaField("cnpjCpfFornecedor", "STRING"),
        bigquery.SchemaField("dataDocumento", "STRING"),
    ]
    
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=schema_overrides,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE, # Sobrescreve para evitar duplicidade de re-execução
    )
    
    logger.info(f"Carregando dados de '{gcs_uri}' para a tabela '{dataset_id}.{table_id}'...")
    load_job = bq_client.load_table_from_uri(gcs_uri, table_ref, job_config=job_config)
    
    logger.info(f"Job do BigQuery iniciado (ID: {load_job.job_id}). Aguardando conclusão...")
    load_job.result()  # Aguarda a conclusão
    
    destination_table = bq_client.get_table(table_ref)
    logger.info(f"Carga concluída. Tabela contém agora {destination_table.num_rows} linhas.")

def main():
    parser = argparse.ArgumentParser(description="ETL de Ingestão de Despesas da Câmara dos Deputados para o GCP.")
    
    parser.add_argument(
        "--legislatures", 
        type=str, 
        default="56,57", 
        help="Legislaturas separadas por vírgula (Padrão: 56,57)"
    )
    parser.add_argument(
        "--years", 
        type=str, 
        default="2020,2021,2022,2023,2024,2025,2026", 
        help="Anos das despesas separados por vírgula (Padrão: 2020,2021,2022,2023,2024,2025,2026)"
    )
    parser.add_argument(
        "--limit-deputies", 
        type=int, 
        default=None, 
        help="Limite de deputados a processar por legislatura (útil para testes rápidos)"
    )
    parser.add_argument(
        "--bucket", 
        type=str, 
        default="dados-brutos-camara", 
        help="Nome do bucket do Cloud Storage (Padrão: dados-brutos-camara)"
    )
    parser.add_argument(
        "--dataset", 
        type=str, 
        default="deputy_spending_analytics", 
        help="Nome do dataset do BigQuery (Padrão: deputy_spending_analytics)"
    )
    parser.add_argument(
        "--table", 
        type=str, 
        default="raw_deputy_expenses", 
        help="Nome da tabela do BigQuery (Padrão: raw_deputy_expenses)"
    )
    parser.add_argument(
        "--delay", 
        type=float, 
        default=0.1, 
        help="Delay em segundos entre as requisições à API para evitar rate limit (Padrão: 0.1)"
    )
    
    args = parser.parse_args()
    
    # Resolver ID do Projeto GCP (Ordem: Argumento -> .env [id_project] -> GCP Default)
    project_id = os.getenv("id_project")
    if not project_id:
        try:
            _, project_id = default()
        except Exception:
            project_id = None
            
    logger.info("=== Iniciando Processo de Ingestão ===")
    logger.info(f"Projeto GCP Identificado: {project_id}")
    
    # Processar listas de entrada
    legislatures = [int(x.strip()) for x in args.legislatures.split(",")]
    years_requested = [int(x.strip()) for x in args.years.split(",")]
    
    logger.info(f"Legislaturas selecionadas: {legislatures}")
    logger.info(f"Anos solicitados: {years_requested}")
    
    # Criar diretório temporário local
    temp_dir = "tmp"
    os.makedirs(temp_dir, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    local_file_path = os.path.join(temp_dir, f"raw_expenses_{timestamp}.jsonl")
    
    total_records = 0
    
    try:
        # Abrir o arquivo local para escrita em modo append (NDJSON)
        with open(local_file_path, "w", encoding="utf-8") as f_out:
            for leg in legislatures:
                deputies = get_deputies(leg, limit=args.limit_deputies)
                
                # Filtrar anos de interesse que pertencem a esta legislatura específica
                leg_years = LEGISLATURE_YEARS.get(leg, [])
                active_years = [y for y in years_requested if y in leg_years]
                
                logger.info(f"Anos ativos para a legislatura {leg}: {active_years}")
                
                for idx, dep in enumerate(deputies, start=1):
                    dep_id = dep.get("id")
                    dep_name = dep.get("nome")
                    dep_party = dep.get("siglaPartido")
                    dep_uf = dep.get("siglaUf")
                    
                    logger.info(f"[{idx}/{len(deputies)}] Processando despesas do deputado: {dep_name} (ID: {dep_id}, {dep_party}-{dep_uf})")
                    
                    for year in active_years:
                        logger.info(f"  -> Buscando despesas do ano {year}...")
                        expenses = get_expenses_for_deputy(dep_id, year, delay=args.delay)
                        
                        logger.info(f"  -> {len(expenses)} despesas encontradas.")
                        
                        # Adicionar metadados a cada registro de despesa
                        for expense in expenses:
                            # TODO(security): Validação opcional de formato de dados externos
                            expense["id_deputado"] = dep_id
                            expense["nome_deputado"] = dep_name
                            expense["sigla_partido"] = dep_party
                            expense["sigla_uf"] = dep_uf
                            expense["id_legislatura"] = leg
                            expense["ano_coleta"] = year
                            
                            # Escrever como uma linha JSON
                            f_out.write(json.dumps(expense, ensure_ascii=False) + "\n")
                            total_records += 1
                            
                        # Pequena pausa entre anos para o mesmo deputado
                        time.sleep(args.delay)
                        
                    # Pausa extra entre deputados
                    time.sleep(args.delay * 2)
                    
        logger.info(f"=== Coleta Local Concluída! Total de registros salvos: {total_records} ===")
        
        if total_records == 0:
            logger.warning("Nenhum registro de despesa coletado. Encerrando o pipeline sem enviar para o GCP.")
            return

        # Upload para o Google Cloud Storage
        destination_blob = f"raw_data/raw_expenses_{timestamp}.jsonl"
        gcs_uri = upload_file_to_gcs(local_file_path, args.bucket, destination_blob, project_id=project_id)
        
        # Carga no BigQuery
        load_gcs_to_bigquery(gcs_uri, args.dataset, args.table, project_id=project_id)
        
    finally:
        # Limpeza do arquivo temporário local
        if os.path.exists(local_file_path):
            logger.info(f"Limpando arquivo temporário local: {local_file_path}")
            os.remove(local_file_path)
            
    logger.info("=== Processo de Ingestão de Despesas Concluído com Sucesso! ===")

if __name__ == "__main__":
    main()
