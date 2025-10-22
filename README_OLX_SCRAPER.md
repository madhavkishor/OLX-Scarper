OLX Car Cover Scraper
=====================

Files:
 - olx_car_cover_scraper.py  : Python script that scrapes OLX search results and saves JSON + CSV.
 - olx_car_cover_results.json: (created when you run the script) JSON output of results.
 - olx_car_cover_results.csv : (created when you run the script) CSV output of results.

How to run:
1. Install dependencies:
   pip install requests beautifulsoup4

2. Run the script:
   python olx_car_cover_scraper.py --url "https://www.olx.in/items/q-car-cover" --pages 1 --visit-details

   Use --pages to attempt additional search result pages. If OLX uses JavaScript to load results,
   consider using Selenium or Playwright; the script has a --use-selenium flag as a hint to extend it.

How to put this on GitHub (example commands):
  git init
  git add olx_car_cover_scraper.py README.md
  git commit -m "Add OLX car-cover scraper script"
  # create a new repository on GitHub (via web UI) or use gh CLI, then:
  git remote add origin https://github.com/your-username/your-repo.git
  git branch -M main
  git push -u origin main

Notes:
 - I cannot push to your GitHub for you (no credentials). Follow the commands above to create a repo and push.
 - If you want, paste your repo link here and I can review the code / provide a ready-to-run variant.
