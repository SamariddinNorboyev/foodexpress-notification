import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import aiosmtplib
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("EmailService")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

def generate_html_template(title: str, status_msg: str, order_id: str, items: list, total_price: float, currency: str) -> str:
    """Zamonaviy, responsive HTML Email shablonini generatsiya qilish"""
    
    # Buyurtma ichidagi taomlar uchun HTML qatorlarini yaratish
    items_html = ""
    for item in items:
        items_html += f"""
        <tr>
            <td style="padding: 12px 0; border-bottom: 1px solid #edf2f7; color: #4a5568;">{item.get('name', 'Taom')}</td>
            <td style="padding: 12px 0; border-bottom: 1px solid #edf2f7; color: #718096; text-align: center;">{item.get('qty', 1)} tа</td>
            <td style="padding: 12px 0; border-bottom: 1px solid #edf2f7; color: #2d3748; text-align: right; font-weight: 600;">{item.get('price', 0):,} {currency}</td>
        </tr>
        """

    # Asosiy HTML har qanday ekran (mobil va desktop) uchun moslashuvchan (responsive) dizaynda
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7fafc; margin: 0; padding: 0; -webkit-font-smoothing: antialiased;">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f7fafc; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
                        
                        <tr>
                            <td style="background: linear-gradient(135deg, #ff6b6b 0%, #ff4757 100%); padding: 32px; text-align: center;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.5px;">FoodExpress</h1>
                                <p style="color: rgba(255, 255, 255, 0.9); margin: 8px 0 0 0; font-size: 16px;">{title}</p>
                            </td>
                        </tr>

                        <tr>
                            <td style="padding: 32px;">
                                <h2 style="color: #1a202c; margin-top: 0; font-size: 20px; font-weight: 700;">{status_msg}</h2>
                                <p style="color: #718096; font-size: 14px; margin-bottom: 24px;">Buyurtma ID: <span style="font-family: monospace; background-color: #edf2f7; padding: 2px 6px; border-radius: 4px; color: #4a5568;">{order_id}</span></p>
                                
                                {f'''
                                <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="margin-bottom: 24px;">
                                    <thead>
                                        <tr>
                                            <th style="text-align: left; color: #a0aec0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; padding-bottom: 8px; border-bottom: 2px solid #edf2f7;">Nomi</th>
                                            <th style="text-align: center; color: #a0aec0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; padding-bottom: 8px; border-bottom: 2px solid #edf2f7;">Soni</th>
                                            <th style="text-align: right; color: #a0aec0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; padding-bottom: 8px; border-bottom: 2px solid #edf2f7;">Narxi</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {items_html}
                                    </tbody>
                                </table>
                                ''' if items else ''}

                                <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #fff5f5; border-radius: 12px; padding: 16px; margin-top: 16px;">
                                    <tr>
                                        <td style="color: #c53030; font-weight: 700; font-size: 16px;">Jami to'lov:</td>
                                        <td style="color: #c53030; font-weight: 800; font-size: 20px; text-align: right;">{total_price:,} {currency}</td>
                                    </tr>
                                </table>

                                <div style="text-align: center; margin-top: 32px;">
                                    <a href="#" style="background-color: #ff4757; color: #ffffff; text-decoration: none; padding: 12px 32px; border-radius: 10px; font-weight: 600; display: inline-block; box-shadow: 0 4px 14px rgba(255, 71, 87, 0.4);">Buyurtmani kuzatish</a>
                                </div>
                            </td>
                        </tr>

                        <tr>
                            <td style="background-color: #f7fafc; padding: 24px; text-align: center; border-top: 1px solid #edf2f7;">
                                <p style="color: #a0aec0; font-size: 12px; margin: 0;">Bu bildirishnoma FoodExpress tizimi tomonidan avtomatik ravishda yuborildi.</p>
                                <p style="color: #a0aec0; font-size: 12px; margin: 4px 0 0 0;">&copy; 2026 FoodExpress. Barcha huquqlar himoyalangan.</p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

async def send_email_async(to_email: str, subject: str, status_msg: str, order_id: str, items: list = None, total_price: float = 0, currency: str = "UZS"):
    """Boyitilgan ma'lumotlar va HTML dizayn bilan email yuborish"""
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.error("❌ SMTP konfiguratsiyalari (.env) yetishmayapti!")
        return

    items = items or []
    
    message = MIMEMultipart("alternative")
    message["From"] = f"FoodExpress <{SMTP_USER}>"
    message["To"] = to_email
    message["Subject"] = subject

    # HTML shablonni generatsiya qilamiz
    html_content = generate_html_template(
        title=subject,
        status_msg=status_msg,
        order_id=order_id,
        items=items,
        total_price=total_price,
        currency=currency
    )
    
    message.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info(f"📧 [HTML EMAIL SENT] Zamonaviy xat muvaffaqiyatli ketdi: {to_email}")
    except Exception as e:
        logger.error(f"❌ Email yuborishda xatolik yuz berdi ({to_email}): {str(e)}")