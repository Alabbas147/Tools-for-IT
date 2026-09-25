import io
import httpx
import yt_dlp
import zipfile
import pymupdf as fitz
from PIL import Image
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

app = FastAPI(title="Freelance Calculator API")

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Tools-for-IT FastAPI backend is running successfully on Vercel"
    }

# Enable CORS so your WordPress site can talk to this Python server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RateRequest(BaseModel):
    desired_income: float
    billable_hours_per_week: float
    vacation_weeks: float
    annual_expenses: float
    tax_rate_percent: float

class AICostRequest(BaseModel):
    provider: str
    input_tokens_per_req: float
    output_tokens_per_req: float
    requests_per_day: float

class ProjectScopeRequest(BaseModel):
    project_type: str
    design_complexity: str
    page_count: int
    features: list[str]
    rush_delivery: bool

class RedirectAuditRequest(BaseModel):
    url: str

class HtaccessRequest(BaseModel):
    force_https: bool = True
    www_redirect: str = "none"
    custom_redirects: list[dict] = []
    enable_litespeed_cache: bool = False
    enable_cors: bool = False

class VideoRequest(BaseModel):
    url: str

MODEL_PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
    "gemini-1-5-pro": {"input": 1.25, "output": 5.00},
    "llama-3-70b": {"input": 0.60, "output": 0.80}
}

BASE_RATES = {
    "landing_page": 800,
    "business_site": 2500,
    "e_commerce": 4500,
    "web_app": 7500
}

DESIGN_MULTIPLIERS = {
    "template": 1.0,
    "custom_modern": 1.3,
    "neo_brutalism_3d": 1.6
}

FEATURE_COSTS = {
    "cms": 400,
    "auth": 600,
    "payment": 800,
    "api_integration": 1200,
    "seo_audit": 500
}

@app.post("/calculate-rate")
def calculate_rate(data: RateRequest):
    working_weeks = 52 - data.vacation_weeks
    total_billable_hours = working_weeks * data.billable_hours_per_week
    
    if total_billable_hours <= 0:
        return {"error": "Billable hours must be greater than zero."}

    gross_income_needed = data.desired_income + data.annual_expenses
    total_revenue_required = gross_income_needed / (1 - (data.tax_rate_percent / 100))
    hourly_rate = total_revenue_required / total_billable_hours
    
    return {
        "hourly_rate": round(hourly_rate, 2),
        "total_annual_revenue": round(total_revenue_required, 2),
        "total_billable_hours": round(total_billable_hours, 1)
    }

@app.post("/calculate-ai-cost")
def calculate_ai_cost(data: AICostRequest):
    pricing = MODEL_PRICING.get(data.provider.lower())
    if not pricing:
        return {"error": "Invalid model selected."}

    daily_input_tokens = (data.input_tokens_per_req * data.requests_per_day) / 1_000_000
    daily_output_tokens = (data.output_tokens_per_req * data.requests_per_day) / 1_000_000

    daily_input_cost = daily_input_tokens * pricing["input"]
    daily_output_cost = daily_output_tokens * pricing["output"]
    daily_total = daily_input_cost + daily_output_cost

    monthly_total = daily_total * 30
    yearly_total = daily_total * 365

    return {
        "model": data.provider,
        "daily_cost": round(daily_total, 2),
        "monthly_cost": round(monthly_total, 2),
        "yearly_cost": round(yearly_total, 2),
        "total_monthly_tokens_m": round((daily_input_tokens + daily_output_tokens) * 30, 2)
    }

@app.post("/estimate-project")
def estimate_project(data: ProjectScopeRequest):
    base = BASE_RATES.get(data.project_type, 2000)
    design_mult = DESIGN_MULTIPLIERS.get(data.design_complexity, 1.0)

    extra_pages = max(0, data.page_count - 3)
    page_cost = extra_pages * 150

    feature_total = sum(FEATURE_COSTS.get(feature, 0) for feature in data.features)

    subtotal = (base + page_cost + feature_total) * design_mult
    rush_fee = subtotal * 0.3 if data.rush_delivery else 0
    total_estimate = round(subtotal + rush_fee)
    estimated_weeks = round(max(1, total_estimate / 1200), 1)

    return {
        "total_estimate": total_estimate,
        "estimated_weeks": estimated_weeks,
        "breakdown": {
            "base_type_cost": base,
            "design_multiplier": design_mult,
            "extra_page_cost": page_cost,
            "features_cost": feature_total,
            "rush_fee": round(rush_fee)
        }
    }

@app.post("/audit-redirects")
async def audit_redirects(data: RedirectAuditRequest):
    target_url = data.url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    chain = []

    # Custom headers mimicking a real browser to prevent Facebook/Cloudflare blocks
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, headers=headers, verify=False) as client:
            response = await client.get(target_url)

            # Record intermediate redirects
            for resp in response.history:
                chain.append({
                    "status_code": resp.status_code,
                    "url": str(resp.url),
                    "location": resp.headers.get("location", "N/A")
                })

            # Record final landing destination
            chain.append({
                "status_code": response.status_code,
                "url": str(response.url),
                "location": "Final Destination"
            })

            return {
                "initial_url": target_url,
                "total_hops": len(response.history),
                "final_url": str(response.url),
                "chain": chain
            }

    except Exception as e:
        return {"error": f"Failed to trace URL: {str(e)}"}

