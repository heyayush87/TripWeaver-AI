from tavily import TavilyClient

from dotenv import load_dotenv
import os

load_dotenv()

client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

def tavily_search(query: str, limit: int = 5):
    """
    Search for a query using the Tavily API.

    Args:
        query (str): The search query.
        limit (int): The maximum number of results to return.
    """
    response = client.search(query=query, max_results=limit)

    result=[]

    for i,r in enumerate(response["results"],1):
        title=r.get("title","unknown")
        url=r.get("url","")
        snippet=r.get("content","").strip()

        #keep only the first 300 characters to avoid wall-of-text
        if len(snippet)>300:
            snippet=snippet[:300].rsplit(" ",1)[0]+"..."

        result.append(f"{i}. {title}\n{url}\n{snippet}\n")
    return "\n\n".join(result)



