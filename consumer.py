import asyncio
import json
import logging
import uuid
import aio_pika
from sqlalchemy.future import select
from database import AsyncSessionLocal
from models import Notification, ProcessedEvent
from email_service import send_email_async

logger = logging.getLogger("NotificationConsumer")
RABBITMQ_URL = "amqp://guest:guest@127.0.0.1:5672/"

STATUS_MESSAGES = {
    "CREATED": "Buyurtmangiz muvaffaqiyatli qabul qilindi!",
    "CONFIRMED": "Buyurtmangiz tasdiqlandi. Restoran taomni tayyorlashni boshlamoqda.",
    "PREPARING": "Taomingiz tayyorlanmoqda.",
    "READY": "Buyurtmangiz tayyor! Kuryer uni tez orada olib ketadi.",
    "DELIVERING": "Buyurtmangiz yo'lda! Kuryer manzilingizga yaqinlashmoqda.",
    "DELIVERED": "Buyurtmangiz yetkazib berildi. Yoqimli ishtaha!",
    "CANCELLED": "Buyurtmangiz bekor qilindi."
}

async def handle_email_background(to_email: str, subject: str, status_msg: str, order_id: str, items: list, total_price: float, currency: str):
    """Safely executes email dispatching out-of-band without touching core event state."""
    logger.info(f"⏳ [BACKGROUND EMAIL] Dispatching process started for {to_email}...")
    try:
        await send_email_async(
            to_email=to_email,
            subject=subject,
            status_msg=status_msg,
            order_id=order_id,
            items=items,
            total_price=total_price,
            currency=currency
        )
        logger.info(f"✅ [BACKGROUND EMAIL] Dispatch routine completed for {to_email}")
    except Exception as em_err:
        logger.error(f"❌ [BACKGROUND EMAIL CRASH] Mail subsystem failed independently, but DB is safe! Details: {str(em_err)}")

