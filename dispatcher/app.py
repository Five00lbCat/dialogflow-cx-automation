from flask import Flask, request, jsonify
import os
import re
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import random

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================================
# WEBHOOK ACTION HANDLERS
# ================================

class WebhookHandlers:
    """
    This class contains all webhook handlers that can be called based on
    the webhook tags generated from plain English descriptions.
    """
    
    @staticmethod
    def fetch_upcoming_assignments(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Fetch upcoming assignments from Canvas/LMS."""
        user_id = WebhookHandlers._get_param(ctx, "user_id")
        
        # Simulate fetching assignments
        assignments = [
            {"title": "CS HW 3", "due": "2025-09-01", "course": "CS 101"},
            {"title": "Math Problem Set 5", "due": "2025-09-03", "course": "MATH 201"},
            {"title": "Essay Draft", "due": "2025-09-05", "course": "ENGL 150"}
        ]
        
        # Format response
        assignment_text = "Here are your upcoming assignments:\n"
        for a in assignments[:3]:  # Show top 3
            assignment_text += f"• {a['title']} ({a['course']}) - Due: {a['due']}\n"
        
        return {
            "sessionInfo": {"parameters": {"assignments": assignments}},
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [assignment_text]}}]
            }
        }
    
    @staticmethod
    def create_study_block(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Create a study block in the calendar."""
        params = WebhookHandlers._get_params(ctx)
        date = params.get("date", "tomorrow")
        time = params.get("time", "2:00 PM")
        duration = params.get("duration", "2 hours")
        subject = params.get("subject", "study session")
        
        response_text = f"✓ I've scheduled a {duration} {subject} for {date} at {time}."
        
        return {
            "sessionInfo": {"parameters": {"block_created": True, "date": date, "time": time}},
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [response_text]}}]
            }
        }
    
    @staticmethod
    def check_calendar_conflicts(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Check for calendar conflicts."""
        params = WebhookHandlers._get_params(ctx)
        date = params.get("date", "today")
        
        # Simulate checking calendar
        conflicts = random.choice([True, False])
        
        if conflicts:
            response = f"You have 2 conflicts on {date}:\n• Meeting at 10 AM\n• Class at 2 PM"
        else:
            response = f"Good news! You have no conflicts on {date}."
        
        return {
            "sessionInfo": {"parameters": {"has_conflicts": conflicts}},
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [response]}}]
            }
        }
    
    @staticmethod
    def get_time_management_tips(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Provide time management tips."""
        tips = [
            "Try the Pomodoro Technique: 25 minutes of focused work, then a 5-minute break.",
            "Use time blocking: Schedule specific time slots for different activities.",
            "Apply the 2-minute rule: If something takes less than 2 minutes, do it now.",
            "Prioritize with the Eisenhower Matrix: Urgent/Important quadrants.",
            "Batch similar tasks together to minimize context switching."
        ]
        
        selected_tips = random.sample(tips, min(3, len(tips)))
        response = "Here are some time management tips:\n"
        for tip in selected_tips:
            response += f"• {tip}\n"
        
        return {
            "sessionInfo": {"parameters": {"tips_provided": True}},
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [response]}}]
            }
        }
    
    @staticmethod
    def analyze_workload(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze current workload and provide insights."""
        # Simulate workload analysis
        workload_score = random.randint(60, 95)
        
        if workload_score > 80:
            assessment = "heavy"
            advice = "Consider prioritizing tasks and possibly dropping or postponing less critical activities."
        elif workload_score > 60:
            assessment = "moderate"
            advice = "Your workload is manageable. Stay organized and maintain your current pace."
        else:
            assessment = "light"
            advice = "You have capacity for additional activities if needed."
        
        response = f"Your current workload is {assessment} ({workload_score}/100).\n{advice}"
        
        return {
            "sessionInfo": {"parameters": {"workload_score": workload_score}},
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [response]}}]
            }
        }
    
    @staticmethod
    def suggest_break_activities(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest break activities."""
        activities = [
            "Take a 10-minute walk outside",
            "Do some light stretching",
            "Practice deep breathing for 5 minutes",
            "Listen to your favorite song",
            "Have a healthy snack and hydrate",
            "Do a quick meditation"
        ]
        
        selected = random.sample(activities, 3)
        response = "Here are some break activities you could try:\n"
        for activity in selected:
            response += f"• {activity}\n"
        
        return {
            "sessionInfo": {"parameters": {"break_suggested": True}},
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [response]}}]
            }
        }
    
    @staticmethod
    def _get_params(ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Extract parameters from context."""
        return (ctx.get("sessionInfo") or {}).get("parameters", {})
    
    @staticmethod
    def _get_param(ctx: Dict[str, Any], key: str, default: Any = None) -> Any:
        """Get a specific parameter from context."""
        return WebhookHandlers._get_params(ctx).get(key, default)


class NaturalLanguageMapper:
    """
    Maps natural language webhook action descriptions to actual handler functions.
    Uses pattern matching and keyword extraction.
    """
    
    # Mapping patterns to handler methods
    PATTERNS = [
        (r"fetch.*assignment|get.*assignment|show.*assignment|upcoming.*assignment", 
        "fetch_upcoming_assignments"),
        (r"create.*study.*block|schedule.*study|book.*study.*time|add.*study.*session", 
        "create_study_block"),
        (r"check.*calendar|calendar.*conflict|conflict.*check|schedule.*conflict", 
        "check_calendar_conflicts"),
        (r"time.*management.*tip|productivity.*tip|study.*tip|management.*advice", 
        "get_time_management_tips"),
        (r"analyze.*workload|workload.*analysis|assess.*workload|check.*workload", 
        "analyze_workload"),
        (r"suggest.*break|break.*activity|break.*suggestion|rest.*activity", 
        "suggest_break_activities"),
    ]
    
    @classmethod
    def find_handler(cls, action_text: str) -> Optional[str]:
        """
        Find the appropriate handler based on natural language description.
        Returns the handler method name or None.
        """
        if not action_text:
            return None
        
        # Convert to lowercase for matching
        text_lower = action_text.lower()
        
        # Try pattern matching
        for pattern, handler in cls.PATTERNS:
            if re.search(pattern, text_lower):
                logger.info(f"Matched '{action_text}' to handler '{handler}'")
                return handler
        
        # Fallback: try to generate handler name from keywords
        # This handles cases where the tag was already processed
        if "_" in action_text and not " " in action_text:
            # Looks like it's already a method name
            return action_text
        
        logger.warning(f"No handler found for action: '{action_text}'")
        return None


# ================================
# MAIN DISPATCHER
# ================================

class Dispatcher:
    """Main dispatcher that routes webhook calls to appropriate handlers."""
    
    def __init__(self):
        self.handlers = WebhookHandlers()
        self.mapper = NaturalLanguageMapper()
    
    def dispatch(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main dispatch method that processes Dialogflow webhook requests.
        """
        # Extract webhook tag/action
        fulfillment_info = body.get("fulfillmentInfo", {})
        tag = fulfillment_info.get("tag", "")
        
        logger.info(f"Received webhook call with tag: '{tag}'")
        
        # Find appropriate handler
        handler_name = self.mapper.find_handler(tag)
        
        if handler_name and hasattr(self.handlers, handler_name):
            # Call the handler
            handler = getattr(self.handlers, handler_name)
            try:
                result = handler(body)
                logger.info(f"Successfully executed handler: {handler_name}")
                return result
            except Exception as e:
                logger.error(f"Error executing handler {handler_name}: {e}")
                return self._error_response(f"Error processing request: {str(e)}")
        else:
            # No handler found - return generic response
            logger.warning(f"No handler for tag '{tag}', returning default response")
            return self._default_response()
    
    def _default_response(self) -> Dict[str, Any]:
        """Return a default response when no handler is found."""
        return {
            "fulfillmentResponse": {
                "messages": [{"text": {"text": ["I'll help you with that."]}}]
            }
        }
    
    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """Return an error response."""
        return {
            "fulfillmentResponse": {
                "messages": [{"text": {"text": [f"I encountered an issue: {error_msg}"]}}]
            }
        }


# ================================
# FLASK APP
# ================================

# Initialize dispatcher
dispatcher = Dispatcher()

# Optional shared secret for security
SHARED_SECRET = os.getenv("DISPATCHER_SECRET")

@app.before_request
def check_auth():
    """Check authentication if shared secret is configured."""
    if SHARED_SECRET and request.path == "/dispatcher":
        provided_secret = request.headers.get("X-Dispatcher-Secret")
        if provided_secret != SHARED_SECRET:
            logger.warning("Unauthorized access attempt")
            return jsonify({"error": "unauthorized"}), 401

@app.post("/dispatcher")
def handle_webhook():
    """Main webhook endpoint for Dialogflow."""
    try:
        body = request.get_json(silent=True) or {}
        logger.info(f"Received webhook request: {body.get('fulfillmentInfo', {}).get('tag', 'no-tag')}")
        
        # Dispatch to appropriate handler
        response = dispatcher.dispatch(body)
        
        # Log response
        logger.info(f"Sending response: {response.get('fulfillmentResponse', {}).get('messages', [])}")
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error handling webhook: {e}", exc_info=True)
        return jsonify({
            "fulfillmentResponse": {
                "messages": [{"text": {"text": ["I encountered an error processing your request."]}}]
            }
        }), 200  # Return 200 to prevent Dialogflow retry

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.get("/")
def index():
    """Root endpoint with API information."""
    return jsonify({
        "service": "Dialogflow Dispatcher",
        "version": "2.0",
        "endpoints": {
            "/dispatcher": "POST - Main webhook endpoint",
            "/health": "GET - Health check",
            "/test": "POST - Test endpoint for debugging"
        }
    })

@app.post("/test")
def test_webhook():
    """Test endpoint for debugging webhook actions."""
    body = request.get_json() or {}
    tag = body.get("tag", "")
    
    # Create a mock Dialogflow request
    mock_request = {
        "fulfillmentInfo": {"tag": tag},
        "sessionInfo": {"parameters": body.get("parameters", {})}
    }
    
    response = dispatcher.dispatch(mock_request)
    return jsonify(response)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting dispatcher on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Shared secret: {'configured' if SHARED_SECRET else 'not configured'}")
    
    app.run(host="0.0.0.0", port=port, debug=debug)