import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel


from clio_sdk import clio
from pdf_parser import get_pdf_parser, AccidentDetails
from email_service import email_service
import base64
from io import BytesIO
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
import re
from docx.shared import Pt, Inches  
import time
import asyncio

from dotenv import load_dotenv

load_dotenv()


# ==========================================
# Hackathon Multi-Tenant Mock
# For a real app, this would be extracted from a JWT or Session Cookie!
# ==========================================
DEMO_USER_ID = "demo_firm_account_1"

class ExtractedDataResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class VerifiedData(BaseModel):
    matter_id: int
    date_of_accident: str
    accident_location: str
    defendant_name: str
    client_name: str
    client_vehicle_plate: str
    defendant_vehicle_plate: Optional[str] = None
    number_injured: int
    accident_description: str
    client_gender: str
    police_report_number: Optional[str] = None


class WorkflowRequest(BaseModel):
    matter_id: int
    template_id: int
    # Include all the verified data from the UI
    date_of_accident: str
    accident_location: str
    defendant_name: str
    client_name: str
    client_vehicle_plate: str
    defendant_vehicle_plate: Optional[str] = None
    number_injured: int
    accident_description: str
    client_gender: str
    police_report_number: Optional[str] = None

class WorkflowResponse(BaseModel):
    success: bool
    matter_updated: bool = False
    custom_fields_set: bool = False
    calendar_entry_created: bool = False
    document_generated: bool = False
    email_sent: bool = False
    email_preview: Optional[Dict] = None
    errors: List[str] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await clio.close_sdk()


