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
import uvicorn

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("SearchAppLogger")

SOLR_URL = os.getenv("SOLR_URL")
JSON_FILE_PATH = os.getenv("JSON_FILE_PATH", "data.json")
RESULTS_PER_PAGE = 10

app = FastAPI()

# Static files and templates setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class SolrRepository:
    def __init__(self, solr_url):
        self.solr = pysolr.Solr(solr_url, always_commit=True) if solr_url else None

    def _build_query(self, query: str) -> str:
        """
        Build a Solr query string for the given query and predefined searchable fields.

        Args:
            query (str): The search query.

        Returns:
            str: The constructed Solr query string.
        """
        searchable_fields = ["title", "description", "userEmail", "channelTitle"]
        return " OR ".join([f"{field}:{query}" for field in searchable_fields])

    def search(self, query: str, fields: Optional[List[str]] = None, start: int = 0):
        """
        Search across the specified fields or default to all fields if not specified.

        Args:
            query (str): The search query.
            fields (Optional[List[str]]): List of fields to return in the results.
            start (int): Starting index for pagination.

        Returns:
            List[Dict]: A list of documents that match the query.
        """
        if not self.solr:
            raise RuntimeError("Solr is not configured.")

        try:
            field_list = ",".join(fields) if fields else "*"
            solr_query = self._build_query(query)
            results = self.solr.search(solr_query, fl=field_list, start=start, rows=RESULTS_PER_PAGE)
            return [doc for doc in results]
        except Exception as e:
            logger.error("Error searching Solr: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Solr search failed.")

    def get_total_results(self, query: str) -> int:
        """
        Returns the total number of results for the query.

        Args:
            query (str): The search query.

        Returns:
            int: Total number of matching results.
        """
        if not self.solr:
            raise RuntimeError("Solr is not configured.")

        try:
            # Build the Solr query
            solr_query = self._build_query(query)

            # Fetch the total count of results
            results = self.solr.search(solr_query, rows=0)  # rows=0 to fetch only the count
            return results.hits
        except Exception as e:
            logger.error("Error fetching total results from Solr: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="Solr total results count failed.")



class JsonRepository:
    def __init__(self, filename):
        self.filename = filename

    def search(self, query: str, fields: Optional[List[str]] = None, start: int = 0):
        try:
            with open(self.filename, "r") as f:
                data = json.load(f)

            results = [
                {field: item[field] for field in fields} if fields else item
                for item in data if query.lower() in json.dumps(item).lower()
            ]
            return results[start: start + RESULTS_PER_PAGE]
        except Exception as e:
            logger.error("Error searching JSON file: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="JSON search failed.")

    def get_total_results(self, query: str) -> int:
        """Returns the total number of results for the query."""
        try:
            with open(self.filename, "r") as f:
                data = json.load(f)

            results = [item for item in data if query.lower() in json.dumps(item).lower()]
            return len(results)
        except Exception as e:
            logger.error("Error counting total results in JSON file: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail="JSON total results count failed.")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """
    Render the home page with the search bar.
    """
    return templates.TemplateResponse("single_page.html", {"request": request})

@app.get("/api/search")
def search(
    query: str = Query(..., description="Search query"),
    source: str = Query("json", description="Data source: 'solr' or 'json'"),
    fields: Optional[List[str]] = Query(None, description="Fields to include in results"),
    page: int = Query(1, description="Page number for pagination")
):
    """
    API endpoint to query data from Solr or JSON file.

    Parameters:
    - `query`: The search query.
    - `source`: Data source ('solr' or 'json').
    - `fields`: Optional list of fields to include in the response.
    - `page`: Page number for pagination.
    """
    start = (page - 1) * RESULTS_PER_PAGE

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

    # Get search results and total results count
    results = repository.search(query, fields, start=start)
    total_results = repository.get_total_results(query)  # Implement this in repositories
    total_pages = (total_results // RESULTS_PER_PAGE) + (1 if total_results % RESULTS_PER_PAGE > 0 else 0)

    return {
        "results": results,
        "page": page,
        "total_pages": total_pages,
        "total_results": total_results
    }



def main():
    uvicorn.run(app, host="0.0.0.0", port=8985)