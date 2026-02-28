import httpx
import json
import time
import os
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

# 1. Define the directory instead of a single file
TOKENS_DIR = Path("clio_tokens_storage")

# 2. Ensure the directory exists when the app starts up
TOKENS_DIR.mkdir(parents=True, exist_ok=True)

class ClioSDK:
    def __init__(self) -> None:
        # We store a dictionary of clients so users don't share HTTP sessions!
        self._clients: Dict[str, httpx.AsyncClient] = {}
        
        # Clio Endpoints
        self._base_url = "https://app.clio.com/api/v4"
        self._auth_url = "https://app.clio.com/oauth/token"
        
        # App Credentials
        self._client_id = os.getenv("CLIO_CLIENT_ID")
        self._client_secret = os.getenv("CLIO_CLIENT_SECRET")
        self._redirect_uri = os.getenv("CLIO_REDIRECT_URI", "http://127.0.0.1:8000/oauth/callback")

    # ==========================================
    # Token File Management
    # ==========================================
    def _get_token_file_path(self, user_id: str) -> Path:
        """Helper to get the specific file path for a user."""
        return TOKENS_DIR / f"{user_id}.json"

    def _read_tokens_from_file(self, user_id: str) -> dict:
        """Reads tokens from the user's dedicated file."""
        user_file = self._get_token_file_path(user_id)
        if user_file.exists():
            with open(user_file, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def _write_tokens_to_file(self, user_id: str, access_token: str, refresh_token: str, expires_in: int):
        """Writes tokens to the user's dedicated file, preventing overlaps."""
        user_file = self._get_token_file_path(user_id)
        expires_at = time.time() + int(expires_in) - 300  # 5 min safety buffer
        
        data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at
        }
        
        with open(user_file, "w") as f:
            json.dump(data, f, indent=4)

    def get_authorization_url(self, user_id: str) -> str:
        """Generate URL and pass user_id in the state parameter."""
        return (
            f"https://app.clio.com/oauth/authorize"
            f"?response_type=code"
            f"&client_id={self._client_id}"
            f"&redirect_uri={self._redirect_uri}"
            f"&state={user_id}"
        )

    async def exchange_code_for_tokens(self, code: str, user_id: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._auth_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._redirect_uri,
                },
            )
            response.raise_for_status()
            tokens = response.json()
            
            self._write_tokens_to_file(
                user_id=user_id,
                access_token=tokens["access_token"],
                refresh_token=tokens["refresh_token"],
                expires_in=tokens["expires_in"]
            )
            return tokens

    # ==========================================
    # SDK Core Logic
    # ==========================================
    async def close_sdk(self):
        """Close all active client connections."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    async def _get_request_headers(self, user_id: str) -> dict:
        tokens = self._read_tokens_from_file(user_id)
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_at = tokens.get("expires_at", 0)

        if not access_token or time.time() > expires_at:
            if not refresh_token:
                raise Exception(f"No refresh token found for user {user_id}. Please run the OAuth login flow.")

            async with httpx.AsyncClient() as httpx_client:
                response = await httpx_client.post(
                    self._auth_url,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    },
                )
                response.raise_for_status()
                new_tokens = response.json()
                
                access_token = new_tokens["access_token"]
                self._write_tokens_to_file(
                    user_id=user_id,
                    access_token=access_token,
                    refresh_token=new_tokens["refresh_token"],
                    expires_in=new_tokens["expires_in"]
                )

        return {"Authorization": f"Bearer {access_token}"}

    async def _get_httpx_client(self, user_id: str) -> httpx.AsyncClient:
        """Get an isolated HTTP client for the requested user."""
        if user_id not in self._clients:
            self._clients[user_id] = httpx.AsyncClient(base_url=self._base_url, timeout=30.0)

        headers = await self._get_request_headers(user_id)
        self._clients[user_id].headers.update(headers)
        return self._clients[user_id]

    # ==========================================
    # API Methods - Matters & Contacts
    # ==========================================
    async def get_matters(self, user_id: str, fields: str = "id,display_number,description,client,status") -> List[Dict]:
        client = await self._get_httpx_client(user_id)
        response = await client.get("/matters.json", params={"fields": fields})
        response.raise_for_status()
        return response.json().get("data", [])

    async def get_matter(self, user_id: str, matter_id: int, fields: str = None) -> Dict:
        client = await self._get_httpx_client(user_id)
        params = {"fields": fields} if fields else {}
        response = await client.get(f"/matters/{matter_id}.json", params=params)
        response.raise_for_status()
        return response.json().get("data", {})

    async def get_contacts(self, user_id: str, fields: str = "id,name,first_name,last_name,primary_email_address") -> List[Dict]:
        client = await self._get_httpx_client(user_id)
        response = await client.get("/contacts.json", params={"fields": fields})
        response.raise_for_status()
        return response.json().get("data", [])

    async def get_contact(self, user_id: str, contact_id: int, fields: str = None) -> Dict:
        client = await self._get_httpx_client(user_id)
        params = {"fields": fields} if fields else {}
        response = await client.get(f"/contacts/{contact_id}.json", params=params)
        response.raise_for_status()
        return response.json().get("data", {})

    # ==========================================
    # API Methods - Custom Fields
    # ==========================================
    async def get_custom_fields(self, user_id: str, parent_type: str = "Matter") -> List[Dict]:
        client = await self._get_httpx_client(user_id)
        response = await client.get(
            "/custom_fields.json",
            params={"parent_type": parent_type.lower(), "fields": "id,name,field_type,parent_type"}
        )
        response.raise_for_status()
        return response.json().get("data", [])

    async def create_custom_field(self, user_id: str, name: str, field_type: str, parent_type: str = "Matter", displayed: bool = True) -> Dict:
        client = await self._get_httpx_client(user_id)
        payload = {
            "data": {
                "name": name,
                "field_type": field_type,
                "parent_type": parent_type.capitalize(),
                "displayed": displayed
            }
        }
        response = await client.post("/custom_fields.json", json=payload)
        response.raise_for_status()
        return response.json().get("data", {})

    async def get_custom_field_set(self, user_id: str, name: str, parent_type: str = "Matter") -> Optional[Dict]:
        client = await self._get_httpx_client(user_id)
        response = await client.get(
            "/custom_field_sets.json",
            params={"parent_type": parent_type, "fields": "id,name,custom_fields", "query": name}
        )
        response.raise_for_status()
        for s in response.json().get("data", []):
            if s.get("name") == name:
                return s
        return None

    async def create_custom_field_set(self, user_id: str, name: str, custom_field_ids: list, parent_type: str = "Matter") -> Dict:
        client = await self._get_httpx_client(user_id)
        payload = {
            "data": {
                "name": name,
                "parent_type": parent_type,
                "custom_field_ids": custom_field_ids,
                "displayed": True
            }
        }
        response = await client.post("/custom_field_sets.json", json=payload)
        response.raise_for_status()
        return response.json().get("data", {})

    async def ensure_custom_fields_exist(self, user_id: str, required_fields: Dict[str, str], parent_type: str = "Matter") -> Dict[str, int]:
        existing = await self.get_custom_fields(user_id, parent_type=parent_type)
        field_map = {f["name"]: f["id"] for f in existing}

        for field_name, field_type in required_fields.items():
            if field_name not in field_map:
                new_field = await self.create_custom_field(user_id, name=field_name, field_type=field_type, parent_type=parent_type)
                field_map[field_name] = new_field["id"]

        set_name = "Police Report Automation Fields"
        field_ids = [field_map[name] for name in required_fields.keys()]
        field_set = await self.get_custom_field_set(user_id, set_name, parent_type=parent_type)
        
        if not field_set:
            await self.create_custom_field_set(user_id, set_name, field_ids, parent_type=parent_type)
        else:
            existing_ids = [f["id"] for f in field_set.get("custom_fields", [])]
            missing_ids = [fid for fid in field_ids if fid not in existing_ids]
            if missing_ids:
                client = await self._get_httpx_client(user_id)
                await client.patch(f"/custom_field_sets/{field_set['id']}.json", json={"data": {"custom_field_ids": existing_ids + missing_ids}})
        return field_map

    async def upsert_matter_custom_fields(self, user_id: str, matter_id: int, field_id_value_map: dict) -> Dict:
        client = await self._get_httpx_client(user_id)
        
        response = await client.get(
            f"/matters/{matter_id}.json", 
            params={"fields": "custom_field_values{id,custom_field}"}
        )
        response.raise_for_status()
        
        existing_values = response.json().get("data", {}).get("custom_field_values", [])
        value_id_map = {}
        for v in existing_values:
            cf = v.get("custom_field")
            if cf and cf.get("id") and v.get("id"):
                value_id_map[cf["id"]] = v["id"]
                
        upsert_payload = []
        for field_id, value in field_id_value_map.items():
            if field_id in value_id_map:
                upsert_payload.append({
                    "id": value_id_map[field_id],
                    "value": value
                })
            else:
                upsert_payload.append({
                    "custom_field": {"id": field_id},
                    "value": value
                })
            
        if not upsert_payload:
            return {}

        patch_resp = await client.patch(
            f"/matters/{matter_id}.json",
            json={"data": {"custom_field_values": upsert_payload}}
        )
        patch_resp.raise_for_status()
        return patch_resp.json().get("data", {})

    # ==========================================
    # API Methods - Calendars & Automation
    # ==========================================
    async def get_calendars(self, user_id: str, writeable: bool = True) -> List[Dict]:
        client = await self._get_httpx_client(user_id)
        params = {"fields": "id,name,type,permission"}
        if writeable:
            params["writeable"] = "true"
        response = await client.get("/calendars.json", params=params)
        response.raise_for_status()
        return response.json().get("data", [])

    async def create_calendar_entry(self, user_id: str, summary: str, start_at: datetime, end_at: datetime, matter_id: int = None, attendee_ids: List[int] = None, description: str = None, all_day: bool = False, calendar_owner_id: int = None) -> Dict:
        client = await self._get_httpx_client(user_id)
        if not calendar_owner_id:
            calendars = await self.get_calendars(user_id, writeable=True)
            if calendars:
                calendar_owner_id = calendars[0]["id"]
            else:
                raise Exception("No writable calendars found")
        
        start_str = start_at.strftime("%Y-%m-%dT00:00:00Z") if all_day else start_at.isoformat()
        end_str = end_at.strftime("%Y-%m-%dT23:59:59Z") if all_day else end_at.isoformat()
        
        data = {
            "summary": summary,
            "start_at": start_str,
            "end_at": end_str,
            "all_day": all_day,
            "calendar_owner": {"id": calendar_owner_id}
        }
        if matter_id: data["matter"] = {"id": matter_id}
        if attendee_ids: data["attendees"] = [{"id": aid, "type": "User"} for aid in attendee_ids]
        if description: data["description"] = description

        response = await client.post("/calendar_entries.json", json={"data": data})
        response.raise_for_status()
        return response.json().get("data", {})

    async def get_document_templates(self, user_id: str) -> List[Dict]:
        client = await self._get_httpx_client(user_id)
        response = await client.get("/document_templates.json", params={"fields": "id,filename,content_type,created_at"})
        response.raise_for_status()
        data = response.json().get("data", [])
        for item in data:
            item["name"] = item.get("filename", f"Template {item.get('id')}")
        return data

    async def create_document_from_template(self, user_id: str, template_id: int, matter_id: int, filename: str, formats: List[str] = None) -> Dict:
        client = await self._get_httpx_client(user_id)
        data = {
            "document_template": {"id": template_id},
            "matter": {"id": matter_id},
            "filename": filename,
            "formats": formats or ["original"]
        }
        response = await client.post("/document_automations.json", json={"data": data})
        response.raise_for_status()
        return response.json().get("data", {})

    async def get_document(self, user_id: str, document_id: int) -> Dict:
        client = await self._get_httpx_client(user_id)
        response = await client.get(f"/documents/{document_id}.json", params={"fields": "id,name,latest_document_version"})
        response.raise_for_status()
        return response.json().get("data", {})

    async def download_document(self, user_id: str, document_id: int) -> bytes:
        client = await self._get_httpx_client(user_id)
        doc = await self.get_document(user_id, document_id)
        version = doc.get("latest_document_version", {})
        
        response = await client.get(f"/document_versions/{version['id']}.json", params={"fields": "id,download_url"})
        response.raise_for_status()
        download_url = response.json().get("data", {}).get("download_url")
        
        async with httpx.AsyncClient() as download_client:
            dl_response = await download_client.get(download_url)
            dl_response.raise_for_status()
            return dl_response.content
        
    async def create_document_template(self, user_id: str, filename: str, file_base64: str) -> Dict:
        """Create a new Document Template in Clio using a base64 encoded file."""
        client = await self._get_httpx_client(user_id)
        
        payload = {
            "data": {
                "filename": filename,
                "file": file_base64
            }
        }
        
        response = await client.post("/document_templates.json", json=payload)
        response.raise_for_status()
        return response.json().get("data", {})

clio = ClioSDK()