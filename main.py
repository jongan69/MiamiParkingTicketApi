#!/usr/bin/env python3
"""
Miami-Dade Parking Search API -> Enhanced JSON with detailed citation info
- Gets basic citation information from search results
- Fetches detailed information from individual citation pages
- Includes violation details, vehicle details, and payment information
- Exposed as a Flask API with GET endpoint
- Performance optimized with concurrent requests and session reuse
"""

import json
import time
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import threading
import os

app = Flask(__name__)

BASE_URL = "https://www2.miamidadeclerk.gov/payparking/parkingSearch.aspx"

# Global session for reuse across requests
_session_lock = threading.Lock()
_global_session = None

def get_global_session():
    """Get or create a global session for reuse."""
    global _global_session
    with _session_lock:
        if _global_session is None:
            _global_session = requests.Session()
            _global_session.headers.update({
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": BASE_URL,
                "Origin": "https://www2.miamidadeclerk.gov",
            })
        return _global_session

# ------------------ Utilities ------------------

@lru_cache(maxsize=128)
def collect_form_fields_cached(soup_text: str) -> dict:
    """Cached version of collect_form_fields for repeated form structures."""
    soup = BeautifulSoup(soup_text, "html.parser")
    return collect_form_fields(soup)

def collect_form_fields(soup: BeautifulSoup) -> dict:
    """Collect *all* form fields. Keeps ASP.NET happy on postbacks."""
    data = {}
    # Use more efficient selectors
    for inp in soup.select('input[name]'):
        name = inp["name"]
        t = (inp.get("type") or "").lower()
        if t in ("checkbox", "radio"):
            if inp.has_attr("checked"):
                data[name] = inp.get("value", "on")
        else:
            data[name] = inp.get("value", "")
    
    # Optimize select queries
    for sel in soup.select('select[name]'):
        name = sel["name"]
        opt = sel.find("option", selected=True) or sel.find("option")
        if opt:
            data[name] = opt.get("value", opt.get_text(strip=True))
    
    for ta in soup.select('textarea[name]'):
        data[ta["name"]] = ta.get_text()
    return data

def extract_hidden_fields(soup: BeautifulSoup) -> dict:
    """Grab essential ASP.NET state fields."""
    def val(i):
        el = soup.find("input", id=i)
        return el["value"] if el and el.has_attr("value") else ""
    return {
        "__VIEWSTATE": val("__VIEWSTATE"),
        "__EVENTVALIDATION": val("__EVENTVALIDATION"),
        "__VIEWSTATEGENERATOR": val("__VIEWSTATEGENERATOR"),
    }

def postback(session: requests.Session, soup: BeautifulSoup, event_target: str, event_argument: str = "", max_retries: int = 3):
    """
    Perform a postback with the given __EVENTTARGET, preserving all fields.
    Returns the new BeautifulSoup and the raw HTML.
    """
    for attempt in range(max_retries):
        try:
            data = collect_form_fields(soup)
            data.update(extract_hidden_fields(soup))
            data["__EVENTTARGET"] = event_target
            data["__EVENTARGUMENT"] = event_argument
            
            # Reduced delay for better performance
            if attempt > 0:
                time.sleep(0.5)  # Reduced from 2 seconds
            
            r = session.post(BASE_URL, data=data, timeout=30)  # Reduced timeout
            r.raise_for_status()
            return BeautifulSoup(r.text, "html.parser"), r.text
        except requests.exceptions.Timeout:
            if attempt == max_retries - 1:
                raise
            print(f"[retry {attempt + 1}/{max_retries}] Timeout, retrying...")
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            print(f"[retry {attempt + 1}/{max_retries}] Request failed: {e}, retrying...")
    
    raise Exception(f"Failed after {max_retries} attempts")

# ------------------ Parsing helpers ------------------

def find_results_table(soup: BeautifulSoup):
    """
    Find the citations table by checking its header text.
    Looks for headers containing: Citation, Date Issued, Status, Amount Due.
    """
    # Optimize table search with more specific selectors
    for table in soup.find_all("table"):
        headers = [th.get_text(strip=True).lower() for th in table.find_all("th")]
        if not headers:
            continue
        needed = {"citation", "date issued", "status", "amount due"}
        if needed.issubset(set(headers)):
            return table
    return None

