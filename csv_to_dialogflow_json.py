import pandas as pd
import json
import sys
import argparse
import re
import os
from pathlib import Path

# Core required columns
REQUIRED_COLUMNS = [
    "Page Name",
    "Intent Name", 
    "Trigger Type & User Example",
    "Bot Prompt",
    "Next Page / Transition",
    "Parameter Set",
    "Webhook Action",
    "Suggested Chips",
]

# Optional columns that might exist
OPTIONAL_COLUMNS = [
    "Step",
    "Next Step",
    "Notes/Comments"
]

def sanitize(value):
    """Clean up cell values, handling various empty indicators."""
    if pd.isna(value) or value is None:
        return None
    s = str(value).strip()
    # Common empty indicators in sheets - these mean "no value"
    if s in {"—", "-", "__", "_", "", "N/A", "n/a", "nan", "None"}:
        return None
    return s

def parse_params(param_str):
    """Parse comma-separated key=value pairs."""
    if not param_str:
        return {}
    result = {}
    for pair in str(param_str).split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k.strip()] = v.strip()
        else:
            # If no =, treat as a key with empty value
            result[pair] = ""
    return result

def strip_wrapping_quotes(s: str) -> str:
    """Remove wrapping quotes from a string."""
    s = s.strip()
    # Handle escaped quotes first
    s = s.replace('""', '"')
    # Remove outer quotes if present
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s

def parse_chips(chips_cell) -> list[str]:
    """
    Parse chips from cell. Chips can be:
    - One per line, each typically wrapped in quotes
    - Separated by newlines within the cell
    - Sometimes comma-separated (fallback)
    """
    if chips_cell is None:
        return []
    raw = str(chips_cell).strip()
    if not raw or raw in {"—", "-", "__", "_", ""}:
        return []
    
    chips = []
    
    # Primary method: split by newlines (most common in sheets)
    if '\n' in raw:
        parts = raw.split('\n')
    # Fallback: try semicolon separation
    elif ';' in raw:
        parts = raw.split(';')
    # Last resort: treat as single chip
    else:
        parts = [raw]
    
    # Process each part
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Handle escaped quotes
        p = p.replace('""', '"')
        # Strip wrapping quotes
        p = strip_wrapping_quotes(p)
        if p and p not in {"—", "-", "__", "_"}:
            chips.append(p)
    
    # Remove duplicates while preserving order
    seen = set()
    out = []
    for c in chips:
        if c not in seen:
            out.append(c)
            seen.add(c)
    
    return out

def parse_next_pages(cell, chips_count):
    """
    Parse Next Page / Transition which may be:
    - Empty/None (indicating end of flow/branch)
    - A single value (applies to all chips)
    - Slash-separated values aligned by chip index (e.g., PageA/PageB/PageC)
    - Newline-separated values (alternative format)
    """
    if cell is None:
        # No next page = end state (this is valid!)
        return [None] * chips_count
    
    s = str(cell).strip()
    if not s or s in {"—", "-", "__", "_", "N/A", "n/a"}:
        # These all indicate end states
        return [None] * chips_count
    
    # Check for newline separation first
    if '\n' in s:
        targets = [t.strip() for t in s.split('\n') if t.strip()]
    # Then check for slash separation
    elif '/' in s and not s.startswith('http'):  # Don't split URLs
        targets = [t.strip() for t in s.split('/') if t.strip()]
    else:
        # Single target for all chips
        return [s] * chips_count
    
    # Clean targets - convert empty strings to None
    cleaned_targets = []
    for t in targets:
        if t and t not in {"—", "-", "__", "_", "N/A", "n/a"}:
            cleaned_targets.append(t)
        else:
            cleaned_targets.append(None)  # End state for this path
    
    # Handle target count vs chip count mismatch
    if len(cleaned_targets) == 1:
        # Single target for all chips
        return cleaned_targets * chips_count
    elif len(cleaned_targets) == chips_count:
        # Perfect match
        return cleaned_targets
    else:
        # Mismatch - log warning but try to handle gracefully
        print(f"  Warning: Next Page count ({len(cleaned_targets)}) doesn't match chip count ({chips_count})")
        # If we have fewer targets than chips, pad with the last target (or None)
        while len(cleaned_targets) < chips_count:
            cleaned_targets.append(cleaned_targets[-1] if cleaned_targets else None)
        return cleaned_targets[:chips_count]

def parse_trigger_and_example(trigger_raw):
    """
    Parse the "Trigger Type & User Example" column.
    Format is typically: "Intent: User says 'example'" or "Event: Something happens"
    Returns: (trigger_type, user_example)
    """
    if not trigger_raw:
        return None, None
    
    # Common pattern: "Type: Example"
    if ':' in trigger_raw:
        parts = trigger_raw.split(':', 1)
        trigger_type = parts[0].strip()
        example = parts[1].strip() if len(parts) > 1 else ""
        
        # Clean up common phrases
        example = example.replace('User says ', '')
        example = example.replace('User responds with ', '')
        example = example.replace('User denies ', '')
        example = example.replace('User accepts ', '')
        example = strip_wrapping_quotes(example)
        
        return trigger_type, example
    
    # No colon - treat entire string as example
    return "Intent", strip_wrapping_quotes(trigger_raw)

