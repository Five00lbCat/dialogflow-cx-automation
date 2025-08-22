import json
import re
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DialogflowUploader:
    def __init__(self, service_account_file: str, project_id: str, location: str, 
                 agent_id: str, dispatcher_url: str, dispatcher_header: Optional[str] = None):
        """Initialize the Dialogflow uploader with configuration."""
        self.service_account_file = service_account_file
        self.project_id = project_id
        self.location = location
        self.agent_id = agent_id
        self.dispatcher_url = dispatcher_url
        self.dispatcher_header = dispatcher_header
        
        # Setup API URLs
        self.api_prefix = f"https://{location}-dialogflow.googleapis.com/v3"
        self.base_url = f"{self.api_prefix}/projects/{project_id}/locations/{location}/agents/{agent_id}"
        
        # Setup authentication
        self.headers = self._auth_headers()
        
        # Cache for existing resources
        self.cache = {
            'flows': {},
            'intents': {},
            'pages': {},
            'webhooks': {}
        }
        
    def _auth_headers(self) -> Dict[str, str]:
        """Generate authentication headers."""
        credentials = service_account.Credentials.from_service_account_file(
            self.service_account_file, 
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        credentials.refresh(Request())
        return {
            'Authorization': f'Bearer {credentials.token}',
            'Content-Type': 'application/json'
        }
    
    def _refresh_auth(self):
        """Refresh authentication token."""
        self.headers = self._auth_headers()
    
    @staticmethod
    def slugify(s: str) -> str:
        """Convert string to valid Dialogflow identifier."""
        s = s.lower().strip()
        s = re.sub(r"\s+", "_", s)
        s = re.sub(r"[^a-z0-9_]", "", s)
        s = re.sub(r"_+", "_", s)
        return s.strip("_")
    
    def _api_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make API request with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(2 ** attempt)  # Exponential backoff
                
                response = requests.request(method, url, headers=self.headers, **kwargs)
                
                # Handle auth refresh
                if response.status_code == 401 and attempt < max_retries - 1:
                    logger.info("Refreshing authentication token...")
                    self._refresh_auth()
                    continue
                
                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 5))
                    logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                # Log error details for debugging
                if response.status_code == 400:
                    logger.error(f"Bad request details: {response.text}")
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
        
        return response
    
    def list_by_name(self, url: str, key: str) -> Dict:
        """List resources and index by display name."""
        resp = self._api_request('GET', url)
        return {item["displayName"]: item for item in resp.json().get(key, [])}
    
    def upsert_flow(self, display_name: str) -> str:
        """Create or update a flow."""
        # Check cache first
        if display_name in self.cache['flows']:
            return self.cache['flows'][display_name]
        
        flows = self.list_by_name(f"{self.base_url}/flows", "flows")
        
        if display_name in flows:
            resource_name = flows[display_name]["name"]
        else:
            resp = self._api_request('POST', f"{self.base_url}/flows", 
                                    json={"displayName": display_name})
            resource_name = resp.json()["name"]
        
        self.cache['flows'][display_name] = resource_name
        return resource_name
    
    def upsert_webhook(self, display_name: str, uri: str, headers_map: Optional[Dict] = None) -> str:
        """Create or update a webhook."""
        # Check cache
        cache_key = f"{display_name}::{uri}"
        if cache_key in self.cache['webhooks']:
            return self.cache['webhooks'][cache_key]
        
        hooks = self.list_by_name(f"{self.base_url}/webhooks", "webhooks")
        
        if display_name in hooks:
            name = hooks[display_name]["name"]
            logger.info(f"Webhook '{display_name}' already exists, using existing configuration")
        else:
            payload = {"displayName": display_name, "genericWebService": {"uri": uri}}
            if headers_map:
                payload["genericWebService"]["requestHeaders"] = headers_map
            
            resp = self._api_request('POST', f"{self.base_url}/webhooks", json=payload)
            name = resp.json()["name"]
        
        self.cache['webhooks'][cache_key] = name
        return name
    
    def upsert_intent(self, display_name: str, training_phrases: List[str], 
                     intents_index: Optional[Dict] = None) -> str:
        """Create or update an intent."""
        if not intents_index:
            intents_index = self.list_by_name(f"{self.base_url}/intents", "intents")
        
        body = {
            "displayName": display_name,
            "trainingPhrases": [
                {"repeatCount": 1, "parts": [{"text": tp}]} 
                for tp in training_phrases if tp
            ]
        }
        
        if display_name in intents_index:
            intent_name = intents_index[display_name]["name"]
            self._api_request('PATCH', f"{self.api_prefix}/{intent_name}",
                            params={"updateMask": "trainingPhrases"},
                            json={"trainingPhrases": body["trainingPhrases"]})
        else:
            resp = self._api_request('POST', f"{self.base_url}/intents", json=body)
            intent_name = resp.json()["name"]
        
        return intent_name
    
    def upsert_page(self, flow_url: str, display_name: str, prompts: List[str], 
                   chips: List[str], pages_index: Optional[Dict] = None, 
                   is_end_state: bool = False) -> str:
        """Create or update a page, marking it as an end state if specified."""
        if not pages_index:
            pages_index = self.list_by_name(f"{flow_url}/pages", "pages")
        
        # Build entry fulfillment
        messages = []
        if prompts:
            messages.append({"text": {"text": prompts}})
        if chips:
            chip_objs = [{"text": c} for c in chips]
            messages.append({
                "payload": {
                    "richContent": [[{"type": "chips", "options": chip_objs}]]
                }
            })
        
        body = {
            "displayName": display_name,
            "entryFulfillment": {"messages": messages}
        }
        
        if display_name in pages_index:
            page_name = pages_index[display_name]["name"]
            self._api_request('PATCH', f"{self.api_prefix}/{page_name}",
                            params={"updateMask": "entryFulfillment"},
                            json={"entryFulfillment": body["entryFulfillment"]})
        else:
            resp = self._api_request('POST', f"{flow_url}/pages", json=body)
            page_name = resp.json()["name"]
        
        return page_name
    
    def patch_flow_start_route(self, flow_url: str, first_page_name: str):
        """Set the flow's start route to the first page."""
        pages_resp = self._api_request('GET', f"{flow_url}/pages")
        pages = pages_resp.json().get("pages", [])
        page_map = {p["displayName"]: p["name"] for p in pages}
        
        target = page_map.get(first_page_name)
        if not target:
            raise RuntimeError(f"First page '{first_page_name}' not found in flow.")
        
        body = {"transitionRoutes": [{"condition": "true", "targetPage": target}]}
        self._api_request('PATCH', flow_url,
                        params={"updateMask": "transitionRoutes"}, 
                        json=body)
    
    def upload_single_flow(self, json_path: str, flow_name: Optional[str] = None) -> Tuple[bool, str]:
        """Upload a single flow from JSON file."""
        try:
            # Load JSON
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Determine flow name
            if not flow_name:
                flow_name = Path(json_path).stem.replace("dialogflow_", "")
                flow_name = flow_name.replace("_", " ").title()
            
            logger.info(f"Uploading flow '{flow_name}' from {json_path}")
            
            # Check for end states in the data
            end_pages = data.get("end_pages", [])
            if end_pages:
                logger.info(f"Flow contains {len(end_pages)} end state pages")
            
            # Create/update flow
            flow_resource = self.upsert_flow(flow_name)
            flow_url = f"{self.api_prefix}/{flow_resource}"
            
            # Setup dispatcher webhook (if we have webhook actions in the data)
            dispatcher_name = None
            has_webhooks = any(r.get("webhook_action") for r in data.get("routes", []))
            
            if has_webhooks or data.get("webhooks"):
                headers_map = None
                if self.dispatcher_header:
                    if "=" in self.dispatcher_header:
                        k, v = self.dispatcher_header.split("=", 1)
                        headers_map = {k.strip(): v.strip()}
                
                dispatcher_name = self.upsert_webhook("Dispatcher", self.dispatcher_url, headers_map)
                logger.info(f"Webhook configured: Dispatcher -> {self.dispatcher_url}")
            else:
                logger.info("No webhooks needed for this flow")
            
            # Get existing resources
            intents_index = self.list_by_name(f"{self.base_url}/intents", "intents")
            pages_index = self.list_by_name(f"{flow_url}/pages", "pages")
            
            # Create/update pages
            page_name_to_id = {}
            for page, info in data.get("pages", {}).items():
                # Check if this is an end state page
                is_end_state = page in end_pages
                if is_end_state:
                    logger.info(f"  Creating end state page: {page}")
                
                page_resource = self.upsert_page(
                    flow_url, page,
                    info.get("prompts", []),
                    info.get("chips", []),
                    pages_index,
                    is_end_state
                )
                page_name_to_id[page] = page_resource
                pages_index[page] = {"name": page_resource}
            
            # Create/update intents
            intent_name_to_id = {}
            for intent_name, intent_info in data.get("intents", {}).items():
                tp = intent_info.get("training_phrases", [])
                intent_resource = self.upsert_intent(intent_name, tp, intents_index)
                intent_name_to_id[intent_name] = intent_resource
                intents_index[intent_name] = {"name": intent_resource}
            
            # Create routes
            routes_by_page = {}
            valid_route_count = 0
            skipped_route_count = 0
            
            for r in data.get("routes", []):
                # Skip routes without valid next pages (these are end states)
                if not r.get("next_page"):
                    skipped_route_count += 1
                    logger.debug(f"  Skipping end state route from {r.get('page')}")
                    continue
                
                routes_by_page.setdefault(r["page"], []).append(r)
                valid_route_count += 1
            
            logger.info(f"Processing {valid_route_count} valid routes ({skipped_route_count} end state routes skipped)")
            
            # Apply routes to pages
            for page, routes in routes_by_page.items():
                page_resource = page_name_to_id.get(page)
                if not page_resource:
                    logger.warning(f"Page '{page}' not found in created pages, skipping routes")
                    continue
                
                patch_url = f"{self.api_prefix}/{page_resource}"
                transition_routes = []
                
                for r in routes:
                    intent_ref = intent_name_to_id.get(r["intent"])
                    next_page = r.get("next_page")
                    
                    if not next_page:
                        continue
                        
                    target_page_ref = page_name_to_id.get(next_page)
                    if not target_page_ref:
                        logger.warning(f"Target page '{next_page}' not found, skipping route")
                        continue
                    
                    # Build basic route structure
                    route_payload = {
                        "intent": intent_ref,
                        "targetPage": target_page_ref
                    }
                    
                    # ONLY add triggerFulfillment if we have webhook or parameters
                    webhook_action = r.get("webhook_action")
                    params = r.get("parameters")
                    
                    # Check if we actually have content for triggerFulfillment
                    has_webhook = webhook_action and dispatcher_name
                    has_params = params and isinstance(params, dict) and any(params.values())
                    
                    if has_webhook or has_params:
                        trig = {}
                        
                        # Add webhook reference if we have dispatcher and action
                        if has_webhook:
                            trig["webhook"] = dispatcher_name
                            trig["tag"] = webhook_action
                            logger.debug(f"    Adding webhook action: {webhook_action}")
                        
                        # Add parameters if they exist and are non-empty
                        if has_params:
                            param_actions = []
                            for k, v in params.items():
                                if k and v:  # Only add non-empty params
                                    param_actions.append({"parameter": k, "value": v})
                            if param_actions:
                                trig["setParameterActions"] = param_actions
                                logger.debug(f"    Adding {len(param_actions)} parameters")
                        
                        # Only add triggerFulfillment if trig has content
                        if trig:
                            route_payload["triggerFulfillment"] = trig
                    
                    transition_routes.append(route_payload)
                
                # Update page routes only if there are routes to add
                if transition_routes:
                    self._api_request('PATCH', patch_url,
                                    params={"updateMask": "transitionRoutes"},
                                    json={"transitionRoutes": transition_routes})
                    logger.info(f"Updated {len(transition_routes)} routes for page: {page}")
                else:
                    logger.info(f"Page '{page}' is an end state (no outgoing routes)")
            
            # Set start route
            first_page = data.get("first_page")
            if first_page:
                self.patch_flow_start_route(flow_url, first_page)
                logger.info(f"Set flow start route to: {first_page}")
            
            logger.info(f"✓ Successfully uploaded flow '{flow_name}'")
            return True, flow_name
            
        except Exception as e:
            logger.error(f"✗ Failed to upload {json_path}: {e}")
            return False, str(e)
    
    def upload_bulk(self, json_dir: str, max_workers: int = 3) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Upload multiple flows from a directory of JSON files."""
        json_path = Path(json_dir)
        if not json_path.exists():
            raise ValueError(f"Directory does not exist: {json_dir}")
        
        # Find all JSON files
        json_files = list(json_path.glob("dialogflow_*.json"))
        if not json_files:
            logger.warning(f"No dialogflow_*.json files found in {json_dir}")
            return [], []
        
        logger.info(f"Found {len(json_files)} flows to upload")
        logger.info("=" * 50)
        
        successes = []
        failures = []
        
        # Sequential upload (safer for API limits)
        for json_file in json_files:
            success, result = self.upload_single_flow(str(json_file))
            if success:
                successes.append(result)
            else:
                failures.append((json_file.name, result))
            
            # Rate limiting
            time.sleep(1)
        
        # Summary
        logger.info("=" * 50)
        logger.info(f"Upload complete: {len(successes)}/{len(json_files)} successful")
        
        if failures:
            logger.error("Failed uploads:")
            for file, error in failures:
                logger.error(f"  - {file}: {error}")
        
        return successes, failures

def main():
    parser = argparse.ArgumentParser(description="Upload flows to Dialogflow CX")
    parser.add_argument("--service-account", required=True, help="Service account JSON file")
    parser.add_argument("--project-id", required=True, help="GCP project ID")
    parser.add_argument("--location", default="us-central1", help="Dialogflow location")
    parser.add_argument("--agent-id", required=True, help="Dialogflow agent ID")
    parser.add_argument("--dispatcher-url", required=True, help="Dispatcher webhook URL")
    parser.add_argument("--dispatcher-header", help="Optional header for dispatcher (format: Key=Value)")
    parser.add_argument("--json-dir", help="Directory containing JSON files for bulk upload")
    parser.add_argument("--json-file", help="Single JSON file to upload")
    parser.add_argument("--flow-name", help="Flow display name (for single file upload)")
    
    args = parser.parse_args()
    
    # Initialize uploader
    uploader = DialogflowUploader(
        service_account_file=args.service_account,
        project_id=args.project_id,
        location=args.location,
        agent_id=args.agent_id,
        dispatcher_url=args.dispatcher_url,
        dispatcher_header=args.dispatcher_header
    )
    
    try:
        if args.json_dir:
            # Bulk upload
            successes, failures = uploader.upload_bulk(args.json_dir)
            exit(0 if not failures else 1)
        elif args.json_file:
            # Single file upload
            success, result = uploader.upload_single_flow(args.json_file, args.flow_name)
            exit(0 if success else 1)
        else:
            logger.error("Please specify either --json-dir for bulk upload or --json-file for single upload")
            exit(1)
            
    except Exception as e:
        logger.error(f"Error: {e}")
        exit(1)

if __name__ == "__main__":
    main()