# -*- coding: utf-8 -*-
import os
import json
import logging
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import List, Optional
import pysolr
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("SearchAppLogger")

# Constants
SOLR_URL = os.getenv("SOLR_URL")
JSON_FILE_PATH = os.getenv("JSON_FILE_PATH", "data.json")

# FastAPI app
app = FastAPI()

# Static files and templates setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class SolrRepository:
    def __init__(self, solr_url):
        self.solr = pysolr.Solr(solr_url, always_commit=True) if solr_url else None

    def search(self, query: str, fields: Optional[List[str]] = None):
        if not self.solr:
            raise RuntimeError("Solr is not configured.")

        try:
            solr_query = f"{query}"
            results = self.solr.search(solr_query, fl=",".join(fields) if fields else None)
            return [doc for doc in results]
        except Exception as e:
            logger.error("Error searching Solr: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Solr search failed.")

class JsonRepository:
    def __init__(self, filename):
        self.filename = filename

    def search(self, query: str, fields: Optional[List[str]] = None):
        try:
            with open(self.filename, "r") as f:
                data = json.load(f)

            results = [
                {field: item[field] for field in fields} if fields else item
                for item in data if query.lower() in json.dumps(item).lower()
            ]
            return results
        except Exception as e:
            logger.error("Error searching JSON file: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="JSON search failed.")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """
    Render the home page with a search bar.
    """
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/search")
def search(
    query: str = Query(..., description="Search query"),
    source: str = Query("json", description="Data source: 'solr' or 'json'"),
    fields: Optional[List[str]] = Query(None, description="Fields to include in results"),
    request: Request = None
):
    """
    Search endpoint to query data from Solr or JSON file.

    Parameters:
    - `query`: The search query.
    - `source`: Data source ('solr' or 'json').
    - `fields`: Optional list of fields to include in the response.
    """
    if source == "solr":
        if not SOLR_URL:
            raise HTTPException(status_code=500, detail="Solr is not configured.")

        repository = SolrRepository(SOLR_URL)
    elif source == "json":
        if not os.path.exists(JSON_FILE_PATH):
            raise HTTPException(status_code=500, detail="JSON file is not available.")

        repository = JsonRepository(JSON_FILE_PATH)
    else:
        raise HTTPException(status_code=400, detail="Invalid source. Use 'solr' or 'json'.")

    results = repository.search(query, fields)
    if request:
        return templates.TemplateResponse("results.html", {"request": request, "results": results, "query": query})
    return {"results": results}
