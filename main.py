from fastapi import FastAPI, Request, Form, HTTPException, Header, Cookie, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from typing import Optional
import os

from app.ai_engine import ContentRepurposer
from app.stripe_handler import StripePayments, PLANS
from app.auth import AuthSystem, ensure_data_dir

# Ensure data folder exists on startup
ensure_data_dir()

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="ContentBlast",
    description="AI-powered content repurposing tool",
    version="1.0.0"
)

# Mount static files and templates
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize services
repurposer = ContentRepurposer()
payments = StripePayments()
auth = AuthSystem()


# Helper to get current user
def get_current_user(session_token: str = None):
    if not session_token:
        return None
    return AuthSystem.get_user_from_session(session_token)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Landing page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/app", response_class=HTMLResponse)
async def dashboard(request: Request, session_token: Optional[str] = Cookie(None)):
    """Main application dashboard"""
    user = get_current_user(session_token)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, session_token: Optional[str] = Cookie(None)):
    """Login page"""
    user = get_current_user(session_token)
    if user:
        return RedirectResponse(url="/app", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, session_token: Optional[str] = Cookie(None)):
    """Register page"""
    user = get_current_user(session_token)
    if user:
        return RedirectResponse(url="/app", status_code=302)
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/pricing", response_class=HTMLResponse)
async def pricing(request: Request, session_token: Optional[str] = Cookie(None)):
    """Pricing page"""
    user = get_current_user(session_token)
    return templates.TemplateResponse("pricing.html", {"request": request, "plans": PLANS, "user": user})


@app.get("/success", response_class=HTMLResponse)
async def success(request: Request):
    """Payment success page"""
    return templates.TemplateResponse("success.html", {"request": request})


# Auth API endpoints
@app.post("/api/register")
async def api_register(
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    name: str = Form(default="")
):
    """Register new user."""
    result = AuthSystem.register(email, password, name)

    if result.get("success"):
        # Auto-login after registration
        login_result = AuthSystem.login(email, password)
        if login_result.get("success"):
            response = JSONResponse(content={"success": True, "redirect": "/app"})
            response.set_cookie(
                key="session_token",
                value=login_result["session_token"],
                max_age=7*24*60*60,  # 7 days
                httponly=True,
                samesite="lax"
            )
            return response

    return JSONResponse(content=result)


@app.post("/api/login")
async def api_login(
    response: Response,
    email: str = Form(...),
    password: str = Form(...)
):
    """Login user."""
    result = AuthSystem.login(email, password)

    if result.get("success"):
        response = JSONResponse(content={"success": True, "redirect": "/app", "user": result["user"]})
        response.set_cookie(
            key="session_token",
            value=result["session_token"],
            max_age=7*24*60*60,
            httponly=True,
            samesite="lax"
        )
        return response

    return JSONResponse(content=result)


@app.post("/api/logout")
async def api_logout(response: Response, session_token: Optional[str] = Cookie(None)):
    """Logout user."""
    if session_token:
        AuthSystem.logout(session_token)

    response = JSONResponse(content={"success": True, "redirect": "/"})
    response.delete_cookie(key="session_token")
    return response


@app.get("/api/me")
async def api_me(session_token: Optional[str] = Cookie(None)):
    """Get current user info."""
    user = get_current_user(session_token)
    if user:
        return JSONResponse(content={"success": True, "user": user})
    return JSONResponse(content={"success": False, "error": "Not logged in"})


@app.post("/api/repurpose")
async def repurpose_content(
    content: str = Form(...),
    content_type: str = Form(default="article"),
    session_token: Optional[str] = Cookie(None)
):
    """
    API endpoint to repurpose content.
    """
    # Check user and limits
    user = get_current_user(session_token)

    if user:
        # Check repurpose limit
        if user["repurposes_limit"] > 0 and user["repurposes_used"] >= user["repurposes_limit"]:
            raise HTTPException(
                status_code=403,
                detail="Repurpose limit reached. Please upgrade your plan!"
            )

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
        # Use repurpose credit if logged in
        if user:
            usage = AuthSystem.use_repurpose(user["email"])
            result["repurposes_remaining"] = usage.get("repurposes_remaining", 0)

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
