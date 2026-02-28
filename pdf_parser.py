import os

import base64
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field, computed_field
import google.generativeai as genai


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
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3.1-pro-preview')
    
    async def parse_police_report(self, pdf_content: bytes) -> AccidentDetails:
        pdf_base64 = base64.standard_b64encode(pdf_content).decode("utf-8")
        
        # PROMPT SIMPLIFIED: We no longer need to explain the JSON format!
        extraction_prompt = """You are an expert legal document analyzer. Analyze this police report PDF and extract the required information.
        IMPORTANT: Carefully identify who is the VICTIM/CLIENT (the person who was harmed) versus the DEFENDANT (the at-fault party).
        Look for indicators like: "Victim" vs "Suspect" labels, who was injured, and who is listed as at-fault."""

        # Call Gemini with the PDF and the Structured Output Configuration
        response = self.model.generate_content(
            [
                extraction_prompt,
                {"mime_type": "application/pdf", "data": pdf_base64}
            ],
            # This forces Gemini to adhere exactly to your Pydantic model
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=AccidentDetails,
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