@app.post("/convert-pdf-to-images")
async def convert_pdf_to_images(file: UploadFile = File(...)):
    # Read the uploaded PDF file
    pdf_bytes = await file.read()

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return {"error": f"Invalid PDF file: {str(e)}"}

    # Create an in-memory ZIP archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=150)  # Render at 150 DPI for sharp image quality
            img_bytes = pix.tobytes("png")
            zip_file.writestr(f"page_{page_num + 1}.png", img_bytes)

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=pdf_pages_png.zip"}
    )

@app.post("/convert-image")
async def convert_image(
    files: list[UploadFile] = File(...),
    output_format: str = Form("WEBP"),
    quality: int = Form(80)
):
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for index, uploaded_file in enumerate(files):
            # Read image file
            image_bytes = await uploaded_file.read()
            img = Image.open(io.BytesIO(image_bytes))

            # Convert RGBA to RGB if saving as JPEG
            if output_format.upper() == "JPEG" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            output_io = io.BytesIO()
            fmt = output_format.upper()
            ext = "webp" if fmt == "WEBP" else ("jpg" if fmt == "JPEG" else "png")

            # Save with specified compression quality
            if fmt in ["WEBP", "JPEG"]:
                img.save(output_io, format=fmt, quality=quality, optimize=True)
            else:
                img.save(output_io, format=fmt, optimize=True)

            output_io.seek(0)

            # Name file base + index
            base_name = uploaded_file.filename.rsplit(".", 1)[0]
            zip_file.writestr(f"{base_name}_optimized.{ext}", output_io.getvalue())

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=optimized_images.zip"}
    )

@app.post("/convert-images-to-pdf")
async def convert_images_to_pdf(files: list[UploadFile] = File(...)):
    image_list = []

    for uploaded_file in files:
        contents = await uploaded_file.read()
        img = Image.open(io.BytesIO(contents))

        # Convert RGBA/PNG with transparency to RGB for PDF export
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        image_list.append(img)

    if not image_list:
        return {"error": "No valid images uploaded"}

    pdf_buffer = io.BytesIO()
    # Save first image and append the remaining images into a single PDF
    image_list[0].save(pdf_buffer, format="PDF", save_all=True, append_images=image_list[1:])
    pdf_buffer.seek(0)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=compiled_images.pdf"}
    )

@app.post("/generate-htaccess")
async def generate_htaccess(data: HtaccessRequest):
    rules = [
        "# =============================================",
        "# GENERATED HTACCESS DIRECTIVES",
        "# =============================================",
        ""
    ]

    rules.append("<IfModule mod_rewrite.c>")
    rules.append("RewriteEngine On")
    rules.append("RewriteBase /")

    # 1. Force HTTPS
    if data.force_https:
        rules.append("\n# Force HTTPS")
        rules.append("RewriteCond %{HTTPS} off")
        rules.append("RewriteRule ^(.*)$ https://%{HTTP_HOST}%{REQUEST_URI} [L,R=301]")

    # 2. WWW Domain Standardization
    if data.www_redirect == "force_www":
        rules.append("\n# Force WWW")
        rules.append("RewriteCond %{HTTP_HOST} !^www\\. [NC]")
        rules.append("RewriteRule ^(.*)$ https://www.%{HTTP_HOST}/$1 [L,R=301]")
    elif data.www_redirect == "remove_www":
        rules.append("\n# Remove WWW")
        rules.append("RewriteCond %{HTTP_HOST} ^www\\.(.+) [NC]")
        rules.append("RewriteRule ^(.*)$ https://%1/$1 [L,R=301]")

    # 3. Custom Page Redirects
    if data.custom_redirects:
        rules.append("\n# Custom URL Redirects")
        for redirect in data.custom_redirects:
            source = redirect.get("source", "").strip()
            target = redirect.get("target", "").strip()
            redirect_type = redirect.get("type", "301")
            if source and target:
                rules.append(f"Redirect {redirect_type} {source} {target}")

    rules.append("</IfModule>")

    # 4. LiteSpeed Cache Integration
    if data.enable_litespeed_cache:
        rules.append("\n# =============================================")
        rules.append("# LITESPEED CACHE RULES")
        rules.append("# =============================================")
        rules.append("<IfModule LiteSpeed>")
        rules.append("CacheEnable public /")
        rules.append("CacheHeader on")
        rules.append("</IfModule>")

    # 5. CORS Headers
    if data.enable_cors:
        rules.append("\n# Enable CORS Headers")
        rules.append("<IfModule mod_headers.c>")
        rules.append('Header set Access-Control-Allow-Origin "*"')
        rules.append("</IfModule>")

    return {"htaccess_code": "\n".join(rules)}

@app.post("/extract-video")
async def extract_video(data: VideoRequest):
    video_url = data.url.strip()
    if not video_url.startswith(("http://", "https://")):
        video_url = "https://" + video_url

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "best[ext=mp4]/best",
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            # Extract video metadata
            title = info.get("title", "Social Video")
            thumbnail = info.get("thumbnail", "")
            duration = info.get("duration", 0)
            direct_url = info.get("url", "")
            uploader = info.get("uploader", info.get("extractor", "Unknown"))

            # Format duration into MM:SS
            minutes, seconds = divmod(duration or 0, 60)
            duration_str = f"{minutes:02d}:{seconds:02d}" if duration else "N/A"

            return {
                "title": title,
                "thumbnail": thumbnail,
                "duration": duration_str,
                "uploader": uploader,
                "download_url": direct_url
            }

    except Exception as e:
        return {"error": f"Failed to process video link: {str(e)}"}


