# Miami Beach Parking Tickets API

A Flask API that fetches parking ticket information from the Miami-Dade Clerk's office website.

## Features

- Fetches parking ticket information by license plate tag number
- Returns detailed citation information including violation details, vehicle details, and payment information
- Exposed as a RESTful API with JSON responses

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Running as API

Start the API server:
```bash
python main.py --api
```

The API will be available at `http://localhost:5000`

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
  "count": 2,
  "total_due": "$150.00",
  "citations": [
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

## License

This project is for educational purposes. Please respect the terms of service of the Miami-Dade Clerk's website.
# MiamiParkingTicketApi
