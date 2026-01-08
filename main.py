from fastapi import FastAPI, Request, Form, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import os

from app.ai_engine import ContentRepurposer
from app.stripe_handler import StripePayments, PLANS

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="ContentBlast",
    description="AI-powered content repurposing tool",
    version="1.0.0"
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize services
repurposer = ContentRepurposer()
payments = StripePayments()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/app", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main application dashboard"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@app.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request):
    """Pricing page"""
    return templates.TemplateResponse("pricing.html", {"request": request, "plans": PLANS})


@app.get("/success", response_class=HTMLResponse)
async def success(request: Request):
    """Payment success page"""
    return templates.TemplateResponse("success.html", {"request": request})


@app.post("/api/repurpose")
async def repurpose_content(
    content: str = Form(...),
    content_type: str = Form(default="article")
):
    """
    API endpoint to repurpose content.
    """
    if not content or len(content.strip()) < 50:
        raise HTTPException(
            status_code=400, 
            detail="Content must be at least 50 characters long"
        )

    if len(content) > 10000:
        raise HTTPException(
            status_code=400,
            detail="Content must be less than 10,000 characters"
        )

    # Get cost estimate
    estimate = repurposer.estimate_cost(content)

    # Repurpose content
    result = repurposer.repurpose(content, content_type)

    if result.get("success"):
        result["cost_estimate"] = estimate
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))


@app.post("/api/checkout")
async def create_checkout(request: Request, plan_id: str = Form(...), email: str = Form(None)):
    """
    Create Stripe checkout session.
    """
    base_url = str(request.base_url).rstrip("/")

    result = payments.create_checkout_session(
        plan_id=plan_id,
        success_url=f"{base_url}/success",
        cancel_url=f"{base_url}/pricing",
        customer_email=email
    )

    if result.get("success"):
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))


@app.post("/api/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """
    Handle Stripe webhooks.
    """
    payload = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    result = payments.handle_webhook(payload, stripe_signature, webhook_secret)

    if result.get("success"):
        return JSONResponse(content=result)
    else:
        raise HTTPException(status_code=400, detail=result.get("error"))


@app.get("/api/plans")
async def get_plans():
    """Get available plans."""
    return JSONResponse(content=PLANS)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "ContentBlast"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