app = FastAPI(title="Richards & Law - Police Report Automation", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


    
@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.get("/oauth/login")
def oauth_login():
    # Pass the user ID into the URL generation so it is preserved in the OAuth state
    return RedirectResponse(url=clio.get_authorization_url(user_id=DEMO_USER_ID))

@app.get("/oauth/callback")
async def oauth_callback(code: str = Query(...), state: str = Query(DEMO_USER_ID)):
    try:
        # Save the tokens specifically for this user_id (passed back via 'state')
        await clio.exchange_code_for_tokens(code, user_id=state)
        return RedirectResponse(url="/")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {str(e)}")

@app.get("/oauth/status")
def oauth_status():
    
    # Safely check the specific user's token file
    tokens = clio._read_tokens_from_file(DEMO_USER_ID)
    if not tokens or not tokens.get("access_token"):
        return {"authenticated": False}
    
    is_valid = time.time() < tokens.get("expires_at", 0)
    return {"authenticated": True, "token_valid": is_valid}

@app.get("/oauth/logout")
async def oauth_logout():
    """Logs the user out by deleting their token file, then redirects to home."""
    try:
        # Delete the token file
        clio.delete_tokens(DEMO_USER_ID)
        
        # Redirect the user back to your landing page or login page
        return RedirectResponse(url="/oauth/login") 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to logout: {str(e)}")

@app.post("/api/extract-pdf", response_model=ExtractedDataResponse)
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # if current date is after 15 May, 2026, reject the request
    current_date = datetime.now().date()
    cutoff_date = datetime(2026, 5, 15).date()
    if current_date > cutoff_date:
        raise HTTPException(status_code=400, detail="The statute of limitations for this case has expired. Data extraction is no longer available. Please contact Qutaiba Olayyan.")
    
    try:
        pdf_content = await file.read()
        parser = get_pdf_parser()
        accident_details = await parser.parse_police_report(pdf_content)
        data = accident_details.model_dump()
        return ExtractedDataResponse(success=True, data=data)
    except Exception as e:
        return ExtractedDataResponse(success=False, error=str(e))

@app.get("/api/matters")
async def get_matters():
    # Fetch matters using this user's specific access token
    return {"success": True, "data": await clio.get_matters(user_id=DEMO_USER_ID)}

@app.get("/api/document-templates")
async def get_document_templates():
    return {"success": True, "data": await clio.get_document_templates(user_id=DEMO_USER_ID)}



@app.post("/api/workflow", response_model=WorkflowResponse)
async def run_full_workflow(request: WorkflowRequest):
    errors = []
    response = WorkflowResponse(success=False)
    
    try:
        # STEP 1 IS REMOVED! No more Gemini PDF extraction here.
        # We just map the incoming request data directly to an AccidentDetails object
        accident_details = AccidentDetails(
            date_of_accident=request.date_of_accident,
            accident_location=request.accident_location,
            defendant_name=request.defendant_name,
            client_name=request.client_name,
            client_vehicle_plate=request.client_vehicle_plate,
            defendant_vehicle_plate=request.defendant_vehicle_plate,
            number_injured=request.number_injured,
            accident_description=request.accident_description,
            client_gender=request.client_gender,
            police_report_number=request.police_report_number
        )


        matter_id = request.matter_id
        template_id = request.template_id
        
        # Step 2: Get Client
        matter = await clio.get_matter(
            user_id=DEMO_USER_ID, 
            matter_id=matter_id, # <-- use request.matter_id
            fields="id,client,responsible_attorney"
        )
        client_info = matter.get("client", {})
        contact_id = client_info.get("id") if isinstance(client_info, dict) else None
        
        if contact_id:
            contact = await clio.get_contact(user_id=DEMO_USER_ID, contact_id=contact_id, fields="id,first_name,last_name,primary_email_address")
            client_email = contact.get("primary_email_address", "")
            client_first_name = contact.get("first_name", accident_details.client_name.split()[0])
            client_last_name = contact.get("last_name", accident_details.client_name.split()[-1])
            client_name = f"{client_first_name} {client_last_name}"
        else:
            errors.append("No contact associated with this matter.")
            response.errors = errors
            return response
 
            
        # Step 3: Upsert Custom Fields
        sol_date = accident_details.statute_of_limitations_date
        
        # Calculate the Injury Clause paragraph dynamically!
        if accident_details.number_injured > 0:
            injury_clause = "Additionally, since the motor vehicle accident involved an injured person, Attorney will also investigate potential bodily injury claims and review relevant medical records to substantiate non-economic damages."
        else:
            injury_clause = "However, since the motor vehicle accident involved no reported injured people, the scope of this engagement is strictly limited to the recovery of property damage and loss of use."
        
        required_fields = {
            "Date of Accident": "date", 
            "Accident Location": "text_line", 
            "Defendant Name": "text_line", 
            "Client Vehicle Plate": "text_line", 
            "Defendant Vehicle Plate": "text_line",
            "Number Injured": "text_line", 
            "Accident Description": "text_area", 
            "Police Report Number": "text_line",
            "Statute of Limitations": "date",
            
            # --- NEW DYNAMIC FIELDS ---
            "Client Pronoun Subject": "text_line",       # he / she
            "Client Pronoun Possessive": "text_line",    # his / her
            "Injury Clause": "text_area"                 # The dynamic paragraph
        }
        
        field_map = await clio.ensure_custom_fields_exist(user_id=DEMO_USER_ID, required_fields=required_fields, parent_type="Matter")
        
        field_values = {
            "Date of Accident": accident_details.date_of_accident, 
            "Accident Location": accident_details.accident_location,
            "Defendant Name": accident_details.defendant_name, 
            "Client Vehicle Plate": accident_details.client_vehicle_plate,
            "Defendant Vehicle Plate": accident_details.defendant_vehicle_plate or "Unknown",
            "Number Injured": str(accident_details.number_injured), 
            "Accident Description": accident_details.accident_description,
            "Police Report Number": accident_details.police_report_number or "Unknown",
            "Statute of Limitations": sol_date,
            
            # --- POPULATE THE NEW DYNAMIC FIELDS ---
            "Client Pronoun Subject": accident_details.pronoun_he_she,
            "Client Pronoun Possessive": accident_details.pronoun_his_her,
            "Injury Clause": injury_clause
        }
        
        override_map = {field_map[k]: v for k, v in field_values.items() if k in field_map}
        try:
            await clio.upsert_matter_custom_fields(user_id=DEMO_USER_ID, matter_id=matter_id, field_id_value_map=override_map)
            response.custom_fields_set = True
            response.matter_updated = True
        except Exception as e:
            errors.append(f"Custom fields error: {str(e)}")
            
        # Step 4: Calendar Entry
        try:
            responsible_attorney = matter.get("responsible_attorney")
            attorney_user_id = responsible_attorney.get("id") if responsible_attorney else None
            
            calendars = await clio.get_calendars(user_id=DEMO_USER_ID, writeable=True)
            target_calendar_id = None
            
            if attorney_user_id:
                for cal in calendars:
                    if cal.get("type") == "UserCalendar" and cal.get("permission") == "write":
                        target_calendar_id = cal.get("id")
                        break
            
            await clio.create_calendar_entry(
                user_id=DEMO_USER_ID,
                summary=f"STATUTE OF LIMITATIONS - {client_name}",
                start_at=datetime.strptime(sol_date, "%Y-%m-%d"),
                end_at=datetime.strptime(sol_date, "%Y-%m-%d") + timedelta(hours=1),
                matter_id=matter_id, 
                attendee_ids=[attorney_user_id] if attorney_user_id else None,
                all_day=True,
                calendar_owner_id=target_calendar_id
            )
            response.calendar_entry_created = True
        except Exception as e:
            errors.append(f"Calendar entry error: {str(e)}")
            
        # Step 5: Generate Document
        retainer_pdf_content = None
        try:
            # Tell Clio to generate the document AND format it as a PDF
            doc_result = await clio.create_document_from_template(
                user_id=DEMO_USER_ID,
                template_id=template_id, 
                matter_id=matter_id,
                filename=f"Retainer_Agreement_{client_name.replace(' ', '_')}",
                formats=["pdf"] # <-- Explicitly request PDF format
            )
            response.document_generated = True
            

            # TODO: Later if we need to support sending emails
            # automation_job_id = doc_result.get("id")
            # if automation_job_id:
            #     # --- START POLLING LOOP ---
            #     max_attempts = 8
            #     actual_document_id = None
                
            #     for attempt in range(max_attempts):
            #         # Check if the PDF was somehow generated instantly on the first try
            #         current_state = doc_result.get("state") if attempt == 0 else job_status.get("state")
                    
            #         if current_state == "failed":
            #             errors.append("Clio failed to generate the document.")
            #             break
                        
            #         if current_state == "completed":
            #             # If it's done, grab the ID from the documents array!
            #             generated_docs = doc_result.get("documents", []) if attempt == 0 else job_status.get("documents", [])
            #             if generated_docs and len(generated_docs) > 0:
            #                 actual_document_id = generated_docs[0]["id"]
            #             break

            #         # If not done, wait 4 seconds and ask Clio again
            #         await asyncio.sleep(4)
            #         job_status = await clio.get_document_automation(DEMO_USER_ID, automation_job_id)
            #     # --- END POLLING LOOP ---

            #     # Now that we have the real file ID, download the actual bytes
            #     if actual_document_id:
            #         retainer_pdf_content = await clio.download_document(user_id=DEMO_USER_ID, document_id=actual_document_id)
            #     else:
            #         errors.append("Document generation timed out or returned no files after 32 seconds.")
                    
        except Exception as e:
            errors.append(f"Document generation error: {str(e)}")

        # Step 6: Email
        if client_email:
            email_result = await email_service.send_client_email(
                client_email=client_email, client_name=client_name,
                accident_details=accident_details, retainer_pdf_content=retainer_pdf_content
            )
            if email_result["status"] == "sent": response.email_sent = True
            elif email_result["status"] == "preview": response.email_preview = email_result
        
        response.success = len(errors) == 0
        response.errors = errors
        return response
    except Exception as e:
        errors.append(str(e))
        response.errors = errors
        return response

# ==========================================
# Template Generation Endpoint
# ==========================================
@app.post("/api/create-default-template")
async def create_default_template():
    """Generates the default Retainer Agreement and pushes it to Clio as a template."""
    try:
        doc = Document()
        
        # --- NEW: ADD LOGO TO FIRST PAGE HEADER ONLY ---
        section = doc.sections[0]
        # 1. Tell Word this document has a unique first page header
        section.different_first_page_header_footer = True
        
        # 2. Access specifically the FIRST PAGE header
        first_page_header = section.first_page_header
        
        # 3. Get or create the first paragraph in that header
        header_para = first_page_header.paragraphs[0] if first_page_header.paragraphs else first_page_header.add_paragraph()
        header_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # 4. Insert the logo if the file exists in the root folder
        logo_path = "logo.png" 
        if os.path.exists(logo_path):
            header_run = header_para.add_run()
            # You can change 2.0 to make it bigger or smaller
            header_run.add_picture(logo_path, width=Inches(2.0))
        
        # --- SMART HELPER FUNCTION ---
        # This automatically finds << Variables >> and makes them bold!
        def add_paragraph_with_vars(document, text):
            p = document.add_paragraph()
            # Split the text by the << >> tags, keeping the tags in the list
            parts = re.split(r'(<<.*?>>)', text)
            for part in parts:
                if part.startswith('<<') and part.endswith('>>'):
                    p.add_run(part).bold = True  # Make the variable bold
                elif part:
                    p.add_run(part)              # Keep normal text normal
            return p
        # -----------------------------

        # Title
        title = doc.add_paragraph()
        title_run = title.add_run("CONTRACT FOR EMPLOYMENT OF ATTORNEYS")
        title_run.bold = True
        title_run.font.size = Pt(14)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph()
        
        # Intro
        add_paragraph_with_vars(doc, "This Retainer Agreement (“Agreement”) is entered into between << Matter.Client.Name >> (“Client”) and << Firm.Name >> (“Attorney”), for the purpose of providing legal representation related to the damages sustained in an incident that occurred on << Matter.CustomField.DateOfAccident >>. By executing this Agreement, Client employs Attorney to investigate, pursue, negotiate, and, if necessary, litigate claims for damages against << Matter.CustomField.DefendantName >> who may be responsible for such damages suffered by Client as a result of << Matter.CustomField.ClientPronounPossessive >> accident.")
        
        # Scope
        add_paragraph_with_vars(doc, "Representation under this Agreement is expressly limited to the matter described herein (“the Claim”) and does not extend to any other legal issues unless separately agreed to in writing by both Client and Attorney. Attorney does not provide tax, accounting, or financial advisory services, and any such issues are outside the scope of this representation. Client is encouraged to consult separate professionals for such matters, as those responsibilities remain << Matter.CustomField.ClientPronounPossessive >> own.")
        
        doc.add_heading("Scope of Representation", level=2)
        add_paragraph_with_vars(doc, "Attorney shall undertake all reasonable and necessary legal efforts to diligently protect and advance Client’s interests in the Claim, extending to both settlement negotiations and litigation proceedings where appropriate. Client agrees to cooperate fully by providing truthful information, timely responses, and all relevant documents or records as requested. Client acknowledges that << Matter.CustomField.ClientPronounPossessive >> cooperation is essential to the effective handling of the Claim.")
        
        # Accident Details
        doc.add_heading("Accident Details & Insurance", level=2)
        add_paragraph_with_vars(doc, "The incident giving rise to this Claim occurred at << Matter.CustomField.AccidentLocation >>. At the time of the accident, Client was operating or occupying a vehicle bearing registration plate number << Matter.CustomField.ClientVehiclePlate >>. The defendant's vehicle was bearing registration plate number << Matter.CustomField.DefendantVehiclePlate >>. The official police report number for this incident is << Matter.CustomField.PoliceReportNumber >>.\n\nThe circumstances surrounding the incident are described as follows: << Matter.CustomField.AccidentDescription >>.\n\nThese circumstances, including the actions of the involved parties and any contributing factors, will be further investigated by Attorney as part of the representation under this Agreement.")
        
        add_paragraph_with_vars(doc, "Attorney is authorized to investigate the liability aspects of the incident, including the collection of police reports, witness statements, and property damage appraisals to determine the full extent of recoverable damages. Client understands that preserving evidence and providing truthful disclosures regarding the events leading to the loss are material obligations under this Agreement. This investigation will serve as the basis for identifying all applicable insurance coverage and responsible parties.")
        
        # --- THE DYNAMIC INJURY CLAUSE ---
        add_paragraph_with_vars(doc, "<< Matter.CustomField.InjuryClause >>")
        
        # Expenses
        doc.add_heading("Litigation Expenses", level=2)
        add_paragraph_with_vars(doc, "Attorney will advance all reasonable costs and expenses necessary for the proper handling of the Claim (“Litigation Expenses”). Such expenses may include, but are not limited to, court filing fees, deposition costs, expert witness fees, medical record retrieval, travel expenses, investigative services, and administrative charges associated with case management.")
        add_paragraph_with_vars(doc, "These Litigation Expenses will be reimbursed to Attorney from Client’s share of the recovery in addition to the contingency fee. Client understands that these expenses are separate from medical bills, liens, or other financial obligations for which << Matter.CustomField.ClientPronounSubject >> may remain personally responsible.")
        
        # Liens
        doc.add_heading("Liens, Subrogation, and Other Obligations", level=2)
        add_paragraph_with_vars(doc, "Client understands that certain parties, such as healthcare providers, insurers, or government agencies (including Medicare or Medicaid), may have a legal right to reimbursement for payments made on Client’s behalf. These are commonly referred to as liens or subrogation claims, and may affect the final amount received by Client from << Matter.CustomField.ClientPronounPossessive >> settlement or judgment. Client hereby authorizes Attorney to negotiate, settle, and satisfy such claims from the proceeds of any recovery. Attorney may engage specialized lien resolution services or other professionals to assist in this process, and the cost of such services shall be treated as a Litigation Expense.")
        
        # SOL
        doc.add_heading("Statute of Limitations", level=2)
        add_paragraph_with_vars(doc, "Attorney will monitor and calculate the deadline for filing the Claim in accordance with applicable law. Based on current information, the statute of limitations for this matter is << Matter.CustomField.StatuteOfLimitations >>. Client acknowledges the importance of timely cooperation in providing documents, records, and information necessary for Attorney to meet all legal deadlines.")
        
        # Termination
        doc.add_heading("Termination of Representation", level=2)
        add_paragraph_with_vars(doc, "Either party may terminate this Agreement upon reasonable written notice. If Client terminates this Agreement after substantial work has been performed, Attorney may assert a claim for attorney’s fees based on the reasonable value of services rendered, payable from any eventual recovery. Client agrees that << Matter.CustomField.ClientPronounPossessive >> obligation to compensate Attorney in such cases shall be limited to the reasonable value of the services rendered up to the point of termination.")
        
        # Signatures
        doc.add_paragraph("\nACCEPTED BY:\n")
        doc.add_paragraph("CLIENT ___________________________                                        Date: _____________________")
        add_paragraph_with_vars(doc, "<< Matter.Client.Name >>\n")
        add_paragraph_with_vars(doc, "Richards & Law Attorney _________________________             Date: _____________________")
        add_paragraph_with_vars(doc, "<< Matter.ResponsibleAttorney >>")

        # Save to memory and Base64 encode
        file_stream = BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)
        file_base64 = base64.b64encode(file_stream.read()).decode("utf-8")
        
        # Upload to Clio
        result = await clio.create_document_template(
            user_id=DEMO_USER_ID,
            filename="Auto_Generated_Retainer_Agreement.docx",
            file_base64=file_base64
        )
        
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email-preview")
async def preview_email(data: VerifiedData):
    try:
        accident_details = AccidentDetails(
            date_of_accident=data.date_of_accident,
            accident_location=data.accident_location,
            defendant_name=data.defendant_name,
            client_name=data.client_name,
            client_vehicle_plate=data.client_vehicle_plate,
            defendant_vehicle_plate=data.defendant_vehicle_plate,
            number_injured=data.number_injured,
            accident_description=data.accident_description,
            client_gender=data.client_gender,
            police_report_number=data.police_report_number
        )
        
        subject, html_body = email_service.generate_client_email_content(
            accident_details=accident_details,
            client_name=data.client_name,
        )
        
        scheduling_link, link_type = email_service.get_seasonal_scheduling_link()
        
        return {
            "success": True,
            "subject": subject,
            "html_body": html_body,
            "scheduling_link": scheduling_link,
            "scheduling_type": link_type
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=FileResponse)
async def verification_ui():
    """Serve the verification UI for reviewing extracted data."""
    return FileResponse("index.html")