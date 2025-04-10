import argparse
import json
import os
import sys
import re
import hashlib
import csv
from datetime import datetime
from flask import Flask, request, Response, send_file
from lxml import etree

app = Flask(__name__)

# Global variables to store configuration
config = {
    "api_key": None,
    "nzb_path": None,
    "nzbs_data": None,
    "external_url": None,
    "categories": {}
}

def load_nzbs_data(json_file_path):
    """Load the NZB metadata from the JSON file."""
    if not os.path.exists(json_file_path):
        print(f"Error: NZB files JSON '{json_file_path}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(json_file_path, 'r') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading JSON file: {e}", file=sys.stderr)
        sys.exit(1)

def load_categories():
    """Load category mappings from CSV file."""
    categories = {}
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "newznab_categories.csv")
    
    if not os.path.exists(csv_path):
        print(f"Warning: Categories file '{csv_path}' not found. Using empty category mappings.")
        return categories
    
    try:
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # Skip header row if present
            for row in reader:
                if len(row) >= 2:
                    category_id = row[0].strip()
                    category_name = row[1].strip()
                    categories[category_id] = category_name
    except Exception as e:
        print(f"Warning: Error loading categories file: {e}", file=sys.stderr)
    
    return categories

def get_named_categories(categories):
    named_categories = []
    child_parents = [str(1000*divmod(int(i),1000)[0]) for i in categories if divmod(int(i),1000)[1] > 0]
    for category in categories:
        if category not in child_parents:
            named_categories.append(get_category_name(category))

    return named_categories

def verify_api_key():
    """Verify that the API key is present and valid."""
    api_key = request.args.get('apikey')
    if not api_key or api_key != config["api_key"]:
        return False
    return True

def error_response(code, message):
    """Generate an error response in Newznab XML format."""
    root = etree.Element("error", code=str(code), description=message)
    xml_str = etree.tostring(
        root, 
        xml_declaration=True, 
        encoding="UTF-8", 
        pretty_print=True
    )
    return Response(xml_str, mimetype='application/xml')

def get_guid_from_filename(filename):
    """Generate MD5 hash of the NZB filename to use as GUID."""
    return hashlib.md5(filename.encode('utf-8')).hexdigest()

def get_category_name(category_id):
    """Get category name from ID using the loaded mappings."""
    return config["categories"].get(str(category_id), f"Category {category_id}")

def build_item_xml(item, parent_element):
    """Build XML for a single NZB item."""
    current_time = datetime.now().strftime("%a, %d %b %Y %H:%M:%S %z")
    
    # Convert categories to a list if it's a single value
    categories = item.get("categories", [])
    if not isinstance(categories, list):
        categories = [categories]
    
    # Generate MD5 hash of filename for GUID
    filename = item.get('filename', '')
    guid = get_guid_from_filename(filename)
    
    # Create item element
    item_elem = etree.SubElement(parent_element, "item")
    
    # Add item details
    title_elem = etree.SubElement(item_elem, "title")
    title_elem.text = item.get('title', 'Unknown')
    
    guid_elem = etree.SubElement(item_elem, "guid", isPermaLink="true")
    guid_elem.text = f"{config['external_url']}/details/{guid}"
    
    link_elem = etree.SubElement(item_elem, "link")
    link_elem.text = f"{config['external_url']}/api?t=get&id={guid}&apikey={config['api_key']}"
    
    comments_elem = etree.SubElement(item_elem, "comments")
    comments_elem.text = f"{config['external_url']}/details/{guid}"
    
    pubdate_elem = etree.SubElement(item_elem, "pubDate")
    pubdate_elem.text = current_time
    
    # Add categories
    for category in get_named_categories(categories):
        category_elem = etree.SubElement(item_elem, "category")
        category_elem.text = category
    
    # Add enclosure
    enclosure_elem = etree.SubElement(
        item_elem, 
        "enclosure", 
        url=f"{config['external_url']}/api?t=get&id={guid}&apikey={config['api_key']}",
        length=str(item.get('size', 0)),
        type="application/x-nzb"
    )
    
    # Add newznab attributes
    newznab_ns = "http://www.newznab.com/DTD/2010/feeds/attributes/"
    
    for category in categories:
        attr_cat = etree.SubElement(
            item_elem, 
            "{%s}attr" % newznab_ns, 
            name="category", 
            value=str(category)
        )
    
    attr_size = etree.SubElement(
        item_elem, 
        "{%s}attr" % newznab_ns, 
        name="size", 
        value=str(item.get('size', 0))
    )
    
    attr_guid = etree.SubElement(
        item_elem, 
        "{%s}attr" % newznab_ns, 
        name="guid", 
        value=guid
    )
    
    attr_group = etree.SubElement(
        item_elem, 
        "{%s}attr" % newznab_ns, 
        name="group", 
        value=str(item.get('group', 'alt.binaries'))
    )

@app.route('/api', methods=['GET'])
def api():
    """Handle API requests."""
    if not verify_api_key():
        return error_response(100, "Invalid API key")
    
    t = request.args.get('t', '')
    
    if t == 'search' or t == 'tvsearch' or t == 'movie':
        return handle_search()
    elif t == 'get':
        return handle_get()
    else:
        return error_response(203, f"Function not available: {t}")

