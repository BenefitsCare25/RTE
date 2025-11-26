# Company Data Enrichment Platform

A web-based platform that enriches company data from Excel uploads by automatically extracting contact information including phone numbers, email addresses, and founder/director names.

## Features

- **Excel Upload**: Drag-and-drop interface for uploading Excel files
- **Automated Data Enrichment**: Uses web search and scraping to find company contact details
- **Contact Extraction**: Extracts phone numbers (Singapore format), email addresses, and founder names
- **Instant Download**: Get enriched Excel file immediately after processing
- **Stateless Design**: No data storage, privacy-focused approach

## Tech Stack

### Backend
- **FastAPI**: Modern Python web framework
- **Playwright**: Browser automation for web scraping
- **SerpAPI**: Google Custom Search integration
- **pandas & openpyxl**: Excel file processing

### Frontend
- **React 18**: Modern React with hooks
- **TypeScript**: Type-safe development
- **Vite**: Fast build tool
- **TailwindCSS**: Utility-first styling
- **react-dropzone**: File upload component

## Project Structure

```
company-enrichment-platform/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application
│   │   ├── routers/
│   │   │   └── enrichment.py    # API endpoints
│   │   ├── services/
│   │   │   ├── excel_handler.py # Excel processing
│   │   │   ├── search.py        # Web search
│   │   │   └── scraper.py       # Web scraping
│   │   └── utils/
│   │       └── extractors.py    # Contact extraction patterns
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Upload.tsx       # File upload UI
│   │   │   └── Processing.tsx   # Loading indicator
│   │   ├── api/
│   │   │   └── client.ts        # API client
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── .env.example
└── README.md
```

## Local Development Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- SerpAPI account (free tier available)

### Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers:
```bash
playwright install chromium
```

5. Create `.env` file from example:
```bash
cp .env.example .env
```

6. Configure environment variables in `.env`:
```env
SERPAPI_KEY=your_serpapi_key_here
BING_SEARCH_KEY=your_bing_key_here (optional)
FRONTEND_URL=http://localhost:5173
SECRET_KEY=your_random_secret_key
ENVIRONMENT=development
```

7. Run development server:
```bash
uvicorn app.main:app --reload --port 8000
```

Backend will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create `.env` file from example:
```bash
cp .env.example .env
```

4. Configure environment variables in `.env`:
```env
VITE_API_URL=http://localhost:8000
```

5. Run development server:
```bash
npm run dev
```

Frontend will be available at `http://localhost:5173`

## Deployment on Render

### Step 1: Push to GitHub

1. Initialize git repository:
```bash
git init
git add .
git commit -m "Initial commit: Company enrichment platform"
```

2. Create GitHub repository and push:
```bash
git remote add origin https://github.com/yourusername/company-enrichment-platform.git
git branch -M main
git push -u origin main
```

### Step 2: Deploy Backend (Web Service)

1. Go to [Render Dashboard](https://dashboard.render.com/)

2. Click **"New +"** → **"Web Service"**

3. Connect your GitHub repository

4. Configure the service:
   - **Name**: `company-enrichment-api`
   - **Environment**: `Python 3`
   - **Region**: Choose closest to your users
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Build Command**: `pip install -r requirements.txt && playwright install chromium`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

5. Choose instance type:
   - **Recommended**: Standard or higher (for web scraping)
   - Starter may have memory limitations with Playwright

6. Add Environment Variables:
   - Click **"Advanced"** → **"Add Environment Variable"**
   - Add the following:

   ```
   SERPAPI_KEY = your_serpapi_key_here
   BING_SEARCH_KEY = your_bing_key_here (optional)
   FRONTEND_URL = https://your-frontend-name.onrender.com
   SECRET_KEY = <generate with: openssl rand -hex 32>
   ENVIRONMENT = production
   ```

7. Click **"Create Web Service"**

8. Wait for deployment to complete (5-10 minutes)

9. Copy your backend URL (e.g., `https://company-enrichment-api.onrender.com`)

### Step 3: Deploy Frontend (Static Site)

1. In Render Dashboard, click **"New +"** → **"Static Site"**

2. Connect your GitHub repository

3. Configure the service:
   - **Name**: `company-enrichment-frontend`
   - **Branch**: `main`
   - **Root Directory**: `frontend`
   - **Build Command**: `npm install && npm run build`
   - **Publish Directory**: `dist`

4. Add Environment Variables:
   - Click **"Advanced"** → **"Add Environment Variable"**
   - Add:

   ```
   VITE_API_URL = https://your-backend-api.onrender.com
   ```

   Replace with your actual backend URL from Step 2

5. Click **"Create Static Site"**

6. Wait for deployment to complete (3-5 minutes)

7. Your frontend will be available at `https://your-frontend-name.onrender.com`

### Step 4: Update Backend CORS

1. Go back to your backend service in Render

2. Update the `FRONTEND_URL` environment variable with your actual frontend URL:
   ```
   FRONTEND_URL = https://your-frontend-name.onrender.com
   ```

3. Backend will automatically redeploy with updated CORS settings

### Step 5: Get SerpAPI Key

1. Sign up at [SerpAPI](https://serpapi.com/)
2. Free tier includes 100 searches/month
3. Get your API key from dashboard
4. Add it to backend environment variables in Render

## Usage

1. **Visit the platform** at your Render frontend URL

2. **Prepare your Excel file** with the following columns:
   - `name` or `company name`: Company name
   - `uen` or `uen number`: Singapore UEN number
   - `address` or `company address`: Company address

3. **Upload the Excel file** via drag-and-drop or file selector

4. **Wait for processing** (typically 5-30 seconds per company)

5. **Download enriched file** automatically with new columns:
   - Phone Number
   - Email Address
   - Founder/Director
   - Website
   - Enrichment Status

## API Endpoints

### `POST /api/enrich`
Upload Excel file and get enriched data

**Request:**
- Content-Type: `multipart/form-data`
- Body: Excel file

**Response:**
- Content-Type: `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Body: Enriched Excel file

### `GET /api/status`
Check API health status

**Response:**
```json
{
  "status": "online",
  "message": "Company enrichment service is running"
}
```

### `GET /`
API information

**Response:**
```json
{
  "message": "Company Data Enrichment API",
  "status": "active",
  "version": "1.0.0"
}
```

## Troubleshooting

### Backend Issues

**Playwright fails to install:**
- Ensure instance type is Standard or higher
- Add `playwright install chromium` to build command

**SerpAPI quota exceeded:**
- Check your SerpAPI dashboard for usage
- Upgrade plan or wait for monthly reset

**CORS errors:**
- Verify `FRONTEND_URL` matches your actual frontend URL
- Include protocol (https://)

### Frontend Issues

**Can't connect to backend:**
- Verify `VITE_API_URL` is set correctly
- Check backend is deployed and running
- Ensure no trailing slash in API URL

**Build fails:**
- Clear node_modules and reinstall: `rm -rf node_modules && npm install`
- Check Node.js version compatibility (18+)

## Environment Variables Summary

### Backend Environment Variables (Render)
```
SERPAPI_KEY = <your_serpapi_key>
BING_SEARCH_KEY = <optional_bing_key>
FRONTEND_URL = <your_frontend_url>
SECRET_KEY = <random_secret_key>
ENVIRONMENT = production
```

### Frontend Environment Variables (Render)
```
VITE_API_URL = <your_backend_api_url>
```

## License

MIT License - Feel free to use and modify as needed.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Review Render logs for errors
3. Verify all environment variables are set correctly
4. Ensure SerpAPI key is valid and has quota remaining
