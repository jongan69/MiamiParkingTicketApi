# Miami Beach Parking Tickets API

A Flask API that fetches parking ticket information from the Miami-Dade Clerk's office website.

## Features

- Fetches parking ticket information by license plate tag number
- Returns detailed citation information including violation details, vehicle details, and payment information
- Exposed as a RESTful API with JSON responses
- Performance optimized with concurrent requests and session reuse

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Development Mode

Start the API server for development:
```bash
python main.py --api
```

The API will be available at `http://localhost:3000`

### Production Deployment

For production deployment, use a proper WSGI server like Gunicorn:

1. **Install Gunicorn** (already included in requirements.txt):
```bash
pip install gunicorn
```

2. **Run with Gunicorn**:
```bash
gunicorn -w 4 -b 0.0.0.0:3000 wsgi:app
```

3. **Or set production environment and run**:
```bash
export FLASK_ENV=production
python main.py --api
```

**Production Configuration Options:**
- `-w 4`: Use 4 worker processes
- `-b 0.0.0.0:3000`: Bind to all interfaces on port 3000
- `--timeout 120`: Set worker timeout to 120 seconds
- `--max-requests 1000`: Restart workers after 1000 requests

**Example production command:**
```bash
gunicorn -w 4 -b 0.0.0.0:3000 --timeout 120 --max-requests 1000 wsgi:app
```

### API Endpoints

#### GET `/api/parking-tickets`

Fetches parking ticket information by license plate tag number.

**Query Parameters:**
- `tag` (required): The license plate tag number

**Example Request:**
```
GET /api/parking-tickets?tag=ABC123
```

**Example Response:**
```json
{
  "tag_number": "ABC123",
  "summary": {
    "total_citations": 2,
    "total_paid": 1,
    "total_open": 1,
    "total_due": "$150.00"
  },
  "paid_citations": [
    {
      "Citation": "123456789",
      "Date Issued": "01/15/2024",
      "Status": "PAID",
      "Amount Due": "$0.00",
      "needs_payment": false,
      "payment_required": "$0.00",
      "due_date": "02/15/2024"
    }
  ],
  "open_citations": [
    {
      "Citation": "123456789",
      "Date Issued": "01/15/2024",
      "Status": "OPEN",
      "Amount Due": "$75.00",
      "needs_payment": true,
      "payment_required": "$75.00",
      "citation_number": "123456789",
      "tag_number": "ABC123",
      "state": "FL",
      "issue_date": "01/15/2024",
      "amount_due_now": "$75.00",
      "due_date": "02/15/2024",
      "violation_type": "PARKING VIOLATION",
      "location": "123 MAIN ST",
      "municipality": "MIAMI BEACH",
      "vehicle_make": "TOYOTA",
      "vehicle_style": "SEDAN",
      "vehicle_color": "BLUE"
    }
  ]
}
```

#### GET `/`

Returns API documentation and usage information.

### Running as CLI (Original Functionality)

You can still use the original command-line interface:

```bash
python main.py TAG_NUMBER
```

Or run interactively:
```bash
python main.py
# Then enter the tag number when prompted
```

## Error Handling

The API returns appropriate HTTP status codes:

- `200`: Success
- `400`: Missing required parameter 'tag'
- `500`: Server error or failed to fetch data

## Rate Limiting

The API includes built-in delays between requests to be respectful to the Miami-Dade Clerk's website. Please use responsibly.

## Performance Optimizations

The API includes several performance optimizations:

- **Concurrent Requests**: Processes multiple citations simultaneously
- **Session Reuse**: Reuses HTTP connections for better performance
- **Form Data Caching**: Caches form data to reduce redundant requests
- **Optimized Parsing**: Efficient HTML parsing with better selectors
- **Smart Concurrency Limits**: Respectful to the target server

## Production Considerations

### Security
- Use HTTPS in production
- Implement rate limiting
- Add authentication if needed
- Use environment variables for sensitive data

### Monitoring
- Add logging for production monitoring
- Monitor API response times
- Set up health checks

### Scaling
- Use load balancers for high traffic
- Consider caching responses
- Monitor server resources

## License

This project is for educational purposes. Please respect the terms of service of the Miami-Dade Clerk's website.
