"""
Bot WhatsApp para busca de categorias e cotas de veículos
Integrado com FastAPI e OpenAI para processamento de linguagem natural
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import os
import json
import logging
from typing import Optional
from vehicle_search import VehicleDatabase, VehicleSearchParser, format_vehicle_response
from openai import OpenAI

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializar FastAPI
app = FastAPI(title="WhatsApp Vehicle Bot")

# Inicializar banco de dados de veículos
db = VehicleDatabase()
parser = VehicleSearchParser(db)

# Inicializar cliente OpenAI
client = OpenAI()

# Configurações do WhatsApp (Meta Cloud API)
WHATSAPP_API_VERSION = "v18.0"
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "sua_chave_verificacao")

# URL base da API do WhatsApp
WHATSAPP_API_URL = f"https://graph.instagram.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"


def extract_vehicle_info_with_ai(user_message: str) -> dict:
    """
    Usar IA para extrair informações de veículos da mensagem do usuário
    """
    try:
        prompt = f"""
Você é um assistente especializado em extrair informações de veículos de mensagens de usuários.
Analise a seguinte mensagem e extraia as informações do veículo:

Mensagem: "{user_message}"

Responda em JSON com os seguintes campos:
- brand: marca do veículo (ex: Toyota, Ford, etc)
- model: modelo do veículo
- year: ano do veículo (se mencionado)
- fipe_code: código FIPE (se mencionado)
- query_type: tipo de busca ('fipe', 'brand_model', 'brand_only', 'unknown')

Exemplo de resposta:
{{"brand": "Toyota", "model": "Hilux", "year": 2015, "fipe_code": null, "query_type": "brand_model"}}

Responda APENAS com o JSON, sem explicações adicionais.
"""
        
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "Você é um assistente que extrai informações de veículos em JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        # Tentar fazer parse do JSON da resposta
        try:
            result = json.loads(response.choices[0].message.content)
            return result
        except json.JSONDecodeError:
            logger.warning(f"Falha ao fazer parse de JSON da IA: {response.choices[0].message.content}")
            return {"query_type": "unknown"}
            
    except Exception as e:
        logger.error(f"Erro ao chamar OpenAI: {e}")
        return {"query_type": "unknown"}


def search_vehicles(user_message: str) -> list:
    """
    Buscar veículos baseado na mensagem do usuário
    """
    # Extrair informações usando IA
    vehicle_info = extract_vehicle_info_with_ai(user_message)
    
    results = []
    
    # Se temos código FIPE
    if vehicle_info.get('fipe_code'):
        vehicle = db.search_by_fipe(vehicle_info['fipe_code'])
        if vehicle:
            results.append(vehicle)
    
    # Se temos marca e modelo
    elif vehicle_info.get('brand') and vehicle_info.get('model'):
        results = db.search_by_brand_and_model(
            vehicle_info['brand'],
            vehicle_info['model'],
            vehicle_info.get('year')
        )
    
    # Se temos apenas marca
    elif vehicle_info.get('brand'):
        results = db.search_by_brand(vehicle_info['brand'])
    
    # Fallback: tentar busca simples
    if not results:
        results = parser.search(user_message)
    
    return results


def format_whatsapp_response(vehicles: list) -> str:
    """
    Formatar resposta para WhatsApp
    """
    if not vehicles:
        return "❌ Nenhum veículo encontrado com os critérios informados.\n\nTente novamente com:\n- Código FIPE\n- Marca e Modelo\n- Marca e Ano"
    
    if len(vehicles) == 1:
        return format_vehicle_response(vehicles[0])
    
    # Se múltiplos resultados, mostrar resumo
    response = f"🔍 Encontrados {len(vehicles)} veículos:\n\n"
    for i, vehicle in enumerate(vehicles[:5], 1):  # Limitar a 5 resultados
        response += f"{i}. {vehicle.get('Montadora', 'N/A')} {vehicle.get('Modelo', 'N/A')}\n"
        response += f"   FIPE: {vehicle.get('Código Fipe', 'N/A')} | Cota: {vehicle.get('Cota', 'N/A')}\n\n"
    
    if len(vehicles) > 5:
        response += f"... e mais {len(vehicles) - 5} resultados"
    
    return response


def send_whatsapp_message(phone_number: str, message: str) -> bool:
    """
    Enviar mensagem via WhatsApp API
    """
    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.warning("WhatsApp credentials not configured. Message not sent.")
        return False
    
    try:
        import requests
        
        headers = {
            "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
        
        response = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"Message sent successfully to {phone_number}")
            return True
        else:
            logger.error(f"Failed to send message: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {e}")
        return False


@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Webhook de verificação do WhatsApp
    """
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if verify_token == VERIFY_TOKEN:
        logger.info("Webhook verified")
        return PlainTextResponse(challenge)
    else:
        logger.warning("Invalid verify token")
        raise HTTPException(status_code=403, detail="Invalid verify token")


@app.post("/webhook")
async def handle_webhook(request: Request):
    """
    Processar mensagens recebidas do WhatsApp
    """
    try:
        data = await request.json()
        
        # Log da requisição
        logger.info(f"Received webhook: {json.dumps(data, indent=2)}")
        
        # Verificar se é uma mensagem
        if data.get("object") == "whatsapp_business_account":
            entry = data.get("entry", [{}])[0]
            changes = entry.get("changes", [{}])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            
            if messages:
                message = messages[0]
                phone_number = message.get("from")
                message_text = message.get("text", {}).get("body", "")
                
                logger.info(f"Message from {phone_number}: {message_text}")
                
                # Buscar veículos
                vehicles = search_vehicles(message_text)
                
                # Formatar resposta
                response_text = format_whatsapp_response(vehicles)
                
                # Enviar resposta
                send_whatsapp_message(phone_number, response_text)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "vehicles_loaded": len(db.vehicles),
        "brands": len(db.get_all_brands()),
        "categories": len(db.get_categories())
    }


@app.get("/search")
async def search_endpoint(query: str):
    """
    Endpoint de busca para testes
    """
    vehicles = search_vehicles(query)
    response = format_whatsapp_response(vehicles)
    return {
        "query": query,
        "results_count": len(vehicles),
        "response": response,
        "vehicles": vehicles
    }


if __name__ == "__main__":
    import uvicorn
    
    # Carregar variáveis de ambiente do arquivo .env se existir
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    # Iniciar servidor
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
