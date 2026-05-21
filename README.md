# Real-Estate Lead Automation Framework

An automated real-estate scraping, analysis, and lead-generation framework powered by Selenium, Google Gemini AI, and Firebase Realtime Database. This production-ready system streamlines property distribution across multiple social platforms while utilizing advanced AI to analyze and filter high-quality customer leads in real-time.

---

## 🚀 Key Features

* **Smart Generic Scraper:** Dynamically extracts target listings with support for advanced parameter matching (districts, pricing brackets, specific housing amenities).
* **AI-Powered Lead Extraction (Gemini 1.5 Flash):** Evaluates user posts natively to distinguish genuine renters/buyers from spam or hidden brokers, extracting exact budget parameters and geographical preferences.
* **Asynchronous Multi-threading:** Employs daemon threads to process network requests, manage live log queues, and execute platform automation concurrently without UI freezing.
* **Cloud-Based Token & Licensing Controller:** Integrated with Firebase Realtime Database via a custom REST API layer to enforce hardware ID (HWID) authentication, remote status monitoring, and real-time usage quota (Credits/Tokens) deductions.
* **Resilient Interaction Engine:** Features anti-fingerprinting configurations and dynamic DOM error recovery (`StaleElementReferenceException`) to navigate layout shifts during social media interactions.
* **Live HUD Monitoring:** Implements a standalone, zero-memory-leak logging dashboard using `customtkinter` to track execution metrics, operation runtimes, and real-time operational diagnostics.

---

## 🏗️ System Architecture

```text
+-------------------------------------------------------------+
|                     User Control Panel                      |
|             (CustomTkinter GUI Engine & Live HUD)           |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                   HWID Security Controller                  |
|          (Remote License Validation via Firebase REST)      |
+-------------------------------------------------------------+
                              |
       +----------------------+----------------------+
       | (Scraping Mode)                             | (Standalone Hunter Mode)
       v                                             v
+----------------------------+         +----------------------------+
|    Web Automation Core     |         |  Social Stream Monitoring  |
|     (Selenium WebDriver)   |         |    (Target Post Scanner)   |
+----------------------------+         +----------------------------+
       |                                             |
       |  [Extracts Property Listings]               |  [Intercepts Raw Social Leads]
       v                                             v
+----------------------------+         +----------------------------+
|    Dynamic Filter Engine   |         |      Gemini 1.5 Flash      |
|  (Amenity & Budget Match)  |         |   (Contextual NLP Parsing) |
+----------------------------+         +----------------------------+
       |                                             |
       |  [Structured Content Cache]                 |  [Verified Buyer Lead Matrix]
       +----------------------+----------------------+
                              |
                              v
+-------------------------------------------------------------+
|                  Omnichannel Action Layer                   |
|     (Zalo Album Dispatcher & Facebook Cross-Group Relays)   |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                     Firebase Telemetry                      |
|         (Operational Logs & Live Credit Deductions)         |
+-------------------------------------------------------------+
```
⚙️ Core Technical Stack
Language: Python 3.10+

Automation: Selenium WebDriver (Edge Engine)
Artificial Intelligence: Google Generative AI SDK (gemini-2.5-flash)
Database & Cloud Security: Firebase Realtime Database (REST API Integration)
Graphical Interface: CustomTkinter & Native Tkinter Event Queue
Data Processing: Pandas & OpenPyXL

## 📦 Installation & Setup

1. **Clone the Repository:**
```bash
git clone [https://github.com/YOUR_USERNAME/property-automation-framework.git](https://github.com/YOUR_USERNAME/property-automation-framework.git)
cd property-automation-framework```

```bash
pip install -r requirements.txt
(Note: Ensure you have customtkinter, google-generativeai, pandas, openpyxl, selenium, and python-dotenv installed).
```

Configure Environment Variables:
Create a .env file in the root directory based on the .env.example structure:

```
GEMINI_API_KEY=your_google_gemini_api_key
FIREBASE_URL=your_firebase_realtime_database_endpoint
TARGET_URL=your_target_property_website_url
Execute the Application:
```

```
Bash
python main.py
```
🔒 Security & Best Practices
Zero-Hardcode Principle: All credentials, target domains, and API endpoint hooks are fully externalized via environment variables (.env), keeping the core codebase abstract and clean for enterprise portfolio inspection.

Rate Limiting & Safety Cooldowns: Built-in adaptive delay modules and countdown mechanisms emulate human-like behavior, preventing rapid endpoint flooding or sudden security checkpoints on host networks.

📄 License
This project is licensed under the MIT License - see the LICENSE file for details. This repository is hosted strictly for educational purposes and technical evaluation.
