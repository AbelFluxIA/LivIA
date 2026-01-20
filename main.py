import os
import httpx
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Lívia AI - Motor SantoTech")

# --- MODELOS DE DADOS ---
class SearchRequest(BaseModel):
    prompt: str

class ScrapeRequest(BaseModel):
    urls: List[str]

class WordPressRequest(BaseModel):
    title: str
    content: str
    status: str = "publish"

# --- CONFIGURAÇÕES E CREDENCIAIS ---
# O Jina Token e o WP Auth estão fixos como você pediu.
JINA_TOKEN = "jina_09991f5bacd4471198a7c0850a79a5afVz1dGynXMadC33SjPi_6GlV81PJM"
WP_AUTH = "Basic YWRtaW46bWRObERPZVVVd0Fkd1htZmt2MmRVSEFn"
WP_URL = "https://digitalfluxia.com.br/wp-json/wp/v2/posts"

# --- FUNÇÃO AUXILIAR IA (Busca e Ranking) ---
async def call_openai(system_prompt: str, user_content: str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise Exception("Falta a chave OPENAI_API_KEY no Railway.")
    
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, json=payload, headers=headers, timeout=30.0)
        return res.json()['choices'][0]['message']['content'].strip()

# --- ENDPOINT 1: BUSCA E RANKING ---
@app.post("/buscar-noticias")
async def buscar_noticias(req: SearchRequest):
    try:
        # 1. IA define a melhor query de busca
        search_query = await call_openai(
            "Você é Lívia, especialista em SEO. Transforme o desejo do usuário em uma query de busca de notícias potente para Google News. Apenas a query.",
            req.prompt
        )

        # 2. Busca no SerpApi
        serp_key = os.getenv("SERPAPI_API_KEY")
        serp_url = f"https://serpapi.com/search.json?engine=google_news&q={search_query}&gl=br&hl=pt&api_key={serp_key}"
        
        async with httpx.AsyncClient() as client:
            serp_res = await client.get(serp_url)
            news = serp_res.json().get("news_results", [])[:10]

        if not news:
            return {"noticias": [], "status": "Nada encontrado"}

        # 3. IA Escolhe as 3 melhores
        news_list_txt = "\n".join([f"ID {i}: {n['title']}" for i, n in enumerate(news)])
        rank_res = await call_openai(
            f"Com base em '{req.prompt}', escolha os IDs das 3 melhores notícias. Retorne apenas os IDs separados por vírgula (ex: 0, 2, 5).",
            news_list_txt
        )

        selected_ids = [int(i.strip()) for i in rank_res.split(",")]
        melhores = []
        for rank, idx in enumerate(selected_ids):
            if idx < len(news):
                n = news[idx]
                melhores.append({
                    "ranking": f"{rank + 1}ª Notícia",
                    "title": n.get("title"),
                    "source": n.get("source", {}).get("name"),
                    "link": n.get("link")
                })

        return {"noticias": melhores[:3], "query": search_query}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINT 2: SCRAPING MULTIPLO (JINA) ---
@app.post("/scraping")
async def scraping(req: ScrapeRequest):
    headers = {"Authorization": f"Bearer {JINA_TOKEN}"}
    all_text = ""
    async with httpx.AsyncClient() as client:
        # Faz todos os scrapings ao mesmo tempo (paralelo)
        tasks = [client.get(f"https://r.jina.ai/{url}", headers=headers, timeout=40.0) for url in req.urls]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, res in enumerate(responses):
            if isinstance(res, Exception):
                all_content = f"\n[Erro ao ler notícia {i+1}]\n"
            else:
                all_content = f"\n--- CONTEÚDO FONTE {i+1} ---\n{res.text}\n"
            all_text += all_content

    return {"texto_bruto": all_text}

# --- ENDPOINT 3: POSTAR NO WORDPRESS ---
@app.post("/publicar")
async def publicar(req: WordPressRequest):
    headers = {"Authorization": WP_AUTH, "Content-Type": "application/json"}
    payload = {
        "title": req.title,
        "content": req.content,
        "status": req.status
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(WP_URL, headers=headers, json=payload)
        if res.status_code not in [200, 201]:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return {"status": "sucesso", "link": res.json().get("link")}

@app.get("/")
def home():
    return {"status": "Lívia AI Engine Online"}
