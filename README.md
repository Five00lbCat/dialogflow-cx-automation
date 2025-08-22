# Dialogflow CX Bulk Flow Automation


A production-ready automation system that converts CSV-formatted conversation flows into fully configured Dialogflow CX agents. Designed to eliminate hundreds of hours of manual configuration work, the system provides error-tolerant, scalable infrastructure for conversational AI deployment.


---


## Features


- **Bulk CSV to Dialogflow conversion** – Process hundreds of flows in minutes.
- **Intelligent route mapping** – Automatically creates pages, intents, and routes.
- **End state detection** – Identifies and manages conversation endpoints.
- **Webhook integration** – Connects to external services via dispatcher.
- **Error resilience** – Gracefully handles malformed or incomplete data.
- **Comprehensive logging** – Generates detailed reports for every operation.


---


## Quick Start


### Prerequisites
- Python 3.8+
- Google Cloud project with Dialogflow CX API enabled
- Service account with Dialogflow Admin permissions


### Installation
```bash
# Clone repository
git clone https://github.com/yourusername/dialogflow-automation.git
cd dialogflow-automation


# Install dependencies
pip install -r requirements.txt


# Configure project
cp config.example.json config.json
# Edit config.json with your project details


# Add your Google Cloud service account key
mv path/to/service-account.json ./service-account.json
```


### Usage
Convert a single CSV:
```bash
python csv_to_dialogflow_json.py input.csv --output output.json
```


Bulk process all CSVs:
```bash
python bulk_automation.py --config config.json --input-dir csv_files
```


---


## CSV Format


Each CSV should follow the schema below:


| Column | Description | Required |
|--------------------------|---------------------------------------------------------|----------|
| Page Name | Dialogflow page identifier | Yes |
| Intent Name | Intent identifier | No |
| Trigger Type & Example | Format: `"Intent: User says 'example'"` | Yes |
| Bot Prompt | Bot’s response text | Yes |
| Next Page / Transition | Target page(s), slash-separated if multiple | No |
| Parameter Set | Key=value pairs, comma-separated | No |
| Webhook Action | Plain English webhook description | No |
| Suggested Chips | Quick reply options, one per line | No |


See `examples/example.csv` for a complete reference.


---


## Architecture


```
CSV Files → Converter → JSON → Uploader → Dialogflow CX
↓
Dispatcher → External Services
```


### Core Components
- **csv_to_dialogflow_json.py** – Converts CSV flows to Dialogflow-compatible JSON.
- **upload_to_dialogflow.py** – Uploads JSON to Dialogflow via API.
- **bulk_automation.py** – Orchestrates batch conversion and upload.
- **dispatcher/app.py** – Webhook handler for external integrations.


---


## Advanced Features


**End State Detection**
Automatically identifies terminal states when no transitions are specified.


**Webhook Intelligence**
Maps plain-English descriptions to function calls:
Developed as part of Dartmouth College’s Evergreen project to automate the deployment of student support chatbots.
