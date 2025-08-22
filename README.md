# Dialogflow CX Bulk Flow Automation

A powerful automation system that converts CSV-formatted conversation flows into Dialogflow CX agents, saving hours of manual configuration work.

## 🎯 Features

- **Bulk CSV to Dialogflow conversion** - Process hundreds of flows in minutes
- **Intelligent route mapping** - Automatically creates pages, intents, and routes
- **End state detection** - Identifies and handles conversation endpoints
- **Webhook integration** - Supports external service calls via dispatcher
- **Error resilience** - Gracefully handles data inconsistencies
- **Detailed logging** - Comprehensive reports for every operation

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Google Cloud Project with Dialogflow API enabled
- Service Account with Dialogflow Admin permissions

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/dialogflow-automation.git
cd dialogflow-automation

Install dependencies:

pip install -r requirements.txt

Set up configuration:

cp config.example.json config.json
# Edit config.json with your project details

Add your service account JSON file as service-account.json

Usage
Convert a single CSV:

python csv_to_dialogflow_json.py input.csv --output output.json

Bulk process all CSVs:

python bulk_automation.py --config config.json --input-dir csv_files

CSV Format
Your CSV files should have these columns:
ColumnDescriptionRequiredPage NameDialogflow page identifierYesIntent NameIntent identifierNoTrigger Type & User ExampleFormat: "Intent: User says 'example'"YesBot PromptBot's response textYesNext Page / TransitionTarget page(s), can be slash-separatedNoParameter SetKey=value pairs, comma-separatedNoWebhook ActionPlain English webhook descriptionNoSuggested ChipsQuick reply options, one per lineNo

See example.csv for a complete example.

Architecture

CSV Files → Converter → JSON → Uploader → Dialogflow CX
                           ↓
                      Dispatcher → External Services

Components

csv_to_dialogflow_json.py - Converts CSV to Dialogflow-compatible JSON
upload_to_dialogflow.py - Uploads JSON to Dialogflow via API
bulk_automation.py - Orchestrates bulk processing pipeline
dispatcher/app.py - Webhook handler for external integrations

🎨 Advanced Features
End State Detection
Automatically identifies conversation endpoints when no "Next Page" is specified.
Webhook Intelligence
Converts plain English webhook descriptions to function calls:

"fetch upcoming assignments" → fetch_upcoming_assignments()
"save user preferences" → save_user_preferences()

Parameter Handling
Supports session parameters for maintaining conversation context.
📈 Performance

Processes ~100 flows in under 5 minutes
Handles flows with 50+ pages and 100+ routes
Gracefully manages API rate limits

🤝 Contributing
Contributions are welcome! Please feel free to submit a Pull Request.
📝 License
MIT License - see LICENSE file for details
🙏 Acknowledgments
Built for automating Dartmouth College's student support chatbots.