import os

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, computed_field
from google import genai
from google.genai import types


class AccidentDetails(BaseModel):
    date_of_accident: str = Field(description="Date of accident in YYYY-MM-DD format")
    accident_location: str = Field(description="Full address or location of the accident")
    defendant_name: str = Field(description="Name of the defendant/at-fault party")
    client_name: str = Field(description="Name of the client/victim")
    client_vehicle_plate: str = Field(description="Registration plate number of the client's vehicle")
    defendant_vehicle_plate: Optional[str] = Field(description="Registration plate of defendant's vehicle (or empty string if not found)")
    number_injured: int = Field(description="Number of people injured in the accident")
    accident_description: str = Field(description="Brief description of how the accident occurred")
    client_gender: Literal["male", "female"] = Field(description="Gender of client: 'male' or 'female'")
    police_report_number: Optional[str] = Field(description="Police report number if available (or empty string)")
    
    @computed_field
    @property
    def statute_of_limitations_date(self) -> str:
        """Calculate statute of limitations date (8 years from accident)."""
        accident_date = datetime.strptime(self.date_of_accident, "%Y-%m-%d")
        sol_date = accident_date.replace(year=accident_date.year + 8)
        return sol_date.strftime("%Y-%m-%d")
    
    @computed_field
    @property
    def pronoun_his_her(self) -> str:
        """Dynamically returns 'his' or 'her' based on extracted gender."""
        return "his" if self.client_gender == "male" else "her"
    
    @computed_field
    @property
    def pronoun_he_she(self) -> str:
        """Dynamically returns 'he' or 'she' based on extracted gender."""
        return "he" if self.client_gender == "male" else "she"
    
class GeminiPDFParser:
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set")
        
        # --- NEW INITIALIZATION ---
        self.client = genai.Client(api_key=api_key)
        self.model_name = 'gemini-3.1-pro-preview'
    
    async def parse_police_report(self, pdf_content: bytes) -> AccidentDetails:
        
        extraction_prompt = """You are an expert legal document analyzer. Analyze this police report PDF and extract the required information.
        IMPORTANT: Carefully identify who is the VICTIM/CLIENT (the person who was harmed) versus the DEFENDANT (the at-fault party).
        Look for indicators like: "Victim" vs "Suspect" labels, who was injured, and who is listed as at-fault."""

        # --- NEW GENERATION CALL ---
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[
                extraction_prompt,
                # The new SDK handles raw bytes directly! No manual base64 encoding needed.
                types.Part.from_bytes(data=pdf_content, mime_type="application/pdf")
            ],
            # Use the new GenerateContentConfig
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AccidentDetails,
                temperature=0.0 # Set to 0.0 for more consistent data extraction
            )
        )
        
        # Pydantic natively parses the guaranteed JSON string from Gemini
        return AccidentDetails.model_validate_json(response.text)


# Singleton instance
pdf_parser = GeminiPDFParser() if os.getenv("GOOGLE_API_KEY") else None

def get_pdf_parser() -> GeminiPDFParser:
    global pdf_parser
    if pdf_parser is None:
        pdf_parser = GeminiPDFParser()
    return pdf_parser