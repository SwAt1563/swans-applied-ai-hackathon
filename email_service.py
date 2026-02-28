import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from typing import Optional
from pdf_parser import AccidentDetails


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
        client_email: str
    ) -> tuple[str, str]:
        """
        Generate personalized email content for the potential client.
        
        Returns:
            Tuple of (subject, html_body)
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
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: 'Georgia', serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            border-bottom: 2px solid #1a365d;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }}
        .firm-name {{
            color: #1a365d;
            font-size: 24px;
            font-weight: bold;
            margin: 0;
        }}
        .content {{
            margin-bottom: 25px;
        }}
        .cta-button {{
            display: inline-block;
            background-color: #1a365d;
            color: white;
            padding: 12px 30px;
            text-decoration: none;
            border-radius: 5px;
            font-weight: bold;
            margin: 20px 0;
        }}
        .cta-button:hover {{
            background-color: #2c5282;
        }}
        .footer {{
            border-top: 1px solid #ddd;
            padding-top: 15px;
            margin-top: 25px;
            font-size: 12px;
            color: #666;
        }}
        .highlight {{
            background-color: #f7fafc;
            padding: 15px;
            border-left: 4px solid #1a365d;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="header">
        <p class="firm-name">Richards & Law</p>
        <p style="margin: 5px 0; color: #666;">Personal Injury Attorneys</p>
    </div>
    
    <div class="content">
        <p>Dear {client_first_name},</p>
        
        <p>Thank you for reaching out to Richards & Law regarding the incident that occurred on <strong>{formatted_date}</strong> at <strong>{accident_details.accident_location}</strong>.</p>
        
        <div class="highlight">
            <p style="margin: 0;">We understand that {accident_details.accident_description.lower()} This must be a difficult time for you, and we want you to know that our team is here to help you navigate through this process.</p>
        </div>
        
        <p>After reviewing the details of your case, we have prepared a Retainer Agreement for your review. This agreement outlines the terms of our representation and ensures that we can begin working on your behalf as quickly as possible to protect your rights and pursue the compensation you deserve.</p>
        
        <p><strong>Please find the Retainer Agreement attached to this email as a PDF.</strong> We encourage you to review it carefully before our consultation.</p>
        
        <p>To discuss your case in detail and answer any questions you may have, please schedule a {consultation_type} consultation at your earliest convenience:</p>
        
        <p style="text-align: center;">
            <a href="{scheduling_link}" class="cta-button">Schedule Your Consultation</a>
        </p>
        
        <p>Time is of the essence in personal injury cases, and we are committed to providing you with the swift, professional representation you deserve. We look forward to speaking with you soon.</p>
        
        <p>Warm regards,</p>
        
        <p><strong>Andrew Richards</strong><br>
        Managing Attorney<br>
        Richards & Law</p>
    </div>
    
    <div class="footer">
        <p>Richards & Law | Personal Injury Attorneys<br>
        This email and any attachments are confidential and intended solely for the use of the individual or entity to whom they are addressed.</p>
    </div>
</body>
</html>
"""
        
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
            client_email
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
