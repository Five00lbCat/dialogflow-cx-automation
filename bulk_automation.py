#!/usr/bin/env python3
"""
Complete Bulk Automation Pipeline for Google Sheets to Dialogflow CX
This script handles the entire pipeline from CSV conversion to Dialogflow upload.
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import time
from datetime import datetime

# Import the converter and uploader modules
# Note: Make sure csv_to_dialogflow_json.py and upload_to_dialogflow.py are in the same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from csv_to_dialogflow_json import convert_single_csv, convert_bulk
    from upload_to_dialogflow import DialogflowUploader
except ImportError:
    print("Error: Required modules not found. Make sure csv_to_dialogflow_json.py and upload_to_dialogflow.py are in the same directory.")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'dialogflow_automation_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DialogflowAutomation:
    """Main automation class that orchestrates the entire process."""
    
    def __init__(self, config: Dict[str, any]):
        """Initialize with configuration."""
        self.config = config
        self.results = {
            'csv_conversions': {'success': [], 'failed': []},
            'uploads': {'success': [], 'failed': []},
            'statistics': {}
        }
        
        # Initialize uploader if credentials provided
        if all(k in config for k in ['service_account', 'project_id', 'agent_id', 'dispatcher_url']):
            self.uploader = DialogflowUploader(
                service_account_file=config['service_account'],
                project_id=config['project_id'],
                location=config.get('location', 'us-central1'),
                agent_id=config['agent_id'],
                dispatcher_url=config['dispatcher_url'],
                dispatcher_header=config.get('dispatcher_header')
            )
        else:
            self.uploader = None
            logger.warning("Uploader not initialized - missing required configuration")
    
    def validate_environment(self) -> bool:
        """Validate that all required files and configurations are present."""
        issues = []
        
        # Check service account file
        if self.config.get('service_account'):
            sa_path = Path(self.config['service_account'])
            if not sa_path.exists():
                issues.append(f"Service account file not found: {sa_path}")
        
        # Check input directory
        input_dir = Path(self.config.get('input_dir', '.'))
        if not input_dir.exists():
            issues.append(f"Input directory not found: {input_dir}")
        
        # Check for CSV files
        csv_files = list(input_dir.glob("*.csv"))
        if not csv_files:
            issues.append(f"No CSV files found in {input_dir}")
        
        if issues:
            for issue in issues:
                logger.error(issue)
            return False
        
        logger.info(f"Environment validation passed. Found {len(csv_files)} CSV files.")
        return True
    
    def convert_csvs(self) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Convert all CSV files to JSON format."""
        logger.info("=" * 60)
        logger.info("PHASE 1: Converting CSV files to JSON")
        logger.info("=" * 60)
        
        input_dir = Path(self.config['input_dir'])
        output_dir = Path(self.config.get('json_dir', input_dir / 'dialogflow_json'))
        output_dir.mkdir(exist_ok=True)
        
        csv_files = list(input_dir.glob("*.csv"))
        successes = []
        failures = []
        
        for i, csv_file in enumerate(csv_files, 1):
            logger.info(f"Converting {i}/{len(csv_files)}: {csv_file.name}")
            
            try:
                output_file = output_dir / f"dialogflow_{csv_file.stem}.json"
                convert_single_csv(str(csv_file), str(output_file))
                successes.append(str(output_file))
                self.results['csv_conversions']['success'].append(csv_file.name)
                
            except Exception as e:
                logger.error(f"Failed to convert {csv_file.name}: {e}")
                failures.append((csv_file.name, str(e)))
                self.results['csv_conversions']['failed'].append({
                    'file': csv_file.name,
                    'error': str(e)
                })
        
        logger.info(f"Conversion complete: {len(successes)}/{len(csv_files)} successful")
        return successes, failures
    
    def upload_flows(self, json_files: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """Upload all JSON files to Dialogflow."""
        if not self.uploader:
            logger.error("Uploader not initialized - skipping upload phase")
            return [], [(f, "Uploader not configured") for f in json_files]
        
        logger.info("=" * 60)
        logger.info("PHASE 2: Uploading flows to Dialogflow")
        logger.info("=" * 60)
        
        successes = []
        failures = []
        
        for i, json_file in enumerate(json_files, 1):
            logger.info(f"Uploading {i}/{len(json_files)}: {Path(json_file).name}")
            
            try:
                success, result = self.uploader.upload_single_flow(json_file)
                if success:
                    successes.append(result)
                    self.results['uploads']['success'].append(Path(json_file).name)
                else:
                    failures.append((Path(json_file).name, result))
                    self.results['uploads']['failed'].append({
                        'file': Path(json_file).name,
                        'error': result
                    })
                
                # Rate limiting
                if i < len(json_files):
                    time.sleep(self.config.get('upload_delay', 2))
                    
            except Exception as e:
                logger.error(f"Failed to upload {Path(json_file).name}: {e}")
                failures.append((Path(json_file).name, str(e)))
                self.results['uploads']['failed'].append({
                    'file': Path(json_file).name,
                    'error': str(e)
                })
        
        logger.info(f"Upload complete: {len(successes)}/{len(json_files)} successful")
        return successes, failures
    
    def generate_report(self) -> str:
        """Generate a detailed report of the automation results."""
        report = []
        report.append("=" * 60)
        report.append("DIALOGFLOW AUTOMATION REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 60)
        
        # CSV Conversion Results
        report.append("\nCSV CONVERSION RESULTS:")
        report.append(f"  Successful: {len(self.results['csv_conversions']['success'])}")
        report.append(f"  Failed: {len(self.results['csv_conversions']['failed'])}")
        
        if self.results['csv_conversions']['failed']:
            report.append("\n  Failed conversions:")
            for item in self.results['csv_conversions']['failed']:
                report.append(f"    - {item['file']}: {item['error']}")
        
        # Upload Results
        report.append("\nDIALOGFLOW UPLOAD RESULTS:")
        report.append(f"  Successful: {len(self.results['uploads']['success'])}")
        report.append(f"  Failed: {len(self.results['uploads']['failed'])}")
        
        if self.results['uploads']['failed']:
            report.append("\n  Failed uploads:")
            for item in self.results['uploads']['failed']:
                report.append(f"    - {item['file']}: {item['error']}")
        
        # Statistics
        if self.results['statistics']:
            report.append("\nSTATISTICS:")
            for key, value in self.results['statistics'].items():
                report.append(f"  {key}: {value}")
        
        report.append("\n" + "=" * 60)
        
        report_text = "\n".join(report)
        
        # Save report to file
        report_file = f"automation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report_text)
        
        logger.info(f"Report saved to {report_file}")
        return report_text
    
    def run(self) -> bool:
        """Run the complete automation pipeline."""
        logger.info("Starting Dialogflow automation pipeline")
        start_time = time.time()
        
        # Validate environment
        if not self.validate_environment():
            logger.error("Environment validation failed. Aborting.")
            return False
        
        # Phase 1: Convert CSVs to JSON
        json_files, csv_failures = self.convert_csvs()
        
        if not json_files:
            logger.error("No JSON files created. Aborting upload phase.")
            self.generate_report()
            return False
        
        # Phase 2: Upload to Dialogflow (if configured)
        if self.config.get('skip_upload'):
            logger.info("Skipping upload phase (skip_upload=True)")
        else:
            upload_successes, upload_failures = self.upload_flows(json_files)
        
        # Calculate statistics
        elapsed_time = time.time() - start_time
        self.results['statistics'] = {
            'Total processing time': f"{elapsed_time:.2f} seconds",
            'CSV files processed': len(list(Path(self.config['input_dir']).glob("*.csv"))),
            'JSON files created': len(json_files),
            'Flows uploaded': len(self.results['uploads']['success'])
        }
        
        # Generate report
        report = self.generate_report()
        print("\n" + report)
        
        # Return success if at least some files were processed successfully
        return len(json_files) > 0

def load_config(config_file: Optional[str] = None) -> Dict[str, any]:
    """Load configuration from file or environment variables."""
    config = {}
    
    # Try loading from config file
    if config_file and Path(config_file).exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    
    # Override with environment variables
    env_mapping = {
        'DIALOGFLOW_SERVICE_ACCOUNT': 'service_account',
        'DIALOGFLOW_PROJECT_ID': 'project_id',
        'DIALOGFLOW_LOCATION': 'location',
        'DIALOGFLOW_AGENT_ID': 'agent_id',
        'DISPATCHER_URL': 'dispatcher_url',
        'DISPATCHER_HEADER': 'dispatcher_header',
        'INPUT_DIR': 'input_dir',
        'JSON_DIR': 'json_dir'
    }
    
    for env_key, config_key in env_mapping.items():
        if env_key in os.environ:
            config[config_key] = os.environ[env_key]
    
    return config

def main():
    parser = argparse.ArgumentParser(
        description="Automated pipeline for converting Google Sheets CSVs to Dialogflow CX flows"
    )
    
    # Input/Output options
    parser.add_argument('--input-dir', default='.', help='Directory containing CSV files')
    parser.add_argument('--json-dir', help='Directory for JSON output (default: input_dir/dialogflow_json)')
    
    # Dialogflow configuration
    parser.add_argument('--service-account', help='Service account JSON file')
    parser.add_argument('--project-id', help='GCP project ID')
    parser.add_argument('--location', default='us-central1', help='Dialogflow location')
    parser.add_argument('--agent-id', help='Dialogflow agent ID')
    
    # Dispatcher configuration
    parser.add_argument('--dispatcher-url', help='Dispatcher webhook URL')
    parser.add_argument('--dispatcher-header', help='Optional header for dispatcher (format: Key=Value)')
    
    # Processing options
    parser.add_argument('--skip-upload', action='store_true', help='Only convert CSVs, skip upload')
    parser.add_argument('--upload-delay', type=int, default=2, help='Delay between uploads in seconds')
    parser.add_argument('--config', help='JSON config file with all settings')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Override with command line arguments
    for key, value in vars(args).items():
        if value is not None and key != 'config':
            config[key] = value
    
    # Validate minimum required configuration
    if not config.get('input_dir'):
        logger.error("Input directory is required (--input-dir or INPUT_DIR env var)")
        sys.exit(1)
    
    if not config.get('skip_upload'):
        required = ['service_account', 'project_id', 'agent_id', 'dispatcher_url']
        missing = [k for k in required if not config.get(k)]
        if missing:
            logger.error(f"Missing required configuration for upload: {missing}")
            logger.info("Use --skip-upload to only convert CSVs without uploading")
            sys.exit(1)
    
    # Run automation
    automation = DialogflowAutomation(config)
    success = automation.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()