def parse_main_rows(results_table: BeautifulSoup):
    """
    Parse the results table into rows with summary data and expand links.
    Uses header mapping to avoid relying on column order.
    """
    rows = []
    trs = results_table.find_all("tr")
    if len(trs) < 2:
        return rows

    header_cells = [th.get_text(strip=True) for th in trs[0].find_all("th")]
    hmap = {h.lower(): i for i, h in enumerate(header_cells)}
    idx_plus   = hmap.get("more info", 0)
    idx_cit    = hmap.get("citation", 1)
    idx_date   = hmap.get("date issued", 2)
    idx_status = hmap.get("status", 3)
    idx_amount = hmap.get("amount due", 4)

    for tr in trs[1:]:
        tds = tr.find_all("td")
        if len(tds) < max(idx_amount, idx_status, idx_date, idx_cit, idx_plus) + 1:
            continue

        # expand link in first column
        expand_a = tds[idx_plus].find("a", href=True)
        expand_target = None
        if expand_a and "__doPostBack" in expand_a["href"]:
            parts = expand_a["href"].split("'")
            if len(parts) >= 2:
                expand_target = parts[1]

        citation_text = tds[idx_cit].get_text(strip=True)
        if not citation_text:
            continue

        rows.append({
            "Citation": citation_text,
            "Date Issued": tds[idx_date].get_text(strip=True),
            "Status": tds[idx_status].get_text(strip=True),
            "Amount Due": tds[idx_amount].get_text(strip=True),
            "_expand_target": expand_target
        })
    return rows

def parse_citation_details(soup: BeautifulSoup, citation_number: str) -> dict:
    """
    Parse detailed information from a citation detail page.
    """
    details = {}
    
    # Look for specific elements by ID that contain the detailed information
    id_mappings = {
        # Citation information
        "lb_Citation": "citation_number",
        "lb_Tag": "tag_number", 
        "lb_State": "state",
        
        # Date and amount information
        "lb_IssueDateTime": "issue_date_time",
        "lb_amountdue": "amount_due_now",
        "lb_duedate": "due_date", 
        "lb_amountdueafter": "amount_due_after_due_date",
        "lb_Status": "status",
        
        # Violation information
        "lb_Violation": "violation_type",
        "lb_location": "location",
        "lb_municipality": "municipality",
        
        # Vehicle details
        "lb_carmake": "vehicle_make",
        "lb_carstyle": "vehicle_style", 
        "lb_color": "vehicle_color",
    }
    
    # Optimize element search with more efficient selectors
    for element_id, field_name in id_mappings.items():
        element = soup.find("span", id=element_id)
        if element:
            details[field_name] = element.get_text(strip=True)
    
    # Also look for any table-based information as a fallback
    tables = soup.find_all("table", class_="table table-bordered mb-0")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key and value:
                    # Clean up the key name
                    clean_key = key.lower().replace(' ', '_').replace('/', '_').replace('&', 'and')
                    details[f"table_{clean_key}"] = value
    

    
    return details

# ------------------ Optimized main flow ------------------