def handle_search():
    """Handle search API requests."""
    query = request.args.get('q', '')
    cat = request.args.get('cat', '')
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))
    
    # Process query to handle space delimited words and strip common punctuation
    query_terms = []
    if query:
        # Strip common punctuation and split by whitespace
        clean_query = re.sub(r'[,.!?;:"\'-]', ' ', query)
        query_terms = [term.lower() for term in clean_query.split() if term]
    
    # Filter by query and category if provided
    results = []
    for item in config["nzbs_data"]:
        match = True
        
        if query_terms:
            title = item.get('title', '').lower()
            # Check if all query terms are in the title
            if not all(term in title for term in query_terms):
                match = False
            
        if cat:
            # Check if the item's category matches any of the requested categories
            cat_list = cat.split(',')
            item_cats = item.get('categories', [])
            if not isinstance(item_cats, list):
                item_cats = [item_cats]
                
            if not any(c in cat_list for c in item_cats):
                match = False
                
        if match:
            results.append(item)
    
    # Apply pagination
    paginated_results = results[offset:offset+limit]
    
    # Build XML response using lxml
    root = etree.Element(
        "rss", 
        version="2.0", 
        nsmap={
            "atom": "http://www.w3.org/2005/Atom",
            "newznab": "http://www.newznab.com/DTD/2010/feeds/attributes/"
        }
    )
    
    channel = etree.SubElement(root, "channel")
    
    title = etree.SubElement(channel, "title")
    title.text = "Newznab Mock"
    
    description = etree.SubElement(channel, "description")
    description.text = "Newznab Mock API Results"
    
    link = etree.SubElement(channel, "link")
    link.text = config['external_url']
    
    language = etree.SubElement(channel, "language")
    language.text = "en-gb"
    
    webmaster = etree.SubElement(channel, "webMaster")
    webmaster.text = f"admin@{config['external_url'].replace('http://', '').replace('https://', '')}"
    
    category = etree.SubElement(channel, "category")
    category.text = "NZB"
    
    atom_link = etree.SubElement(
        channel, 
        "{http://www.w3.org/2005/Atom}link", 
        href=f"{config['external_url']}/api", 
        rel="self", 
        type="application/rss+xml"
    )
    
    response = etree.SubElement(
        channel, 
        "{http://www.newznab.com/DTD/2010/feeds/attributes/}response", 
        offset=str(offset), 
        total=str(len(results))
    )
    
    # Add items
    for item in paginated_results:
        build_item_xml(item, channel)
    
    # Convert to string
    xml_str = etree.tostring(
        root, 
        xml_declaration=True, 
        encoding="UTF-8", 
        pretty_print=True
    )
    
    return Response(xml_str, mimetype='application/xml')

def handle_get():
    """Handle get API requests to retrieve NZB files."""
    nzb_id = request.args.get('id', '')
    headers = {}

    if not nzb_id:
        return error_response(200, "No NZB ID specified")
    
    # Find the item with the matching GUID (MD5 hash of filename)
    nzb_filename = None
    for item in config["nzbs_data"]:
        filename = item.get('filename', '')
        if get_guid_from_filename(filename) == nzb_id:
            nzb_filename = filename
            break
    
    if not nzb_filename:
        return error_response(300, f"NZB with ID {nzb_id} not found")
    
    # Construct the full path to the NZB file
    nzb_path = os.path.join(config["nzb_path"], nzb_filename)
    
    # Check if the file exists
    if not os.path.isfile(nzb_path):
        return error_response(300, f"NZB file {nzb_filename} not found on disk")
    
    # Read the NZB file content
    try:
        with open(nzb_path, 'r') as f:
            nzb_content = f.read()
        
        headers={"Content-disposition": "attachment",
                 "filename": nzb_filename}
        
        return send_file(nzb_path, as_attachment=True, download_name=nzb_filename, mimetype='application/x-nzb')
    except Exception as e:
        return error_response(900, f"Error reading NZB file: {e}")
    
    # Return the NZB file content
    return Response(nzb_content, mimetype='application/x-nzb', headers=headers)

def main():
    default_nzb_path = os.path.join(os.getcwd(), "nzb_files")
    
    parser = argparse.ArgumentParser(description='Mock Newznab Server', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--host', default='0.0.0.0', help='Host interface to listen on')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on')
    parser.add_argument('--external-url', default='http://localhost:5000', help='External address for the server.  Ensure this is set if being called from another machine.', metavar='URL')
    parser.add_argument('--api-key', default='mock_api_key', help='API key for requests')
    parser.add_argument('--nzb-path', default=default_nzb_path, help='Path to directory containing NZB files')
    parser.add_argument('--nzb-config', required=True, help='Path to JSON file with NZB metadata', metavar='CONFIG')
    
    args = parser.parse_args()
    
    # Validate NZB path
    if not os.path.exists(args.nzb_path):
        print(f"NZB path '{args.nzb_path}' does not exist. Creating directory.")
        try:
            os.makedirs(args.nzb_path)
        except Exception as e:
            print(f"Error creating NZB directory: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Load NZB data
    nzbs_data = load_nzbs_data(args.nzb_config)
    
    # Load category mappings
    categories = load_categories()
    
    # Store configuration
    config["api_key"] = args.api_key
    config["nzb_path"] = args.nzb_path
    config["nzbs_data"] = nzbs_data
    config["external_url"] = args.external_url
    config["categories"] = categories
    
    print(f"Starting Newznab Mock Server on {args.host}:{args.port}")
    print(f"External URL: {args.external_url}")
    print(f"API Key: {args.api_key}")
    print(f"NZB Path: {args.nzb_path}")
    print(f"NZB Files JSON: {args.nzb_config}")
    print(f"Loaded {len(nzbs_data)} NZB entries")
    print(f"Loaded {len(categories)} category mappings")
    
    # Run the Flask app
    app.run(host=args.host, port=args.port, debug=False)

if __name__ == "__main__":
    main()