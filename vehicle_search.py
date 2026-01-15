"""
Módulo de busca e processamento de dados de veículos
Busca em uma base de dados de veículos por Marca, Modelo, Ano, Código FIPE, etc.
"""

import json
import pandas as pd
from typing import List, Dict, Optional
from difflib import SequenceMatcher
import re


class VehicleDatabase:
    """Gerenciador de banco de dados de veículos"""
    
    def __init__(self, json_file: str = '/home/ubuntu/vehicle_database.json'):
        """Inicializar o banco de dados"""
        with open(json_file, 'r', encoding='utf-8') as f:
            self.vehicles = json.load(f)
        
        # Criar índices para busca rápida
        self._create_indexes()
    
    def _create_indexes(self):
        """Criar índices para busca otimizada"""
        self.by_fipe = {}
        self.by_brand = {}
        self.by_model = {}
        
        for vehicle in self.vehicles:
            # Índice por Código FIPE
            fipe = str(vehicle.get('Código Fipe', '')).strip()
            if fipe:
                self.by_fipe[fipe] = vehicle
            
            # Índice por Montadora (marca)
            brand = str(vehicle.get('Montadora', '')).strip().upper()
            if brand:
                if brand not in self.by_brand:
                    self.by_brand[brand] = []
                self.by_brand[brand].append(vehicle)
            
            # Índice por Modelo
            model = str(vehicle.get('Modelo', '')).strip().upper()
            if model:
                if model not in self.by_model:
                    self.by_model[model] = []
                self.by_model[model].append(vehicle)
    
    def search_by_fipe(self, fipe_code: str) -> Optional[Dict]:
        """Buscar veículo por Código FIPE"""
        fipe = str(fipe_code).strip()
        return self.by_fipe.get(fipe)
    
    def search_by_brand_and_model(self, brand: str, model: str, year: Optional[int] = None) -> List[Dict]:
        """Buscar veículos por Marca e Modelo"""
        brand_upper = brand.strip().upper()
        model_upper = model.strip().upper()
        
        results = []
        
        if brand_upper in self.by_brand:
            for vehicle in self.by_brand[brand_upper]:
                vehicle_model = str(vehicle.get('Modelo', '')).strip().upper()
                
                # Verificar se o modelo contém a busca
                if model_upper in vehicle_model or self._similarity(model_upper, vehicle_model) > 0.7:
                    # Se o ano foi fornecido, filtrar por ano
                    if year:
                        ano_inicial = vehicle.get('Ano inicial')
                        ano_final = vehicle.get('Ano final')
                        if ano_inicial and ano_final:
                            try:
                                if int(ano_inicial) <= year <= int(ano_final):
                                    results.append(vehicle)
                            except (ValueError, TypeError):
                                results.append(vehicle)
                        else:
                            results.append(vehicle)
                    else:
                        results.append(vehicle)
        
        return results
    
    def search_by_brand(self, brand: str) -> List[Dict]:
        """Buscar todos os veículos de uma marca"""
        brand_upper = brand.strip().upper()
        return self.by_brand.get(brand_upper, [])
    
    def _similarity(self, a: str, b: str) -> float:
        """Calcular similaridade entre duas strings"""
        return SequenceMatcher(None, a, b).ratio()
    
    def get_all_brands(self) -> List[str]:
        """Obter lista de todas as marcas"""
        return sorted(list(self.by_brand.keys()))
    
    def get_categories(self) -> List[str]:
        """Obter lista de categorias únicas"""
        categories = set()
        for vehicle in self.vehicles:
            cat = vehicle.get('Categoria')
            if cat and str(cat).strip() != '':
                categories.add(str(cat).strip())
        return sorted(list(categories))
    
    def get_quotas(self) -> List[str]:
        """Obter lista de cotas únicas"""
        quotas = set()
        for vehicle in self.vehicles:
            quota = vehicle.get('Cota')
            if quota and str(quota).strip() != '':
                quotas.add(str(quota).strip())
        return sorted(list(quotas))


class VehicleSearchParser:
    """Parser para processar consultas de veículos"""
    
    def __init__(self, db: VehicleDatabase):
        self.db = db
    
    def parse_query(self, query: str) -> Dict:
        """
        Parser de consulta estruturada
        Extrai: Marca, Modelo, Ano, Código FIPE
        """
        result = {
            'brand': None,
            'model': None,
            'year': None,
            'fipe_code': None,
            'raw_query': query
        }
        
        # Padrão para Código FIPE (6 dígitos + hífen + 1 dígito)
        fipe_pattern = r'\d{6}-\d'
        fipe_match = re.search(fipe_pattern, query)
        if fipe_match:
            result['fipe_code'] = fipe_match.group(0)
        
        # Padrão para ano (4 dígitos entre 1900 e 2100)
        year_pattern = r'\b(19|20)\d{2}\b'
        year_match = re.search(year_pattern, query)
        if year_match:
            result['year'] = int(year_match.group(0))
        
        # Extrair marca e modelo por palavras-chave
        # Procurar por marcas conhecidas
        brands = self.db.get_all_brands()
        for brand in brands:
            if brand.lower() in query.lower():
                result['brand'] = brand
                break
        
        return result
    
    def search(self, query: str) -> List[Dict]:
        """Executar busca baseada em consulta"""
        parsed = self.parse_query(query)
        
        # Se temos Código FIPE, buscar por ele
        if parsed['fipe_code']:
            vehicle = self.db.search_by_fipe(parsed['fipe_code'])
            if vehicle:
                return [vehicle]
        
        # Se temos marca e modelo
        if parsed['brand']:
            # Extrair modelo da query removendo a marca
            query_without_brand = query.replace(parsed['brand'], '', 1).strip()
            results = self.db.search_by_brand_and_model(
                parsed['brand'],
                query_without_brand,
                parsed['year']
            )
            if results:
                return results
        
        # Se não encontrou, retornar vazio
        return []


def format_vehicle_response(vehicle: Dict) -> str:
    """Formatar resposta de veículo em texto legível"""
    response = f"""
📋 *Informações do Veículo*

🏷️ *Código FIPE:* {vehicle.get('Código Fipe', 'N/A')}
🚗 *Montadora:* {vehicle.get('Montadora', 'N/A')}
📝 *Modelo:* {vehicle.get('Modelo', 'N/A')}
🎯 *Tipo:* {vehicle.get('Tipo veículo', 'N/A')}
📅 *Anos:* {vehicle.get('Ano inicial', 'N/A')} - {vehicle.get('Ano final', 'N/A')}

💰 *CATEGORIA:* {vehicle.get('Categoria', 'N/A')}
📊 *COTA:* {vehicle.get('Cota', 'N/A')}
"""
    return response.strip()


if __name__ == '__main__':
    # Teste do módulo
    db = VehicleDatabase()
    parser = VehicleSearchParser(db)
    
    print("✓ Banco de dados carregado com sucesso!")
    print(f"Total de veículos: {len(db.vehicles)}")
    print(f"Marcas: {len(db.get_all_brands())}")
    print(f"Categorias: {len(db.get_categories())}")
    print(f"Cotas: {len(db.get_quotas())}")
    
    # Teste de busca
    print("\n--- Teste de Busca ---")
    test_queries = [
        "002107-5",  # Código FIPE
        "Toyota Hilux 2015",
        "Ford Fusion 2011"
    ]
    
    for query in test_queries:
        print(f"\nBuscando: {query}")
        results = parser.search(query)
        if results:
            for vehicle in results:
                print(format_vehicle_response(vehicle))
        else:
            print("Nenhum resultado encontrado")