def slugify(s: str) -> str:
    """Convert string to valid Dialogflow identifier."""
    s = s.lower().strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")

def generate_webhook_tag(action_text: str) -> str:
    """
    Generate a webhook tag from plain English description.
    """
    if not action_text:
        return None
    
    # Convert to lowercase and extract key words
    text = action_text.lower()
    
    # Remove common filler words
    stopwords = {'for', 'the', 'and', 'or', 'with', 'from', 'to', 'a', 'an', 'in', 'on', 'at', 'of'}
    words = [w for w in text.split() if w not in stopwords]
    
    # Take first 3-4 meaningful words
    tag_words = words[:4]
    
    # Join with underscores
    tag = '_'.join(tag_words)
    
    # Clean up
    tag = re.sub(r'[^a-z0-9_]', '', tag)
    tag = re.sub(r'_+', '_', tag)
    
    return tag.strip('_')

def convert_single_csv(csv_path, output_path=None):
    """Convert a single CSV file to Dialogflow JSON."""
    
    print(f"\nProcessing: {csv_path}")
    
    # Read CSV
    df = pd.read_csv(csv_path)
    
    # Check for required columns
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"  Warning: Missing columns: {missing}")
        print(f"  Available columns: {list(df.columns)}")
    
    # Check for optional columns
    has_step = "Step" in df.columns
    has_next_step = "Next Step" in df.columns
    if has_step or has_next_step:
        print(f"  Found Step/Next Step columns - will include in metadata")
    
    # Output structure
    data = {
        "pages": {},
        "intents": {},
        "routes": [],
        "end_pages": [],  # Track pages that are end states
        "first_page": None,
        "webhooks": {},
        "metadata": {
            "source_file": os.path.basename(csv_path),
            "has_step_info": has_step or has_next_step
        }
    }
    
    # Track which pages have no outgoing routes (end states)
    pages_with_routes = set()
    all_pages = set()
    
    # Process each row
    for row_idx, row in df.iterrows():
        try:
            page = sanitize(row.get("Page Name"))
            if not page:
                continue
            
            all_pages.add(page)
            
            intent_name_raw = sanitize(row.get("Intent Name"))
            trigger_raw = sanitize(row.get("Trigger Type & User Example"))
            bot_prompt = sanitize(row.get("Bot Prompt"))
            next_page_cell = sanitize(row.get("Next Page / Transition"))
            param_set = parse_params(sanitize(row.get("Parameter Set")))
            webhook_action_raw = sanitize(row.get("Webhook Action"))
            chips = parse_chips(row.get("Suggested Chips"))
            
            # Get step info if available
            step_info = {}
            if has_step:
                step = sanitize(row.get("Step"))
                if step:
                    step_info["step"] = step
            if has_next_step:
                next_step = sanitize(row.get("Next Step"))
                if next_step:
                    step_info["next_step"] = next_step
            
            # Parse trigger type and user example
            trigger_type, user_example = parse_trigger_and_example(trigger_raw)
            
            # Generate webhook tag from plain English
            webhook_tag = None
            if webhook_action_raw:
                webhook_tag = generate_webhook_tag(webhook_action_raw)
                if webhook_tag:
                    data["webhooks"][webhook_tag] = webhook_action_raw
            
            # Initialize page
            pg = data["pages"].setdefault(page, {
                "prompts": [], 
                "chips": [],
                "metadata": {}
            })
            
            if bot_prompt and bot_prompt not in pg["prompts"]:
                pg["prompts"].append(bot_prompt)
            
            for c in chips:
                if c not in pg["chips"]:
                    pg["chips"].append(c)
            
            # Add step info to page metadata
            if step_info:
                pg["metadata"].update(step_info)
            
            # Set first page (excluding StartPage)
            if not data["first_page"] and page.lower() not in ["startpage", "start_page", "start"]:
                data["first_page"] = page
            
            # Parse next pages (may be multiple if chips have different targets)
            next_pages = parse_next_pages(next_page_cell, len(chips) if chips else 1)
            
            # Track if this page has any outgoing routes
            has_valid_route = False
            
            # Create routes
            if not chips:
                # No chips - create single route with user example (if there's a next page)
                intent_name = intent_name_raw or f"Intent_{slugify(page)}_{row_idx}"
                
                intent = data["intents"].setdefault(intent_name, {"training_phrases": []})
                if user_example and user_example not in intent["training_phrases"]:
                    intent["training_phrases"].append(user_example)
                
                # Check if there's a valid next page
                if next_pages[0] is not None:
                    data["routes"].append({
                        "page": page,
                        "intent": intent_name,
                        "next_page": next_pages[0],
                        "webhook_action": webhook_tag,
                        "parameters": param_set or None
                    })
                    pages_with_routes.add(page)
                    has_valid_route = True
                else:
                    # This is an end state - still create the intent but no route
                    print(f"  Page '{page}' is an end state (no next page)")
            else:
                # With chips - create route for each chip
                for i, chip in enumerate(chips):
                    # Create intent name that includes the chip for clarity
                    base_intent = intent_name_raw or f"Intent_{slugify(page)}"
                    chip_intent_name = f"{base_intent} :: {chip}"
                    
                    # Intent training phrases include both chip text and optional user example
                    intent = data["intents"].setdefault(chip_intent_name, {"training_phrases": []})
                    
                    # Always add chip as training phrase
                    if chip not in intent["training_phrases"]:
                        intent["training_phrases"].append(chip)
                    
                    # Add user example if provided
                    if user_example and user_example not in intent["training_phrases"]:
                        intent["training_phrases"].append(user_example)
                    
                    # Get the next page for this chip
                    next_page_value = next_pages[i] if i < len(next_pages) else next_pages[0]
                    
                    # Create route only if there's a next page
                    if next_page_value is not None:
                        data["routes"].append({
                            "page": page,
                            "intent": chip_intent_name,
                            "next_page": next_page_value,
                            "webhook_action": webhook_tag,
                            "parameters": param_set or None
                        })
                        pages_with_routes.add(page)
                        has_valid_route = True
                    else:
                        # This chip leads to an end state
                        print(f"  Chip '{chip}' from page '{page}' leads to end state")
            
            # Mark page as end state if it has no outgoing routes
            if not has_valid_route and bot_prompt:  # Only if page has content
                if page not in data["end_pages"]:
                    data["end_pages"].append(page)
                    
        except Exception as e:
            print(f"  Error processing row {row_idx + 2}: {e}")
            continue
    
    # Identify pages that are never referenced as next pages (additional end states)
    referenced_pages = set()
    for route in data["routes"]:
        if route.get("next_page"):
            referenced_pages.add(route["next_page"])
    
    # Any page not referenced and not the first page might be an end state
    for page in all_pages:
        if page not in referenced_pages and page != data["first_page"] and page not in pages_with_routes:
            if page not in data["end_pages"]:
                data["end_pages"].append(page)
                print(f"  Page '{page}' identified as end state (no incoming or outgoing routes)")
    
    # Generate output path if not specified
    if not output_path:
        base_name = Path(csv_path).stem
        output_path = f"dialogflow_{base_name}.json"
    
    # Write JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    # Summary
    print(f"\n✓ Converted {csv_path} -> {output_path}")
    print(f"  Pages: {len(data['pages'])} (including {len(data['end_pages'])} end states)")
    print(f"  Intents: {len(data['intents'])}")
    print(f"  Routes: {len(data['routes'])}")
    if data['webhooks']:
        print(f"  Webhooks: {list(data['webhooks'].keys())[:5]}...")
    if data["end_pages"]:
        print(f"  End state pages: {', '.join(data['end_pages'][:5])}")
    
    return output_path