async def process_event(message: aio_pika.IncomingMessage):
    async with message.process():
        try:
            # Step 1: Decode incoming payload packet
            raw_body = message.body.decode("utf-8")
            logger.info(f"\n📥 [CONSUME START] Received raw payload size: {len(raw_body)} bytes")
            body = json.loads(raw_body)
            
            event_id = uuid.UUID(body["eventId"])
            event_type = body["eventType"]
            data = body["data"]
            
            logger.info(f"🔍 [PROCESSING] Event Type: '{event_type}' | ID: {event_id}")

            async with AsyncSessionLocal() as db:
                # Step 2: Idempotency Validation Check
                logger.info(f"🛡️ [IDEMPOTENCY CHECK] Searching database for eventId: {event_id}")
                result = await db.execute(select(ProcessedEvent).filter_by(event_id=event_id))
                if result.scalar_one_or_none():
                    logger.warning(f"⚠️ [DUPLICATE ABORT] Event already handled previously. Skipping: {event_id}")
                    return

                # Parse contract payload fields safely
                order_id = uuid.UUID(data["orderId"])
                customer_id = uuid.UUID(data["customerId"])
                customer_email = data.get("customerEmail") 
                items = data.get("items", [])
                total_price = data.get("totalPrice", 0)
                currency = data.get("currency", "UZS")
                
                notifications_to_save = []
                email_metadata = None  # Store mail configs to execute *after* DB commit finishes

                # Step 3: Business Logic Parsing Matching Event Contracts
                if event_type == "order.created":
                    title = "Yangi Buyurtma"
                    body_text = STATUS_MESSAGES["CREATED"]

                    notifications_to_save.append(Notification(
                        user_id=customer_id, order_id=order_id,
                        type="ORDER_CREATED", title=title, body=body_text
                    ))
                    
                    if customer_email:
                        email_metadata = (customer_email, title, body_text, str(order_id), items, total_price, currency)

                    if "restaurantId" in data and data["restaurantId"]:
                        rest_id = uuid.UUID(data["restaurantId"])
                        notifications_to_save.append(Notification(
                            user_id=rest_id, order_id=order_id,
                            type="ORDER_CREATED", title="Yangi Buyurtma Keldi!",
                            body=f"Restoraningizga yangi buyurtma tushdi (ID: {str(order_id)[:8]})."
                        ))
                    
                elif event_type == "order.status_changed":
                    new_status = data["newStatus"]
                    title = f"Buyurtma holati: {new_status}"
                    body_text = STATUS_MESSAGES.get(new_status, "Buyurtma holati yangilandi.")
                    
                    notifications_to_save.append(Notification(
                        user_id=customer_id, order_id=order_id,
                        type="STATUS_CHANGED", title=title, body=body_text
                    ))
                    
                    if customer_email:
                        email_metadata = (customer_email, title, body_text, str(order_id), items, total_price, currency)

                    if "courierId" in data and data["courierId"]:
                        courier_id = uuid.UUID(data["courierId"])
                        notifications_to_save.append(Notification(
                            user_id=courier_id, order_id=order_id,
                            type="STATUS_CHANGED", title="Sizga buyurtma biriktirildi",
                            body=f"Buyurtmani mijozga yetkazishni boshlang (ID: {str(order_id)[:8]})."
                        ))
                else:
                    logger.warning(f"❓ [UNKNOWN TYPE] Discarding unexpected event specification: {event_type}")
                    return

                # Step 4: Add Records & Commit Transactions to Database
                logger.info(f"💾 [DB STAGE] Staging {len(notifications_to_save)} notifications for ingestion...")
                for notif in notifications_to_save:
                    db.add(notif)
                
                db.add(ProcessedEvent(event_id=event_id))
                
                logger.info("💾 [DB COMMIT] Sending transaction commit request to Database engine...")
                await db.commit()
                logger.info("💾 [DB SUCCESS] Records successfully saved and stored permanently!")

            # Step 5: Execute Email Delivery outside the closed DB scope
            if email_metadata:
                logger.info("✉️ [EMAIL TRIGGER] Handing off email tracking payload to isolated thread task...")
                asyncio.create_task(handle_email_background(*email_metadata))

            logger.info("🏁 [CONSUME END] Successfully finalized event message package processing.\n")

        except Exception as e:
            logger.error(f"💥 [CRITICAL CONSUMER BREAKDOWN] Processing exception occurred: {str(e)}", exc_info=True)

async def start_consumer():
    """RabbitMQ connection resilience monitor loop that honors shutdown signals"""
    RABBITMQ_URL = "amqp://guest:guest@127.0.0.1:5672/"
    
    while True:
        try:
            logger.info(f"🔌 [AMQP CONNECT] Connecting to broker instance link: {RABBITMQ_URL}")
            connection = await aio_pika.connect_robust(RABBITMQ_URL, timeout=5)
            channel = await connection.channel()
            
            exchange = await channel.declare_exchange(
                "foodexpress", 
                type=aio_pika.ExchangeType.TOPIC,
                durable=True
            )
            
            queue = await channel.declare_queue(
                "notification-service-queue", 
                durable=True
            )
            
            await queue.bind(exchange, routing_key="order.created")
            await queue.bind(exchange, routing_key="order.status_changed")
            
            logger.info("🚀 [SYSTEM READY] Notification Consumer actively watching channels [order.created, order.status_changed]...")
            
            async with connection:
                await queue.consume(process_event)
                while True:
                    await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            # 🔴 CRITICAL: When FastAPI cancels this task on shutdown/reload, 
            # we catch it, log it, and cleanly exit the function (break the while loop).
            logger.info("🛑 [SYSTEM SHUTDOWN] Consumer task received cancellation signal. Cleaning up and exiting...")
            break
            
        except (aio_pika.exceptions.AMQPConnectionError, asyncio.TimeoutError) as err:
            # Only catch actual network/timeout errors for reconnection routines
            logger.warning(f"🔄 [CONNECTION FAILED] Reason: {str(err)}. Re-attempting handshake in 5 seconds...")
            await asyncio.sleep(5)
            
        except Exception as general_err:
            logger.error(f"💥 [UNKNOWN ERROR] {str(general_err)}. Retrying in 5 seconds...")
            await asyncio.sleep(5)