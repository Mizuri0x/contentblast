import os
import stripe
from typing import Dict, Optional

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Pricing plans
PLANS = {
    "starter": {
        "name": "Starter",
        "price": 1900,  # $19.00 in cents
        "repurposes": 50,
        "features": ["50 repurposes/month", "All platforms", "Email support"]
    },
    "pro": {
        "name": "Pro", 
        "price": 4900,  # $49.00 in cents
        "repurposes": 200,
        "features": ["200 repurposes/month", "All platforms", "Priority support", "API access"]
    },
    "unlimited": {
        "name": "Unlimited",
        "price": 9900,  # $99.00 in cents
        "repurposes": -1,  # unlimited
        "features": ["Unlimited repurposes", "All platforms", "24/7 support", "Custom integrations"]
    }
}

class StripePayments:
    """
    Stripe payment handler for ContentBlast subscriptions.
    """

    @staticmethod
    def create_checkout_session(
        plan_id: str,
        success_url: str,
        cancel_url: str,
        customer_email: Optional[str] = None
    ) -> Dict:
        """
        Create a Stripe Checkout session for subscription.
        """
        if plan_id not in PLANS:
            return {"success": False, "error": "Invalid plan"}

        plan = PLANS[plan_id]

        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="subscription",
                customer_email=customer_email,
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"ContentBlast {plan['name']}",
                            "description": f"{plan['repurposes']} repurposes per month" if plan['repurposes'] > 0 else "Unlimited repurposes",
                        },
                        "unit_amount": plan["price"],
                        "recurring": {"interval": "month"}
                    },
                    "quantity": 1,
                }],
                success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
                cancel_url=cancel_url,
                metadata={
                    "plan_id": plan_id,
                    "repurposes": str(plan["repurposes"])
                }
            )

            return {
                "success": True,
                "session_id": session.id,
                "checkout_url": session.url
            }

        except stripe.error.StripeError as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def handle_webhook(payload: bytes, sig_header: str, webhook_secret: str) -> Dict:
        """
        Handle Stripe webhook events.
        """
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, webhook_secret
            )
        except ValueError:
            return {"success": False, "error": "Invalid payload"}
        except stripe.error.SignatureVerificationError:
            return {"success": False, "error": "Invalid signature"}

        # Handle events
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            # Here you would activate the subscription in your database
            return {
                "success": True,
                "event": "subscription_created",
                "customer_email": session.get("customer_email"),
                "plan_id": session.get("metadata", {}).get("plan_id")
            }

        elif event["type"] == "customer.subscription.deleted":
            # Handle cancellation
            return {"success": True, "event": "subscription_cancelled"}

        return {"success": True, "event": event["type"]}

    @staticmethod
    def get_plans() -> Dict:
        """Return available plans."""
        return PLANS