def convert_bulk(input_dir, output_dir=None):
    """Convert all CSV files in a directory."""
    input_path = Path(input_dir)
    if not input_path.exists():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    
    # Create output directory
    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = input_path / "dialogflow_json"
    output_path.mkdir(exist_ok=True)
    
    # Find all CSV files
    csv_files = list(input_path.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {input_dir}")
        return [], []
    
    print(f"Found {len(csv_files)} CSV files to convert")
    print("=" * 50)
    
    results = []
    errors = []
    
    for csv_file in csv_files:
        try:
            output_file = output_path / f"dialogflow_{csv_file.stem}.json"
            convert_single_csv(str(csv_file), str(output_file))
            results.append(csv_file.name)
        except Exception as e:
            print(f"✗ Failed to convert {csv_file.name}: {e}")
            errors.append((csv_file.name, str(e)))
    
    # Summary
    print("\n" + "=" * 50)
    print(f"Conversion complete: {len(results)}/{len(csv_files)} successful")
    if errors:
        print("\nFailed conversions:")
        for file, error in errors:
            print(f"  - {file}: {error}")
    
    return results, errors

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert CSV files to Dialogflow JSON format")
    parser.add_argument("input", help="CSV file or directory containing CSV files")
    parser.add_argument("--output", help="Output JSON file or directory")
    parser.add_argument("--bulk", action="store_true", help="Process all CSV files in directory")
    
    args = parser.parse_args()
    
    try:
        if args.bulk or os.path.isdir(args.input):
            convert_bulk(args.input, args.output)
        else:
            convert_single_csv(args.input, args.output)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)