def fetch_citation_details_optimized(session: requests.Session, citation_number: str, base_form_data: dict = None) -> dict:
    """
    Fetch detailed information for a specific citation using the citation search.
    Optimized version that reuses form data when possible.
    """
    if base_form_data:
        # Reuse form data from the main search
        data = base_form_data.copy()
        data["__EVENTTARGET"] = "ctl00$ContentPlaceHolder1$btnSubmit_CitSearch"
        data["__EVENTARGUMENT"] = ""
        data["ctl00$ContentPlaceHolder1$txtcitn"] = citation_number
        data["ctl00$ContentPlaceHolder1$txtTag"] = ""
        
        # Keep expected fields if present
        if "ctl00$ContentPlaceHolder1$hfTab" in data:
            data["ctl00$ContentPlaceHolder1$hfTab"] = "citation"
        if "ctl00$ContentPlaceHolder1$DropDownState" in data:
            data["ctl00$ContentPlaceHolder1$DropDownState"] = "FL"
    else:
        # Fallback to original method if no base form data
        r = session.get(BASE_URL, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        
        data = collect_form_fields(soup)
        data.update(extract_hidden_fields(soup))
        data["__EVENTTARGET"] = "ctl00$ContentPlaceHolder1$btnSubmit_CitSearch"
        data["__EVENTARGUMENT"] = ""
        data["ctl00$ContentPlaceHolder1$txtcitn"] = citation_number
        
        if "ctl00$ContentPlaceHolder1$hfTab" in data:
            data["ctl00$ContentPlaceHolder1$hfTab"] = "citation"
        if "ctl00$ContentPlaceHolder1$txtTag" in data:
            data["ctl00$ContentPlaceHolder1$txtTag"] = ""
        if "ctl00$ContentPlaceHolder1$DropDownState" in data:
            data["ctl00$ContentPlaceHolder1$DropDownState"] = "FL"
    
    # Submit the citation search
    r2 = session.post(BASE_URL, data=data, timeout=30)
    r2.raise_for_status()
    soup = BeautifulSoup(r2.text, "html.parser")
    
    # Parse the detailed information
    return parse_citation_details(soup, citation_number)

def fetch_citation_details_worker(args):
    """Worker function for concurrent citation detail fetching."""
    session, citation_number, base_form_data, row = args
    
    # Extract row data early to avoid scope issues
    citation = row["Citation"]
    date_issued = row["Date Issued"]
    status = row["Status"]
    amount_due = row["Amount Due"]
    
    try:
        details = fetch_citation_details_optimized(session, citation_number, base_form_data)
        
        # Start with basic information
        citation_info = {
            "Citation": citation,
            "Date Issued": date_issued,
            "Status": status,
            "Amount Due": amount_due,
        }
        
        # Add payment context
        if status == "OPEN":
            citation_info["needs_payment"] = True
            citation_info["payment_required"] = amount_due
        else:
            citation_info["needs_payment"] = False
            citation_info["payment_required"] = "$0.00"
        
        if details:
            # Clean up the details by removing table_ prefix and organizing them
            cleaned_details = {}
            for key, value in details.items():
                if key.startswith('table_'):
                    # Remove table_ prefix and clean up the key
                    clean_key = key[6:]  # Remove 'table_' prefix
                    cleaned_details[clean_key] = value
                else:
                    cleaned_details[key] = value
            citation_info.update(cleaned_details)
            
            # Ensure due_date is properly included
            if 'due_date' not in citation_info:
                citation_info['due_date'] = "Not available"
                citation_info['due_date_estimated'] = False
        
        return citation_info
    except Exception as e:
        print(f"  ✗ Error fetching details for citation {citation_number}: {e}")
        # Return basic info even if details fail
        return {
            "Citation": citation,
            "Date Issued": date_issued,
            "Status": status,
            "Amount Due": amount_due,
            "needs_payment": status == "OPEN",
            "payment_required": amount_due if status == "OPEN" else "$0.00",
            "due_date": "Not available",
            "due_date_estimated": False,
            "error": str(e)
        }

def fetch_all_citations(tag_number: str) -> dict:
    try:
        session = get_global_session()

        # 1) GET initial page
        print(f"  Step 1: Getting initial page...")
        r = session.get(BASE_URL, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # 2) Build form for search
        print(f"  Step 2: Building search form...")
        data = collect_form_fields(soup)
        data.update(extract_hidden_fields(soup))
        data["__EVENTTARGET"] = "ctl00$ContentPlaceHolder1$btnSubmit_TagSearch"
        data["__EVENTARGUMENT"] = ""
        data["ctl00$ContentPlaceHolder1$txtTag"] = tag_number.strip().upper()

        # Keep expected fields if present
        if "ctl00$ContentPlaceHolder1$DropDownState" in data and not data["ctl00$ContentPlaceHolder1$DropDownState"]:
            data["ctl00$ContentPlaceHolder1$DropDownState"] = "FL"
        if "ctl00$ContentPlaceHolder1$hfTab" in data:
            data["ctl00$ContentPlaceHolder1$hfTab"] = "tagplate"
        if "ctl00$ContentPlaceHolder1$txtcitn" in data:
            data["ctl00$ContentPlaceHolder1$txtcitn"] = ""

        # 3) POST search
        print(f"  Step 3: Submitting search...")
        r2 = session.post(BASE_URL, data=data, timeout=30)
        r2.raise_for_status()
        soup = BeautifulSoup(r2.text, "html.parser")

        # 4) Parse main results
        print(f"  Step 4: Parsing results...")
        table = find_results_table(soup)
        if not table:
            msg = soup.select_one("#lblErrorTag")
            return {
                "tag_number": tag_number.strip().upper(),
                "summary": {
                    "total_citations": 0,
                    "total_paid": 0,
                    "total_open": 0,
                    "total_due": None
                },
                "paid_citations": [],
                "open_citations": [],
                "message": msg.get_text(strip=True) if msg else "No results table found."
            }

        rows = parse_main_rows(table)
        total_due_el = soup.select_one("#lbl_totaldue_vTag")
        total_due = total_due_el.get_text(strip=True) if total_due_el else None

        # 5) Fetch detailed information for each citation using concurrent requests
        citations = []
        
        print(f"Found {len(rows)} citations. Fetching detailed information concurrently...")
        
        if len(rows) == 0:
            return {
                "tag_number": tag_number.strip().upper(),
                "summary": {
                    "total_citations": 0,
                    "total_paid": 0,
                    "total_open": 0,
                    "total_due": total_due
                },
                "paid_citations": [],
                "open_citations": []
            }
        
        # Use concurrent requests for better performance
        max_workers = min(5, len(rows))  # Limit concurrent requests to be respectful
        print(f"  Using {max_workers} concurrent workers...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Prepare arguments for workers
            worker_args = []
            for row in rows:
                worker_args.append((session, row["Citation"], data, row))
            
            # Submit all tasks
            future_to_citation = {}
            for args in worker_args:
                future = executor.submit(fetch_citation_details_worker, args)
                future_to_citation[future] = args[1]  # citation number
            
            # Collect results as they complete
            for future in as_completed(future_to_citation):
                citation_number = future_to_citation[future]
                try:
                    citation_info = future.result()
                    citations.append(citation_info)
                    print(f"  ✓ Completed citation {citation_number}")
                except Exception as e:
                    print(f"  ✗ Exception for citation {citation_number}: {e}")
                    # Add basic info even if details fail
                    citations.append({
                        "Citation": citation_number,
                        "Date Issued": "Unknown",
                        "Status": "Unknown",
                        "Amount Due": "Unknown",
                        "needs_payment": False,
                        "payment_required": "$0.00",
                        "error": str(e)
                    })

        # Sort citations by citation number to maintain consistent order
        citations.sort(key=lambda x: x.get("Citation", ""))

        # Separate citations into paid and open
        paid_citations = [citation for citation in citations if not citation.get("needs_payment", False)]
        open_citations = [citation for citation in citations if citation.get("needs_payment", False)]

        # Calculate totals
        total_open = len(open_citations)
        total_paid = len(paid_citations)

        return {
            "tag_number": tag_number.strip().upper(),
            "summary": {
                "total_citations": len(citations),
                "total_paid": total_paid,
                "total_open": total_open,
                "total_due": total_due
            },
            "paid_citations": paid_citations,
            "open_citations": open_citations
        }
    except Exception as e:
        print(f"Error in fetch_all_citations: {e}")
        import traceback
        traceback.print_exc()
        raise

# ------------------ Flask API Routes ------------------

@app.route('/api/parking-tickets', methods=['GET'])
def get_parking_tickets():
    """
    GET endpoint to fetch parking ticket information by tag number.
    
    Query Parameters:
    - tag: The license plate tag number (required)
    
    Returns:
    - JSON response with parking ticket information
    """
    print(f"API request received for tag: {request.args.get('tag')}")
    
    # Get tag number from query parameter
    tag = request.args.get('tag')
    
    if not tag:
        print("Error: Missing tag parameter")
        return jsonify({
            "error": "Missing required parameter 'tag'",
            "usage": "Use /api/parking-tickets?tag=YOUR_TAG_NUMBER"
        }), 400
    
    try:
        print(f"Starting to fetch citations for tag: {tag}")
        # Fetch the parking ticket data
        result = fetch_all_citations(tag)
        print(f"Successfully fetched {result.get('count', 0)} citations")
        return jsonify(result)
    except Exception as e:
        print(f"Error fetching parking ticket data: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "error": "Failed to fetch parking ticket data",
            "message": str(e)
        }), 500

@app.route('/', methods=['GET'])
def home():
    """
    Home endpoint with API documentation.
    """
    return jsonify({
        "name": "Miami Beach Parking Tickets API",
        "description": "API to fetch parking ticket information from Miami-Dade Clerk's office",
        "endpoints": {
            "/api/parking-tickets": {
                "method": "GET",
                "description": "Fetch parking tickets by license plate tag number",
                "parameters": {
                    "tag": "License plate tag number (required)"
                },
                "example": "/api/parking-tickets?tag=ABC123"
            }
        },
        "usage": "Make a GET request to /api/parking-tickets?tag=YOUR_TAG_NUMBER"
    })

# ------------------ CLI (kept for backward compatibility) ------------------

if __name__ == "__main__":
    
    # Check if running as CLI or API
    if len(sys.argv) > 1 and sys.argv[1] == '--api':
        # Run as API
        try:
            print("Starting Miami Beach Parking Tickets API...")
            print("API will be available at: http://localhost:3000")
            print("Example: http://localhost:3000/api/parking-tickets?tag=ABC123")
            print("Press Ctrl+C to stop the server")
            
            # Check if this is production or development
            is_production = os.environ.get('FLASK_ENV') == 'production'
            
            if is_production:
                print("Running in PRODUCTION mode")
                # Production settings
                app.config['DEBUG'] = False
                app.config['TESTING'] = False
                # Use gunicorn or other WSGI server in production
                print("For production, use: gunicorn -w 4 -b 0.0.0.0:3000 wsgi:app")
            else:
                print("Running in DEVELOPMENT mode")
                # Development settings
                app.config['DEBUG'] = True
                app.config['TESTING'] = False
            
            # Start the server
            app.run(debug=not is_production, host='0.0.0.0', port=3000, use_reloader=False)
        except Exception as e:
            print(f"Error starting Flask server: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Run as CLI (original behavior)
        # Get tag number from command line arguments
        if len(sys.argv) > 1:
            tag = sys.argv[1]
        else:
            # Prompt user for tag number if not provided
            tag = input("Enter tag number: ").strip()
            if not tag:
                print("Error: Tag number is required.")
                sys.exit(1)
        
        result = fetch_all_citations(tag)
        print(json.dumps(result, indent=2, ensure_ascii=False))
