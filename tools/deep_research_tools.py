from google import genai
from google.genai import types
import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

def perform_deep_research(topic_or_question: str) -> str:
    """
    Executes an autonomous deep-dive web research loop on a complex topic.
    It performs multiple searches, crawls sites, and synthesizes 
    a comprehensive long-form summary of its findings.
    
    Use this when a profound or nuanced level of detail is required.
    Warning: This process takes 15-30 seconds to execute.
    """
    client = genai.Client()
    model = "gemini-2.5-flash"
    
    # 1. Break the topic into 3 search queries
    resp = client.models.generate_content(
        model=model,
        contents=f"Generate exactly 3 extremely distinct Google search queries that would help thoroughly research this topic from different angles: '{topic_or_question}'. Return ONLY a Python list of the 3 string queries, nothing else."
    )
    
    try:
        import ast
        queries = ast.literal_eval(resp.text.strip().replace('```python', '').replace('```', '').strip())
    except:
        queries = [topic_or_question]
        
    all_context = ""
    urls_visited = []
    
    # 2. Search and scrape
    for query in queries[:3]:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=2))
            for res in results:
                url = res.get('href')
                if not url or url in urls_visited:
                    continue
                urls_visited.append(url)
                
                # Scrape Content
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
                    page = requests.get(url, headers=headers, timeout=5)
                    soup = BeautifulSoup(page.content, 'html.parser')
                    for script in soup(["script", "style"]):
                        script.extract()
                    text = soup.get_text(separator=' ')
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = '\n'.join(chunk for chunk in chunks if chunk)
                    
                    # Store up to 3000 chars per page
                    all_context += f"\n--- Source: {url} ---\n" + text[:3000]
                except:
                    continue

    if not all_context.strip():
        return f"Failed to retrieve deep research data for '{topic_or_question}'."

    # 3. Final Synthesis
    synthesis_prompt = f"""
    You are a Deep Researcher AI. 
    Topic: {topic_or_question}
    
    Below is raw scraped context from various URLs. Synthesize a definitive, multi-paragraph brief 
    answering the user's topic comprehensively. Focus heavily on stats, numbers, and facts.
    
    RAW CONTEXT:
    {all_context[:20000]}
    """
    
    final_resp = client.models.generate_content(
        model=model,
        contents=synthesis_prompt,
        config=types.GenerateContentConfig(temperature=0.2)
    )
    
    return f"DEEP RESEARCH REPORT:\n\n{final_resp.text}\n\n[Sources: {', '.join(urls_visited)}]"

def get_deep_research_tools():
    return [perform_deep_research]
