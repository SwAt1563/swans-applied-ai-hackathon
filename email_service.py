import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from typing import Optional
from pdf_parser import AccidentDetails
from jinja2 import Environment, FileSystemLoader

class EmailService:
    """Service for sending personalized emails to clients."""
    
    # Scheduling links - configured based on season
    IN_OFFICE_SCHEDULING_LINK = os.getenv("IN_OFFICE_SCHEDULING_LINK", "https://calendly.com/richards-law/in-office-consultation")
    VIRTUAL_SCHEDULING_LINK = os.getenv("VIRTUAL_SCHEDULING_LINK", "https://calendly.com/richards-law/virtual-consultation")
    
    # Email configuration
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    FROM_EMAIL = os.getenv("FROM_EMAIL", "info@richardslaw.com")
    FROM_NAME = os.getenv("FROM_NAME", "Richards & Law")
    
    def get_seasonal_scheduling_link(self, date: datetime = None) -> tuple[str, str]:
        """
        Get the appropriate scheduling link based on the season.
        
        March to August: In-office
        September to February: Virtual
        
        Returns:
            Tuple of (link, type) where type is 'in-office' or 'virtual'
        """
        if date is None:
            date = datetime.now()
        
        month = date.month
        
        # March (3) to August (8): In-office
        # September (9) to February (2): Virtual
        if 3 <= month <= 8:
            return self.IN_OFFICE_SCHEDULING_LINK, "in-office"
        else:
            return self.VIRTUAL_SCHEDULING_LINK, "virtual"
    
    def generate_client_email_content(
        self, 
        accident_details: AccidentDetails,
        client_first_name: str,
    ) -> tuple[str, str]:
        """
        Generate personalized email content for the potential client using Jinja2.
        """
        scheduling_link, link_type = self.get_seasonal_scheduling_link()
        consultation_type = "in-office" if link_type == "in-office" else "virtual"
        
        # Format the accident date nicely
        try:
            accident_date = datetime.strptime(accident_details.date_of_accident, "%Y-%m-%d")
            formatted_date = accident_date.strftime("%B %d, %Y")
        except:
            formatted_date = accident_details.date_of_accident
        
        subject = f"Richards & Law - Your Consultation & Retainer Agreement"
        
        # Set up Jinja2 environment (looks in the current directory for templates)
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('email_template.html')
        
        # Render the HTML by passing the variables to the template
        html_body = template.render(
            client_first_name=client_first_name,
            formatted_date=formatted_date,
            accident_location=accident_details.accident_location,
            accident_description=accident_details.accident_description,
            consultation_type=consultation_type,
            scheduling_link=scheduling_link
        )
        
        return subject, html_body
    
    async def send_client_email(
        self,
        client_email: str,
        client_first_name: str,
        accident_details: AccidentDetails,
        retainer_pdf_content: bytes = None
    ) -> dict:
        """
        Send the personalized email with retainer agreement attached.
        
        Args:
            client_email: Client's email address
            client_first_name: Client's first name
            accident_details: Extracted accident details
            retainer_pdf_content: Optional PDF bytes of the retainer agreement
            
        Returns:
            Dictionary with send status
        """
        subject, html_body = self.generate_client_email_content(
            accident_details,
            client_first_name,
        )
        
        # Create message
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = f"{self.FROM_NAME} <{self.FROM_EMAIL}>"
        msg['To'] = client_email
        
        # Attach HTML body
        msg.attach(MIMEText(html_body, 'html'))
        
        # Attach retainer PDF if provided
        if retainer_pdf_content:
            pdf_attachment = MIMEApplication(retainer_pdf_content, _subtype='pdf')
            pdf_attachment.add_header(
                'Content-Disposition', 
                'attachment', 
                filename=f"Retainer_Agreement_{accident_details.client_name.replace(' ', '_')}.pdf"
            )
            msg.attach(pdf_attachment)
        
        # Send email
        if self.SMTP_USER and self.SMTP_PASSWORD:
            try:
                context = ssl.create_default_context()
                with smtplib.SMTP(self.SMTP_HOST, self.SMTP_PORT) as server:
                    server.starttls(context=context)
                    server.login(self.SMTP_USER, self.SMTP_PASSWORD)
                    server.send_message(msg)
                
                return {
                    "status": "sent",
                    "to": client_email,
                    "subject": subject
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "to": client_email
                }
        else:
            # Return preview if SMTP not configured
            return {
                "status": "preview",
                "to": client_email,
                "subject": subject,
                "html_body": html_body,
                "message": "SMTP not configured - email preview only"
            }


email_service = EmailService()
